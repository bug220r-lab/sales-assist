from __future__ import annotations

import json
import unittest
from dataclasses import MISSING, FrozenInstanceError, fields, replace
from datetime import date
from pathlib import Path

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
from synthetic_sales_assist.domain.numeric import (
    CURRENCY_REGISTRY_VERSION,
    Money,
    Quantity,
)
from synthetic_sales_assist.domain.records import VersionBinding
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp
from synthetic_sales_assist.sales_credit.models import (
    SALES_CREDIT_RULE_PACK_VERSION,
    SALES_CREDIT_SCHEMA_VERSION,
    AttributionClassification,
    AttributionDecision,
    ClosedAuditRecord,
    ClosedNoteCode,
    CustomerContinuityStatus,
    EvidenceClassification,
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
    ReplacementCandidateResult,
    ReplacementDecision,
    ReplacementFacts,
    ReplacementStatus,
    SalesCreditCase,
    SalesCreditEffect,
    SalesCreditEvaluation,
    SalesCreditFact,
    SalesCreditReason,
    SalesCreditRule,
    SalesCreditValidation,
    SalesCreditValidationError,
    SearchTriggerType,
    SnapshotStatus,
    TimestampPrecision,
    ValueDecision,
    WorkflowState,
    order_provenance_binding,
    sorted_reasons,
)


ROOT = Path(__file__).resolve().parents[1]


def ts(value: str = "2026-08-20T16:00:00Z") -> CanonicalTimestamp:
    return CanonicalTimestamp(value)


def usd(minor_units: int = 12_345) -> Money:
    return Money.from_minor_units(
        minor_units,
        currency_code="USD",
        registry_version=CURRENCY_REGISTRY_VERSION,
        scale=2,
    )


def content_binding(domain: str, fixture: str) -> HashBinding:
    value = {"fixture": fixture}
    return domain_hash(
        domain,
        canonical_json_bytes(value, expected_members=set(value)),
    )


def valid_interaction(**overrides: object) -> InteractionRecord:
    values: dict[str, object] = {
        "interaction_id": InteractionId("SYN-INTERACTION-000001"),
        "source_ref": EvidenceId("SYN-EVIDENCE-INTERACTION-000001"),
        "recorded_at": ts(),
        "timestamp_precision": TimestampPrecision.EXACT,
        "review_window_start": date(2026, 8, 20),
        "review_window_end": date(2026, 9, 3),
        "workflow_state": WorkflowState.AWAITING_SOURCE_REVIEW,
        "provenance": VersionBinding(
            "sales_credit_interaction_source",
            "sales-credit-interaction-source/v1",
        ),
        "email": "synthetic.user@example.test",
        "phone": "212-555-0100",
        "vin_like_reference": "synthetic: vin reference",
        "part_request": "synthetic: brake request",
        "active_notes": "synthetic: active interaction note",
    }
    values.update(overrides)
    return InteractionRecord(**values)  # type: ignore[arg-type]


def valid_line(**overrides: object) -> LineItemSnapshot:
    values: dict[str, object] = {
        "line_id": EvidenceId("SYN-EVIDENCE-LINE-000001"),
        "sku_id": SkuId("SYN-SKU-000001"),
        "quantity": Quantity(2),
        "line_value": usd(2_500),
        "raw_es_number": "synthetic: ES#000123",
        "canonical_es_number": "123",
        "raw_mfg_oe_number": "synthetic: ab-001 / c",
        "canonical_mfg_oe_number": "AB-001 / C",
        "description": "synthetic: line description",
        "raw_line_rep": "target_rep",
        "observed_availability": "AVAILABLE",
        "observed_eta": ts("2026-08-25T16:00:00Z"),
        "warnings": ("LINE_WARNING",),
    }
    values.update(overrides)
    return LineItemSnapshot.create(**values)  # type: ignore[arg-type]


def valid_material_change(
    kind: MaterialChangeKind = MaterialChangeKind.QUANTITY_CHANGE,
    *,
    suffix: str = "000001",
) -> MaterialChange:
    return MaterialChange(
        EvidenceId(f"SYN-EVIDENCE-CHANGE-{suffix}"),
        kind,
        kind.is_material,
    )


def valid_snapshot(**overrides: object) -> OrderSnapshot:
    source_ref = EvidenceId("SYN-EVIDENCE-ORDER-SOURCE-000001")
    captured_at = ts("2026-08-21T16:00:00Z")
    parser = VersionBinding("sales_credit_parser", "sales-credit-parser/v1")
    values: dict[str, object] = {
        "snapshot_id": SnapshotId("SYN-SNAPSHOT-000001"),
        "order_id": OrderId("SYN-ORDER-000001"),
        "source_ref": source_ref,
        "captured_at": captured_at,
        "parser": parser,
        "extraction_status": SnapshotStatus.VALID,
        "lifecycle_status": OrderLifecycleStatus.ACTIVE,
        "notes_scan_status": NotesScanStatus.COMPLETE,
        "placed_at": ts("2026-08-20T18:00:00Z"),
        "placed_at_precision": TimestampPrecision.EXACT,
        "raw_order_status": "active",
        "raw_order_rep": "target_rep",
        "current_value": usd(),
        "placed_value": usd(),
        "customer_ids": (CustomerId("SYN-CUSTOMER-000001"),),
        "lines": (valid_line(),),
        "material_changes": (),
        "provenance": order_provenance_binding(
            source_ref=source_ref,
            captured_at=captured_at,
            parser=parser,
        ),
        "warnings": (),
        "active_notes": "synthetic: active order note",
    }
    values.update(overrides)
    return OrderSnapshot(**values)  # type: ignore[arg-type]


def valid_evidence(**overrides: object) -> EvidenceEvent:
    values: dict[str, object] = {
        "evidence_id": EvidenceId("SYN-EVIDENCE-EVENT-000001"),
        "order_id": OrderId("SYN-ORDER-000001"),
        "interaction_id": InteractionId("SYN-INTERACTION-000001"),
        "source_type": EvidenceSourceType.SYNTHETIC_EMAIL,
        "source_ref": EvidenceId("SYN-EVIDENCE-SOURCE-000001"),
        "occurred_at": ts("2026-08-20T17:00:00Z"),
        "timestamp_precision": TimestampPrecision.EXACT,
        "direction": EvidenceDirection.TWO_WAY,
        "target_rep_participated": True,
        "connected": False,
        "two_way": True,
        "identifier_kind": EvidenceIdentifierKind.EMAIL,
        "matched_identifier_ref": content_binding(
            EvidenceEvent.IDENTIFIER_REF_DOMAIN,
            "search-identifier-000001",
        ),
        "timing": EvidenceTimingRelation.PRE_ORDER,
        "active_excerpt": "synthetic: bounded evidence excerpt",
    }
    values.update(overrides)
    return EvidenceEvent(**values)  # type: ignore[arg-type]


def valid_attribution(**overrides: object) -> AttributionDecision:
    values: dict[str, object] = {
        "classification": AttributionClassification.TARGET_REP,
        "raw_order_rep_present": True,
    }
    values.update(overrides)
    return AttributionDecision(**values)  # type: ignore[arg-type]


def valid_value(**overrides: object) -> ValueDecision:
    values: dict[str, object] = {
        "status": OrderValueStatus.PLACED_VALUE_VERIFIED,
        "placed_value": usd(),
        "active_value": usd(),
        "material_changes": (),
    }
    values.update(overrides)
    return ValueDecision(**values)  # type: ignore[arg-type]


def valid_replacement(**overrides: object) -> ReplacementDecision:
    values: dict[str, object] = {
        "status": ReplacementStatus.NOT_APPLICABLE,
        "customer_continuity": CustomerContinuityStatus.UNKNOWN,
        "product_continuity": ProductContinuityStatus.UNKNOWN,
    }
    values.update(overrides)
    return ReplacementDecision(**values)  # type: ignore[arg-type]


def valid_candidate_input(**overrides: object) -> ReplacementCandidateInput:
    values: dict[str, object] = {
        "snapshot": valid_snapshot(
            snapshot_id=SnapshotId("SYN-SNAPSHOT-REPLACEMENT-000001"),
            order_id=OrderId("SYN-ORDER-REPLACEMENT-000001"),
        ),
        "line_universe_complete": True,
        "possible_nonexact_continuity": False,
    }
    values.update(overrides)
    return ReplacementCandidateInput(**values)  # type: ignore[arg-type]


def valid_candidate_result(**overrides: object) -> ReplacementCandidateResult:
    values: dict[str, object] = {
        "order_id": OrderId("SYN-ORDER-REPLACEMENT-000001"),
        "snapshot_id": SnapshotId("SYN-SNAPSHOT-REPLACEMENT-000001"),
        "status": ReplacementStatus.NOT_CONTINUATION,
        "customer_continuity": CustomerContinuityStatus.ABSENT,
        "product_continuity": ProductContinuityStatus.UNKNOWN,
        "reasons": (SalesCreditReason.CUSTOMER_CONTINUITY_MISMATCH,),
    }
    values.update(overrides)
    return ReplacementCandidateResult(**values)  # type: ignore[arg-type]


def valid_evaluation(**overrides: object) -> SalesCreditEvaluation:
    values: dict[str, object] = {
        "evaluation_id": EvaluationId("SYN-EVALUATION-000001"),
        "order_id": OrderId("SYN-ORDER-000001"),
        "snapshot_id": SnapshotId("SYN-SNAPSHOT-000001"),
        "workflow_state": WorkflowState.CREDIT_CONFIRMED_TARGET_REP,
        "attribution": valid_attribution(),
        "value": valid_value(),
        "replacement": valid_replacement(),
        "reasons": sorted_reasons(
            SalesCreditReason.TARGET_REP,
            SalesCreditReason.PLACED_VALUE_PROVED,
        ),
        "human_review_required": False,
        "supplied_facts": (SalesCreditFact.ORDER_REP, SalesCreditFact.ORDER_VALUE),
        "validations": (SalesCreditValidation.SNAPSHOT_ACCEPTED,),
        "rules_evaluated": (
            SalesCreditRule.ORDER_REP_ATTRIBUTION,
            SalesCreditRule.PLACED_VALUE,
        ),
        "rules_fired": (SalesCreditRule.ORDER_REP_ATTRIBUTION,),
        "persistence_effects": (
            SalesCreditEffect.ACTIVE_CASE_CLASSIFICATION,
            SalesCreditEffect.NO_PERSISTENCE_MILESTONE_2,
        ),
    }
    values.update(overrides)
    return SalesCreditEvaluation(**values)  # type: ignore[arg-type]


def valid_manager(**overrides: object) -> ManagerOutcome:
    values: dict[str, object] = {
        "occurrence_id": EvidenceId("SYN-EVIDENCE-MANAGER-000001"),
        "outcome": HumanOutcomeType.DENIED,
        "decided_at": ts("2026-08-22T16:00:00Z"),
        "actor": RepId("SYN-REP-MANAGER-000001"),
        "recorded_at": ts("2026-08-22T16:05:00Z"),
        "approved_amount": None,
        "controlled_reason": SalesCreditReason.OTHER_KNOWN_REP,
        "active_note": "synthetic: manager working note",
    }
    values.update(overrides)
    return ManagerOutcome(**values)  # type: ignore[arg-type]


def valid_case(**overrides: object) -> SalesCreditCase:
    values: dict[str, object] = {
        "order_id": OrderId("SYN-ORDER-000001"),
        "interaction_ids": (InteractionId("SYN-INTERACTION-000001"),),
        "snapshot_ids": (SnapshotId("SYN-SNAPSHOT-000001"),),
        "evidence_ids": (EvidenceId("SYN-EVIDENCE-EVENT-000001"),),
        "evaluation_ids": (EvaluationId("SYN-EVALUATION-000001"),),
        "attribution": AttributionClassification.TARGET_REP,
        "order_value_status": OrderValueStatus.PLACED_VALUE_VERIFIED,
        "placed_value": usd(),
        "workflow_state": WorkflowState.CREDIT_CONFIRMED_TARGET_REP,
        "replacement_parent": None,
        "manager_outcome": None,
        "created_at": ts("2026-08-20T16:00:00Z"),
        "updated_at": ts("2026-08-21T16:00:00Z"),
        "active_note": "synthetic: active case note",
    }
    values.update(overrides)
    return SalesCreditCase(**values)  # type: ignore[arg-type]


def valid_closed(**overrides: object) -> ClosedAuditRecord:
    values: dict[str, object] = {
        "order_id": OrderId("SYN-ORDER-000001"),
        "opened_at": ts("2026-08-20T16:00:00Z"),
        "closed_at": ts("2026-08-22T16:00:00Z"),
        "interaction_precisions": (
            TimestampPrecision.CORRECTED,
            TimestampPrecision.EXACT,
        ),
        "system_workflow_before_close": WorkflowState.OTHER_REP_HUMAN_REVIEW,
        "attribution": AttributionClassification.OTHER_REP,
        "order_value_status": OrderValueStatus.PLACED_VALUE_VERIFIED,
        "evidence_source_types": (EvidenceSourceType.SYNTHETIC_EMAIL,),
        "evidence_classifications": (
            EvidenceClassification.INBOUND_EVIDENCE_HUMAN_REVIEW,
        ),
        "reasons": (SalesCreditReason.OTHER_KNOWN_REP,),
        "human_outcome": HumanOutcomeType.DENIED,
        "human_decided_at": ts("2026-08-22T15:55:00Z"),
        "human_recorded_at": ts("2026-08-22T16:00:00Z"),
        "decision_actor": RepId("SYN-REP-MANAGER-000001"),
        "approved_amount": None,
        "controlled_reason": SalesCreditReason.OTHER_KNOWN_REP,
        "concise_note": ClosedNoteCode.HUMAN_OUTCOME_RECORDED,
        "rule_pack_version": SALES_CREDIT_RULE_PACK_VERSION,
    }
    values.update(overrides)
    return ClosedAuditRecord(**values)  # type: ignore[arg-type]


ENUM_INVENTORIES: dict[type[object], tuple[str, ...]] = {
    TimestampPrecision: (
        "EXACT",
        "CORRECTED",
        "REVISION_DERIVED",
        "HISTORICAL_APPROXIMATION",
    ),
    SearchTriggerType: (
        "NORMAL",
        "AUTOMATIC_RECHECK",
        "FORCE_RECHECK",
        "REPLACEMENT_CHECK",
    ),
    SnapshotStatus: ("VALID", "PARTIAL", "INVALID"),
    NotesScanStatus: ("COMPLETE", "INCOMPLETE", "UNAVAILABLE"),
    OrderLifecycleStatus: ("ACTIVE", "CANCELED", "UNKNOWN"),
    MaterialChangeKind: (
        "PRODUCT_ADDITION",
        "PRODUCT_REMOVAL",
        "QUANTITY_CHANGE",
        "SUBSTITUTION",
        "PARTIAL_CANCELLATION",
        "SHIPPING_CHANGE",
        "DISCOUNT",
        "PRICE_ADJUSTMENT",
        "REFUND",
        "RETURN",
        "ROUTINE_WAREHOUSE",
        "ROUTINE_INVENTORY",
        "ROUTINE_TRACKING",
        "ROUTINE_ADMINISTRATIVE",
    ),
    EvidenceSourceType: (
        "SYNTHETIC_EMAIL",
        "SYNTHETIC_PHONE_CALL",
        "SYNTHETIC_CONVERSATION",
        "SYNTHETIC_INTERACTION",
    ),
    EvidenceDirection: ("INBOUND", "OUTBOUND", "TWO_WAY", "UNKNOWN"),
    EvidenceIdentifierKind: ("EMAIL", "PHONE"),
    EvidenceTimingRelation: (
        "PRE_ORDER",
        "POST_ORDER",
        "SAME_DAY_UNCERTAIN",
        "UNKNOWN",
    ),
    EvidenceClassification: (
        "VERIFIED_PREORDER_EVIDENCE",
        "INBOUND_EVIDENCE_HUMAN_REVIEW",
        "OUTBOUND_EVIDENCE_HUMAN_REVIEW",
        "TIMING_UNCERTAIN_HUMAN_REVIEW",
        "POST_ORDER_CONTACT_ONLY",
        "UNKNOWN_OR_CONTRADICTORY",
    ),
    AttributionClassification: ("TARGET_REP", "UNASSIGNED_WEB", "OTHER_REP", "UNKNOWN"),
    OrderValueStatus: (
        "PLACED_VALUE_VERIFIED",
        "CURRENT_ONLY",
        "CHANGED_REVIEW",
        "UNKNOWN",
    ),
    CustomerContinuityStatus: ("PROVED", "ABSENT", "UNKNOWN"),
    ProductContinuityStatus: (
        "EXACT_ES",
        "EXACT_MFG_OE",
        "NONEXACT",
        "ABSENT",
        "UNKNOWN",
    ),
    ReplacementStatus: (
        "NOT_APPLICABLE",
        "WINDOW_ACTIVE",
        "WINDOW_EXPIRED",
        "EXACT_RELEVANT",
        "POSSIBLE_REVIEW",
        "NOT_CONTINUATION",
        "BLOCKED",
    ),
    HumanOutcomeType: ("APPROVED", "DENIED", "PARTIAL", "OTHER_REP", "NOT_PURSUED"),
    ClosedNoteCode: (
        "AUTOMATIC_CLASSIFICATION_CLOSED",
        "HUMAN_OUTCOME_RECORDED",
        "REVIEW_WINDOW_CLOSED_NO_ORDER",
        "CANCELED_NO_REPLACEMENT",
    ),
    SalesCreditReason: (
        "NO_USABLE_SEARCH_IDENTIFIER",
        "IDENTIFIER_SEARCH_INCOMPLETE",
        "NO_ORDER_WINDOW_ACTIVE",
        "NO_ORDER_WINDOW_CLOSED",
        "ORDER_BEFORE_INTERACTION",
        "ORDER_AFTER_REVIEW_WINDOW",
        "ORDER_BEFORE_CANCELLATION",
        "ORDER_AFTER_REPLACEMENT_WINDOW",
        "ORDER_TIMING_UNCERTAIN",
        "AUTOMATIC_RECHECK_THROTTLED_LOCAL_DAY",
        "FORCE_RECHECK_ACCEPTED",
        "SNAPSHOT_INVALID",
        "SNAPSHOT_PARTIAL_DEPENDENCY_BLOCKED",
        "MISSING_REQUIRED_FIELD",
        "UNSUPPORTED_SCHEMA_OR_SNAPSHOT",
        "CONTRADICTORY_FACTS",
        "TARGET_REP",
        "TARGET_REP_WEB",
        "UNASSIGNED_WEB",
        "OTHER_KNOWN_REP",
        "REP_MISSING",
        "REP_UNRECOGNIZED",
        "TWO_WAY_PREORDER_INTERACTION",
        "CONNECTED_PREORDER_CALL",
        "INBOUND_ONLY_PREORDER_CONTACT",
        "OUTBOUND_ONLY_PREORDER_CONTACT",
        "MISSED_OR_UNANSWERED_INBOUND_CALL",
        "POST_ORDER_CONTACT_ONLY",
        "EVIDENCE_TIMING_UNCERTAIN",
        "EVIDENCE_IDENTITY_UNPROVED",
        "NO_QUALIFYING_PREORDER_EVIDENCE",
        "CANCELED_ORDER_ZERO_ACTIVE_VALUE",
        "REPLACEMENT_WINDOW_ACTIVE",
        "EXACT_ES_PRODUCT_CONTINUITY",
        "EXACT_MFG_OE_PRODUCT_CONTINUITY",
        "NONEXACT_PRODUCT_CONTINUITY_REQUIRES_REVIEW",
        "CUSTOMER_CONTINUITY_UNPROVED",
        "CUSTOMER_CONTINUITY_MISMATCH",
        "NO_PRODUCT_CONTINUITY",
        "REPLACEMENT_WINDOW_EXPIRED",
        "PLACED_VALUE_PROVED",
        "PLACED_VALUE_UNAVAILABLE",
        "MATERIAL_CHANGE_DETECTED",
        "ROUTINE_LIFECYCLE_CHANGE_NONMATERIAL",
        "AMBIGUOUS_FACTS_REQUIRE_HUMAN_REVIEW",
    ),
    SalesCreditFact: (
        "SNAPSHOT",
        "ORDER_IDENTITY",
        "ORDER_TIMING",
        "ORDER_LIFECYCLE",
        "ORDER_REP",
        "ORDER_VALUE",
        "MATERIAL_CHANGES",
        "REPLACEMENT_CONTINUITY",
        "CONTACT_EVIDENCE",
    ),
    SalesCreditRule: (
        "SNAPSHOT_VALIDATION",
        "ORDER_WINDOW",
        "CANCELLATION",
        "REPLACEMENT",
        "PLACED_VALUE",
        "MATERIAL_CHANGE",
        "ORDER_REP_ATTRIBUTION",
        "CONTACT_EVIDENCE",
        "AMBIGUITY_ROUTING",
    ),
    SalesCreditValidation: (
        "SNAPSHOT_ACCEPTED",
        "SNAPSHOT_PARTIAL",
        "SNAPSHOT_REJECTED",
        "ORDER_ID_MATCHED",
        "ORDER_TIMING_ACCEPTED",
        "DEPENDENCY_BLOCKED",
    ),
    SalesCreditEffect: (
        "NO_PERSISTENCE_MILESTONE_2",
        "HUMAN_REVIEW_REQUIRED",
        "ZERO_ACTIVE_VALUE",
        "ACTIVE_CASE_CLASSIFICATION",
    ),
}


MODEL_FIELD_INVENTORIES: dict[type[object], tuple[str, ...]] = {
    InteractionRecord: (
        "interaction_id",
        "source_ref",
        "recorded_at",
        "timestamp_precision",
        "review_window_start",
        "review_window_end",
        "workflow_state",
        "provenance",
        "email",
        "phone",
        "corrected_at",
        "corrected_precision",
        "vin_like_reference",
        "part_request",
        "active_notes",
        "last_check_at",
        "next_eligible_check_at",
        "schema_version",
    ),
    LineItemSnapshot: (
        "line_id",
        "sku_id",
        "quantity",
        "line_value",
        "content",
        "raw_es_number",
        "canonical_es_number",
        "raw_mfg_oe_number",
        "canonical_mfg_oe_number",
        "description",
        "raw_line_rep",
        "observed_availability",
        "observed_eta",
        "warnings",
    ),
    MaterialChange: ("change_id", "kind", "affects_commercial_value"),
    OrderSnapshot: (
        "snapshot_id",
        "order_id",
        "source_ref",
        "captured_at",
        "parser",
        "extraction_status",
        "lifecycle_status",
        "notes_scan_status",
        "placed_at",
        "placed_at_precision",
        "raw_order_status",
        "raw_order_rep",
        "current_value",
        "placed_value",
        "customer_ids",
        "lines",
        "material_changes",
        "provenance",
        "canceled_at",
        "warnings",
        "active_notes",
        "schema_version",
    ),
    EvidenceEvent: (
        "evidence_id",
        "order_id",
        "interaction_id",
        "source_type",
        "source_ref",
        "occurred_at",
        "timestamp_precision",
        "direction",
        "target_rep_participated",
        "connected",
        "two_way",
        "identifier_kind",
        "matched_identifier_ref",
        "timing",
        "active_excerpt",
        "schema_version",
        "classification",
    ),
    ReplacementFacts: (
        "customer_continuity",
        "product_continuity",
        "parent_order_id",
        "replacement_order_id",
        "line_universe_complete",
    ),
    ReplacementCandidateInput: (
        "snapshot",
        "line_universe_complete",
        "possible_nonexact_continuity",
    ),
    ReplacementCandidateResult: (
        "order_id",
        "snapshot_id",
        "status",
        "customer_continuity",
        "product_continuity",
        "reasons",
    ),
    AttributionDecision: ("classification", "raw_order_rep_present"),
    ValueDecision: ("status", "placed_value", "active_value", "material_changes"),
    ReplacementDecision: (
        "status",
        "customer_continuity",
        "product_continuity",
        "search_run_id",
        "enumeration_complete",
        "candidate_results",
    ),
    SalesCreditEvaluation: (
        "evaluation_id",
        "order_id",
        "snapshot_id",
        "workflow_state",
        "attribution",
        "value",
        "replacement",
        "reasons",
        "human_review_required",
        "supplied_facts",
        "validations",
        "rules_evaluated",
        "rules_fired",
        "persistence_effects",
        "rule_pack_version",
        "schema_version",
    ),
    ManagerOutcome: (
        "occurrence_id",
        "outcome",
        "decided_at",
        "actor",
        "recorded_at",
        "approved_amount",
        "controlled_reason",
        "active_note",
        "schema_version",
    ),
    SalesCreditCase: (
        "order_id",
        "interaction_ids",
        "snapshot_ids",
        "evidence_ids",
        "evaluation_ids",
        "attribution",
        "order_value_status",
        "placed_value",
        "workflow_state",
        "replacement_parent",
        "manager_outcome",
        "created_at",
        "updated_at",
        "active_note",
        "schema_version",
    ),
    ClosedAuditRecord: (
        "order_id",
        "opened_at",
        "closed_at",
        "interaction_precisions",
        "system_workflow_before_close",
        "attribution",
        "order_value_status",
        "evidence_source_types",
        "evidence_classifications",
        "reasons",
        "human_outcome",
        "human_decided_at",
        "human_recorded_at",
        "decision_actor",
        "approved_amount",
        "controlled_reason",
        "concise_note",
        "rule_pack_version",
        "retention_policy_version",
        "schema_version",
    ),
}


REQUIRED_FIELD_INVENTORIES: dict[type[object], frozenset[str]] = {
    InteractionRecord: frozenset(MODEL_FIELD_INVENTORIES[InteractionRecord][:8]),
    LineItemSnapshot: frozenset(MODEL_FIELD_INVENTORIES[LineItemSnapshot][:5]),
    MaterialChange: frozenset(MODEL_FIELD_INVENTORIES[MaterialChange]),
    OrderSnapshot: frozenset(MODEL_FIELD_INVENTORIES[OrderSnapshot][:18]),
    EvidenceEvent: frozenset(MODEL_FIELD_INVENTORIES[EvidenceEvent][:14]),
    ReplacementFacts: frozenset(MODEL_FIELD_INVENTORIES[ReplacementFacts]),
    ReplacementCandidateInput: frozenset(
        MODEL_FIELD_INVENTORIES[ReplacementCandidateInput][:2]
    ),
    ReplacementCandidateResult: frozenset(
        MODEL_FIELD_INVENTORIES[ReplacementCandidateResult]
    ),
    AttributionDecision: frozenset(MODEL_FIELD_INVENTORIES[AttributionDecision]),
    ValueDecision: frozenset(MODEL_FIELD_INVENTORIES[ValueDecision]),
    ReplacementDecision: frozenset(
        MODEL_FIELD_INVENTORIES[ReplacementDecision][:3]
    ),
    SalesCreditEvaluation: frozenset(MODEL_FIELD_INVENTORIES[SalesCreditEvaluation][:14]),
    ManagerOutcome: frozenset(MODEL_FIELD_INVENTORIES[ManagerOutcome][:5]),
    SalesCreditCase: frozenset(MODEL_FIELD_INVENTORIES[SalesCreditCase][:13]),
    ClosedAuditRecord: frozenset(MODEL_FIELD_INVENTORIES[ClosedAuditRecord][:18]),
}


class ClosedInventoryTests(unittest.TestCase):
    def test_workflow_enum_exactly_matches_binding_json_in_order(self) -> None:
        payload = json.loads(
            (ROOT / "specs" / "sales_credit" / "workflow_states.json").read_text(
                encoding="utf-8"
            )
        )
        expected = tuple(item["state"] for item in payload["states"])
        actual = tuple(item.value for item in WorkflowState)
        self.assertEqual(len(actual), 16)
        self.assertEqual(actual, expected)
        self.assertEqual(
            tuple(payload["target_rep_literals"]),
            ("target_rep", "target_rep_web"),
        )
        self.assertEqual(payload["unassigned_web_literal"], "unassigned_web")

    def test_every_closed_enum_inventory_is_exact(self) -> None:
        for enum_type, expected in ENUM_INVENTORIES.items():
            with self.subTest(enum=enum_type.__name__):
                actual = tuple(item.value for item in enum_type)  # type: ignore[attr-defined]
                self.assertEqual(actual, expected)
                self.assertEqual(len(actual), len(set(actual)))

    def test_timestamp_precision_same_day_proof_partition_is_exact(self) -> None:
        proving = {
            item
            for item in TimestampPrecision
            if item.proves_same_day_ordering
        }
        self.assertEqual(
            proving,
            {TimestampPrecision.EXACT, TimestampPrecision.CORRECTED},
        )

    def test_enum_members_are_ordinary_assignment_immutable(self) -> None:
        for enum_type in ENUM_INVENTORIES:
            member = next(iter(enum_type))  # type: ignore[call-overload]
            with self.subTest(enum=enum_type.__name__):
                with self.assertRaises(AttributeError):
                    member.value = "MUTATED"  # type: ignore[misc]
                with self.assertRaises(TypeError):
                    member.__dict__["_value_"] = "MUTATED"


class ClosedModelShapeTests(unittest.TestCase):
    def test_model_field_inventories_are_exact(self) -> None:
        for model_type, expected in MODEL_FIELD_INVENTORIES.items():
            with self.subTest(model=model_type.__name__):
                self.assertEqual(
                    tuple(item.name for item in fields(model_type)),
                    expected,
                )

    def test_required_constructor_fields_are_exact(self) -> None:
        for model_type, expected in REQUIRED_FIELD_INVENTORIES.items():
            with self.subTest(model=model_type.__name__):
                actual = frozenset(
                    item.name
                    for item in fields(model_type)
                    if item.init
                    and item.default is MISSING
                    and item.default_factory is MISSING
                )
                self.assertEqual(actual, expected)

    def test_all_models_are_frozen_and_slotted(self) -> None:
        instances = (
            valid_interaction(),
            valid_line(),
            valid_material_change(),
            valid_snapshot(),
            valid_evidence(),
            ReplacementFacts(
                CustomerContinuityStatus.UNKNOWN,
                ProductContinuityStatus.UNKNOWN,
                None,
                None,
                False,
            ),
            valid_candidate_input(),
            valid_candidate_result(),
            valid_attribution(),
            valid_value(),
            valid_replacement(),
            valid_evaluation(),
            valid_manager(),
            valid_case(),
            valid_closed(),
        )
        for instance in instances:
            with self.subTest(model=type(instance).__name__):
                self.assertFalse(hasattr(instance, "__dict__"))
                first_field = fields(instance)[0].name
                with self.assertRaises((FrozenInstanceError, AttributeError)):
                    setattr(instance, first_field, None)

    def test_schema_and_rule_pack_versions_are_exact(self) -> None:
        self.assertEqual(SALES_CREDIT_SCHEMA_VERSION, "synthetic-sales-credit-domain/v1")
        self.assertEqual(SALES_CREDIT_RULE_PACK_VERSION, "synthetic-sales-credit-rules/v1")
        bad_schema_factories = (
            lambda: valid_interaction(schema_version="sales-credit-domain/v1"),
            lambda: valid_snapshot(schema_version="sales-credit-domain/v1"),
            lambda: valid_evidence(schema_version="sales-credit-domain/v1"),
            lambda: valid_manager(schema_version="sales-credit-domain/v1"),
            lambda: valid_case(schema_version="sales-credit-domain/v1"),
            lambda: valid_closed(schema_version="sales-credit-domain/v1"),
        )
        for factory in bad_schema_factories:
            with self.subTest(factory=factory):
                with self.assertRaises(SalesCreditValidationError):
                    factory()
        with self.assertRaisesRegex(SalesCreditValidationError, "rule_version"):
            valid_evaluation(rule_pack_version="synthetic-sales-credit-rules/v2")
        with self.assertRaisesRegex(SalesCreditValidationError, "rule_version"):
            valid_closed(rule_pack_version="synthetic-sales-credit-rules/v2")


class MaterialChangeTests(unittest.TestCase):
    def test_all_fourteen_kinds_have_exact_material_partition(self) -> None:
        self.assertEqual(len(MaterialChangeKind), 14)
        material = {
            MaterialChangeKind.PRODUCT_ADDITION,
            MaterialChangeKind.PRODUCT_REMOVAL,
            MaterialChangeKind.QUANTITY_CHANGE,
            MaterialChangeKind.SUBSTITUTION,
            MaterialChangeKind.PARTIAL_CANCELLATION,
            MaterialChangeKind.SHIPPING_CHANGE,
            MaterialChangeKind.DISCOUNT,
            MaterialChangeKind.PRICE_ADJUSTMENT,
            MaterialChangeKind.REFUND,
            MaterialChangeKind.RETURN,
        }
        for index, kind in enumerate(MaterialChangeKind, start=1):
            with self.subTest(kind=kind.value):
                self.assertEqual(kind.is_material, kind in material)
                change = valid_material_change(kind, suffix=f"{index:06d}")
                self.assertEqual(change.affects_commercial_value, kind in material)

    def test_material_flag_cannot_disagree_with_kind(self) -> None:
        for kind in MaterialChangeKind:
            with self.subTest(kind=kind.value):
                with self.assertRaisesRegex(SalesCreditValidationError, "coherence"):
                    MaterialChange(
                        EvidenceId("SYN-EVIDENCE-CHANGE-MISMATCH"),
                        kind,
                        not kind.is_material,
                    )

    def test_snapshot_material_flag_observes_all_changes(self) -> None:
        routine = valid_material_change(
            MaterialChangeKind.ROUTINE_TRACKING,
            suffix="000001",
        )
        material = valid_material_change(
            MaterialChangeKind.REFUND,
            suffix="000002",
        )
        self.assertFalse(valid_snapshot(material_changes=(routine,)).has_material_change)
        self.assertTrue(
            valid_snapshot(material_changes=(routine, material)).has_material_change
        )


class InteractionRecordTests(unittest.TestCase):
    def test_required_and_all_optional_fields_accept_exact_types(self) -> None:
        record = valid_interaction(
            corrected_at=ts("2026-08-21T05:00:00Z"),
            corrected_precision=TimestampPrecision.CORRECTED,
            review_window_start=date(2026, 8, 21),
            review_window_end=date(2026, 9, 4),
            last_check_at=ts("2026-08-21T16:00:00Z"),
            next_eligible_check_at=ts("2026-08-22T04:00:00Z"),
        )
        self.assertTrue(record.has_usable_identifier)
        self.assertEqual(record.effective_at, record.corrected_at)
        self.assertIs(record.effective_precision, TimestampPrecision.CORRECTED)
        minimal = valid_interaction(
            email=None,
            phone=None,
            vin_like_reference=None,
            part_request=None,
            active_notes=None,
        )
        self.assertFalse(minimal.has_usable_identifier)
        self.assertEqual(minimal.effective_at, minimal.recorded_at)

    def test_review_dates_are_exact_new_york_anchor_plus_fourteen(self) -> None:
        with self.assertRaisesRegex(SalesCreditValidationError, "review_start"):
            valid_interaction(review_window_start=date(2026, 8, 19))
        with self.assertRaisesRegex(SalesCreditValidationError, "review_end"):
            valid_interaction(review_window_end=date(2026, 9, 2))
        with self.assertRaisesRegex(SalesCreditValidationError, "review_dates"):
            valid_interaction(review_window_start="2026-08-20")

    def test_correction_timestamp_and_precision_are_one_conditional_pair(self) -> None:
        with self.assertRaisesRegex(SalesCreditValidationError, "correction_pair"):
            valid_interaction(corrected_at=ts("2026-08-20T17:00:00Z"))
        with self.assertRaisesRegex(SalesCreditValidationError, "correction_pair"):
            valid_interaction(corrected_precision=TimestampPrecision.CORRECTED)

    def test_contact_values_are_exact_canonical_synthetic_values(self) -> None:
        invalid_email = "private.marker@" + "outside.invalid"
        cases = (
            ("email", "Synthetic.User@example.test", "interaction_email"),
            ("email", invalid_email, "interaction_email"),
            ("phone", "212-555-0200", "interaction_phone"),
            ("phone", 2125550100, "interaction_phone"),
        )
        for field_name, value, code in cases:
            with self.subTest(field=field_name, value_type=type(value).__name__):
                with self.assertRaisesRegex(SalesCreditValidationError, code) as raised:
                    valid_interaction(**{field_name: value})
                self.assertNotIn(str(value), str(raised.exception))
                self.assertIsNone(raised.exception.__cause__)
                self.assertIsNone(raised.exception.__context__)

    def test_provenance_and_closed_types_reject_aliases(self) -> None:
        with self.assertRaisesRegex(SalesCreditValidationError, "provenance"):
            valid_interaction(provenance=VersionBinding("other", "other/v1"))
        with self.assertRaisesRegex(SalesCreditValidationError, "precision"):
            valid_interaction(timestamp_precision="EXACT")
        with self.assertRaisesRegex(SalesCreditValidationError, "workflow"):
            valid_interaction(workflow_state="AWAITING_SOURCE_REVIEW")
        with self.assertRaisesRegex(SalesCreditValidationError, "recorded_at"):
            valid_interaction(recorded_at="2026-08-20T16:00:00Z")

    def test_active_text_is_bounded_synthetic_and_redacted_from_repr(self) -> None:
        marker = "synthetic: private active marker"
        record = valid_interaction(
            vin_like_reference=marker,
            part_request=marker,
            active_notes=marker,
        )
        self.assertNotIn(marker, repr(record))
        invalid = (
            "private active marker",
            "synthetic:\nprivate marker",
            "synthetic: " + "x" * 247,
            "synthetic: snowman \N{SNOWMAN}",
        )
        for value in invalid:
            with self.subTest(length=len(value)):
                with self.assertRaises(SalesCreditValidationError) as raised:
                    valid_interaction(active_notes=value)
                self.assertNotIn(value, str(raised.exception))


class LineItemSnapshotTests(unittest.TestCase):
    def test_create_binds_exact_normalization_and_content(self) -> None:
        line = valid_line()
        self.assertEqual(line.canonical_es_number, "123")
        self.assertEqual(line.canonical_mfg_oe_number, "AB-001 / C")
        self.assertEqual(line.quantity, Quantity(2))
        self.assertEqual(line.line_value, usd(2_500))
        self.assertEqual(line.content.domain, LineItemSnapshot.CONTENT_DOMAIN)
        self.assertTrue(line.content.preimage.startswith(b"sales-credit-line-content/v1\n"))

    def test_all_optional_fields_may_be_absent(self) -> None:
        line = valid_line(
            raw_es_number=None,
            canonical_es_number=None,
            raw_mfg_oe_number=None,
            canonical_mfg_oe_number=None,
            description=None,
            raw_line_rep=None,
            observed_availability=None,
            observed_eta=None,
            warnings=(),
        )
        self.assertIsNone(line.description)

    def test_normalized_identifier_pairs_are_conditional_and_exact(self) -> None:
        with self.assertRaisesRegex(SalesCreditValidationError, "line_es_number"):
            replace(valid_line(), canonical_es_number=None)
        with self.assertRaisesRegex(SalesCreditValidationError, "line_es_number"):
            replace(valid_line(), canonical_es_number="000123")
        with self.assertRaisesRegex(SalesCreditValidationError, "line_mfg_oe_number"):
            replace(valid_line(), canonical_mfg_oe_number="AB001C")

    def test_product_identifiers_require_scanned_synthetic_source_wrappers(self) -> None:
        ordinary_es = "".join(("987", "654", "321"))
        ordinary_mfg = "".join(("ORDINARY", "-MFG-", "123"))
        for field, value, code in (
            ("raw_es_number", ordinary_es, "line_es_number"),
            ("raw_mfg_oe_number", ordinary_mfg, "line_mfg_oe_number"),
        ):
            with self.subTest(field=field):
                with self.assertRaisesRegex(SalesCreditValidationError, code) as raised:
                    valid_line(**{field: value})
                rendered = f"{raised.exception!s} {raised.exception!r}"
                self.assertNotIn(value, rendered)
                self.assertIsNone(raised.exception.__cause__)
                self.assertIsNone(raised.exception.__context__)

        wrapped = valid_line(
            raw_es_number="synthetic: ES#000456",
            canonical_es_number="456",
            raw_mfg_oe_number="synthetic: ab-002 / d",
            canonical_mfg_oe_number="AB-002 / D",
        )
        self.assertEqual(wrapped.canonical_es_number, "456")
        self.assertEqual(wrapped.canonical_mfg_oe_number, "AB-002 / D")

    def test_content_hash_is_bound_to_every_line_field(self) -> None:
        line = valid_line()
        with self.assertRaisesRegex(SalesCreditValidationError, "content_mismatch"):
            replace(line, description="synthetic: changed line description")
        wrong_domain = content_binding("sales-credit-other-content/v1", "line")
        with self.assertRaisesRegex(SalesCreditValidationError, "line_content"):
            replace(line, content=wrong_domain)

    def test_quantity_money_and_tuple_shapes_are_strict(self) -> None:
        line = valid_line()
        with self.assertRaisesRegex(SalesCreditValidationError, "line_quantity"):
            replace(line, quantity=2)
        with self.assertRaisesRegex(SalesCreditValidationError, "line_value"):
            replace(line, line_value=usd(-1))
        for warnings in (("B", "A"), ("A", "A"), ["A"]):
            with self.subTest(shape=type(warnings).__name__):
                with self.assertRaisesRegex(SalesCreditValidationError, "warnings"):
                    valid_line(warnings=warnings)

    def test_active_description_and_rep_are_private_and_closed(self) -> None:
        marker = "synthetic: private line marker"
        line = valid_line(description=marker)
        self.assertNotIn(marker, repr(line))
        with self.assertRaisesRegex(SalesCreditValidationError, "description"):
            valid_line(description="private line marker")
        with self.assertRaisesRegex(SalesCreditValidationError, "line_rep"):
            valid_line(raw_line_rep="Target Rep")

    def test_raw_rep_handles_are_binding_literals_or_explicitly_synthetic(self) -> None:
        ordinary = "".join(("ordinary", "_rep", "_handle"))
        for builder, field in (
            (valid_line, "raw_line_rep"),
            (valid_snapshot, "raw_order_rep"),
        ):
            with self.subTest(field=field):
                with self.assertRaises(SalesCreditValidationError) as raised:
                    builder(**{field: ordinary})
                self.assertNotIn(ordinary, f"{raised.exception!s} {raised.exception!r}")
                self.assertIsNone(raised.exception.__cause__)
                self.assertIsNone(raised.exception.__context__)
        self.assertEqual(
            valid_snapshot(raw_order_rep="synthetic_other_rep").raw_order_rep,
            "synthetic_other_rep",
        )


class OrderSnapshotTests(unittest.TestCase):
    def test_valid_partial_and_invalid_statuses_accept_their_consistent_shapes(self) -> None:
        valid = valid_snapshot()
        partial = valid_snapshot(
            extraction_status=SnapshotStatus.PARTIAL,
            notes_scan_status=NotesScanStatus.INCOMPLETE,
        )
        invalid = valid_snapshot(
            extraction_status=SnapshotStatus.INVALID,
            order_id=None,
            source_ref=None,
            notes_scan_status=NotesScanStatus.UNAVAILABLE,
            placed_at=None,
            placed_at_precision=None,
            raw_order_status=None,
            raw_order_rep=None,
            current_value=None,
            placed_value=None,
            customer_ids=(),
            lines=(),
            provenance=None,
        )
        self.assertIs(valid.extraction_status, SnapshotStatus.VALID)
        self.assertIs(partial.extraction_status, SnapshotStatus.PARTIAL)
        self.assertIs(invalid.extraction_status, SnapshotStatus.INVALID)

    def test_valid_snapshot_requires_complete_core_and_notes(self) -> None:
        invalid_overrides = (
            {"order_id": None},
            {"placed_at": None, "placed_at_precision": None},
            {"raw_order_status": None},
            {"current_value": None},
            {"source_ref": None, "provenance": None},
            {"notes_scan_status": NotesScanStatus.INCOMPLETE},
        )
        for overrides in invalid_overrides:
            with self.subTest(fields=tuple(overrides)):
                with self.assertRaises(SalesCreditValidationError):
                    valid_snapshot(**overrides)

    def test_partial_snapshot_cannot_hide_missing_required_core(self) -> None:
        with self.assertRaisesRegex(SalesCreditValidationError, "partial.*required"):
            valid_snapshot(
                extraction_status=SnapshotStatus.PARTIAL,
                notes_scan_status=NotesScanStatus.INCOMPLETE,
                order_id=None,
            )

    def test_partial_snapshot_must_name_a_closed_dependency_gap(self) -> None:
        with self.assertRaisesRegex(SalesCreditValidationError, "dependency_gap"):
            valid_snapshot(extraction_status=SnapshotStatus.PARTIAL)

    def test_dependency_incomplete_warnings_require_partial_status(self) -> None:
        for warning in ("CUSTOMERS_INCOMPLETE", "LINES_INCOMPLETE"):
            with self.subTest(warning=warning, status="VALID"):
                with self.assertRaisesRegex(
                    SalesCreditValidationError,
                    "dependency_incomplete_status",
                ):
                    valid_snapshot(warnings=(warning,))
            with self.subTest(warning=warning, status="INVALID"):
                with self.assertRaisesRegex(
                    SalesCreditValidationError,
                    "dependency_incomplete_status",
                ):
                    valid_snapshot(
                        extraction_status=SnapshotStatus.INVALID,
                        warnings=(warning,),
                    )
            with self.subTest(warning=warning, status="PARTIAL"):
                snapshot = valid_snapshot(
                    extraction_status=SnapshotStatus.PARTIAL,
                    warnings=(warning,),
                )
                self.assertIs(snapshot.extraction_status, SnapshotStatus.PARTIAL)

        self.assertIs(valid_snapshot(warnings=("SYNTHETIC_WARNING",)).extraction_status,
                      SnapshotStatus.VALID)

    def test_placed_timestamp_and_precision_are_one_conditional_pair(self) -> None:
        with self.assertRaisesRegex(SalesCreditValidationError, "placed_time_pair"):
            valid_snapshot(placed_at_precision=None)
        with self.assertRaisesRegex(SalesCreditValidationError, "placed_time_pair"):
            valid_snapshot(placed_at=None)

    def test_source_reference_and_provenance_are_exactly_bound(self) -> None:
        snapshot = valid_snapshot()
        with self.assertRaisesRegex(SalesCreditValidationError, "parser"):
            valid_snapshot(
                parser=VersionBinding(
                    "sales_credit_parser",
                    "sales-credit-parser/v2",
                )
            )
        with self.assertRaisesRegex(SalesCreditValidationError, "provenance_pair"):
            replace(snapshot, source_ref=None)
        with self.assertRaisesRegex(SalesCreditValidationError, "provenance_mismatch"):
            replace(
                snapshot,
                provenance=order_provenance_binding(
                    source_ref=EvidenceId("SYN-EVIDENCE-ORDER-SOURCE-OTHER"),
                    captured_at=snapshot.captured_at,
                    parser=snapshot.parser,
                ),
            )

    def test_cancellation_timestamp_is_conditional_on_lifecycle(self) -> None:
        canceled = valid_snapshot(
            lifecycle_status=OrderLifecycleStatus.CANCELED,
            canceled_at=ts("2026-08-22T16:00:00Z"),
        )
        self.assertIsNotNone(canceled.canceled_at)
        with self.assertRaisesRegex(SalesCreditValidationError, "cancellation_time"):
            valid_snapshot(lifecycle_status=OrderLifecycleStatus.CANCELED)
        with self.assertRaisesRegex(SalesCreditValidationError, "cancellation_state"):
            valid_snapshot(canceled_at=ts("2026-08-22T16:00:00Z"))

    def test_sorted_unique_children_and_nonnegative_money_are_strict(self) -> None:
        line_one = valid_line()
        line_two = valid_line(
            line_id=EvidenceId("SYN-EVIDENCE-LINE-000002"),
            sku_id=SkuId("SYN-SKU-000002"),
        )
        valid_snapshot(lines=(line_one, line_two))
        invalid_values = (
            {"customer_ids": [CustomerId("SYN-CUSTOMER-000001")]},
            {"lines": (line_two, line_one)},
            {"lines": (line_one, line_one)},
            {"current_value": usd(-1)},
            {"placed_value": usd(-1)},
        )
        for overrides in invalid_values:
            with self.subTest(fields=tuple(overrides)):
                with self.assertRaises(SalesCreditValidationError):
                    valid_snapshot(**overrides)

    def test_active_notes_and_transaction_text_are_private_and_closed(self) -> None:
        marker = "synthetic: private order marker"
        snapshot = valid_snapshot(active_notes=marker)
        self.assertNotIn(marker, repr(snapshot))
        with self.assertRaisesRegex(SalesCreditValidationError, "snapshot_notes"):
            valid_snapshot(active_notes="private order marker")
        with self.assertRaisesRegex(SalesCreditValidationError, "raw_status"):
            valid_snapshot(raw_order_status="Active Order")
        with self.assertRaisesRegex(SalesCreditValidationError, "raw_rep"):
            valid_snapshot(raw_order_rep=123)


class EvidenceEventTests(unittest.TestCase):
    def test_all_six_classifications_are_derived_from_factual_partitions(self) -> None:
        cases = (
            (
                {},
                EvidenceClassification.VERIFIED_PREORDER_EVIDENCE,
            ),
            (
                {
                    "direction": EvidenceDirection.INBOUND,
                    "target_rep_participated": False,
                    "connected": False,
                    "two_way": False,
                },
                EvidenceClassification.INBOUND_EVIDENCE_HUMAN_REVIEW,
            ),
            (
                {
                    "direction": EvidenceDirection.OUTBOUND,
                    "target_rep_participated": True,
                    "connected": False,
                    "two_way": False,
                },
                EvidenceClassification.OUTBOUND_EVIDENCE_HUMAN_REVIEW,
            ),
            (
                {"timing": EvidenceTimingRelation.SAME_DAY_UNCERTAIN},
                EvidenceClassification.TIMING_UNCERTAIN_HUMAN_REVIEW,
            ),
            (
                {"timing": EvidenceTimingRelation.POST_ORDER},
                EvidenceClassification.POST_ORDER_CONTACT_ONLY,
            ),
            (
                {"timing": EvidenceTimingRelation.UNKNOWN},
                EvidenceClassification.UNKNOWN_OR_CONTRADICTORY,
            ),
        )
        observed: set[EvidenceClassification] = set()
        for overrides, expected in cases:
            with self.subTest(expected=expected.value):
                event = valid_evidence(**overrides)
                self.assertIs(event.classification, expected)
                observed.add(event.classification)
        self.assertEqual(observed, set(EvidenceClassification))

    def test_connected_target_rep_call_is_verified(self) -> None:
        event = valid_evidence(
            source_type=EvidenceSourceType.SYNTHETIC_PHONE_CALL,
            direction=EvidenceDirection.INBOUND,
            target_rep_participated=True,
            connected=True,
            two_way=False,
            identifier_kind=EvidenceIdentifierKind.PHONE,
        )
        self.assertIs(
            event.classification,
            EvidenceClassification.VERIFIED_PREORDER_EVIDENCE,
        )

    def test_every_factual_enum_value_is_accepted_without_aliasing(self) -> None:
        for source_type in EvidenceSourceType:
            valid_evidence(
                source_type=source_type,
                timing=EvidenceTimingRelation.UNKNOWN,
            )
        for direction in EvidenceDirection:
            valid_evidence(
                direction=direction,
                timing=EvidenceTimingRelation.UNKNOWN,
            )
        for identifier in EvidenceIdentifierKind:
            valid_evidence(identifier_kind=identifier)
        for precision in TimestampPrecision:
            valid_evidence(timestamp_precision=precision)

    def test_classification_is_init_false_and_cannot_be_caller_selected(self) -> None:
        with self.assertRaises(TypeError):
            valid_evidence(classification=EvidenceClassification.POST_ORDER_CONTACT_ONLY)

    def test_boolean_and_reference_shapes_are_strict(self) -> None:
        for field_name in ("target_rep_participated", "connected", "two_way"):
            with self.subTest(field=field_name):
                with self.assertRaises(SalesCreditValidationError):
                    valid_evidence(**{field_name: 1})
        with self.assertRaisesRegex(SalesCreditValidationError, "identifier_ref"):
            valid_evidence(
                matched_identifier_ref=content_binding(
                    "sales-credit-other-identifier-ref/v1",
                    "identifier",
                )
            )
        with self.assertRaisesRegex(SalesCreditValidationError, "source_type"):
            valid_evidence(source_type="SYNTHETIC_EMAIL")

    def test_active_excerpt_is_bounded_private_and_repr_redacted(self) -> None:
        marker = "synthetic: private evidence marker"
        event = valid_evidence(active_excerpt=marker)
        self.assertNotIn(marker, repr(event))
        with self.assertRaisesRegex(SalesCreditValidationError, "excerpt"):
            valid_evidence(active_excerpt="private evidence marker")


class AttributionValueAndContinuityTests(unittest.TestCase):
    def test_every_attribution_state_has_exact_rep_presence_partition(self) -> None:
        for classification in AttributionClassification:
            if classification is AttributionClassification.UNKNOWN:
                # UNKNOWN intentionally represents both missing and unrecognized raw reps.
                self.assertFalse(AttributionDecision(classification, False).raw_order_rep_present)
                self.assertTrue(AttributionDecision(classification, True).raw_order_rep_present)
            else:
                self.assertTrue(AttributionDecision(classification, True).raw_order_rep_present)
                with self.assertRaisesRegex(SalesCreditValidationError, "coherence"):
                    AttributionDecision(classification, False)

    def test_every_value_state_accepts_only_its_closed_partition(self) -> None:
        decisions = {
            OrderValueStatus.PLACED_VALUE_VERIFIED: ValueDecision(
                OrderValueStatus.PLACED_VALUE_VERIFIED,
                usd(),
                usd(),
                (),
            ),
            OrderValueStatus.CURRENT_ONLY: ValueDecision(
                OrderValueStatus.CURRENT_ONLY,
                None,
                None,
                (),
            ),
            OrderValueStatus.CHANGED_REVIEW: ValueDecision(
                OrderValueStatus.CHANGED_REVIEW,
                None,
                None,
                (MaterialChangeKind.QUANTITY_CHANGE,),
            ),
            OrderValueStatus.UNKNOWN: ValueDecision(
                OrderValueStatus.UNKNOWN,
                None,
                None,
                (),
            ),
        }
        self.assertEqual(set(decisions), set(OrderValueStatus))
        invalid = (
            {
                "status": OrderValueStatus.PLACED_VALUE_VERIFIED,
                "placed_value": None,
                "active_value": usd(),
                "material_changes": (),
            },
            {
                "status": OrderValueStatus.CURRENT_ONLY,
                "placed_value": usd(),
                "active_value": usd(),
                "material_changes": (),
            },
            {
                "status": OrderValueStatus.UNKNOWN,
                "placed_value": None,
                "active_value": usd(),
                "material_changes": (),
            },
            {
                "status": OrderValueStatus.CURRENT_ONLY,
                "placed_value": None,
                "active_value": usd(),
                "material_changes": (),
            },
        )
        for values in invalid:
            with self.subTest(status=values["status"]):
                with self.assertRaises(SalesCreditValidationError):
                    ValueDecision(**values)  # type: ignore[arg-type]

    def test_value_money_is_nonnegative_and_material_kinds_sorted_unique(self) -> None:
        with self.assertRaisesRegex(SalesCreditValidationError, "value_placed"):
            valid_value(placed_value=usd(-1))
        with self.assertRaisesRegex(SalesCreditValidationError, "value_active"):
            valid_value(active_value=usd(-1))
        for kinds in (
            (MaterialChangeKind.REFUND, MaterialChangeKind.DISCOUNT),
            (MaterialChangeKind.REFUND, MaterialChangeKind.REFUND),
            [MaterialChangeKind.REFUND],
        ):
            with self.subTest(shape=type(kinds).__name__):
                with self.assertRaisesRegex(SalesCreditValidationError, "material_changes"):
                    ValueDecision(
                        OrderValueStatus.CHANGED_REVIEW,
                        None,
                        None,
                        kinds,  # type: ignore[arg-type]
                    )

    def test_every_customer_and_product_continuity_state_is_representable(self) -> None:
        parent = OrderId("SYN-ORDER-PARENT-000001")
        replacement = OrderId("SYN-ORDER-REPLACEMENT-000001")
        observed_customers: set[CustomerContinuityStatus] = set()
        observed_products: set[ProductContinuityStatus] = set()
        for customer in CustomerContinuityStatus:
            facts = ReplacementFacts(
                customer,
                ProductContinuityStatus.UNKNOWN,
                parent if customer is CustomerContinuityStatus.PROVED else None,
                replacement if customer is CustomerContinuityStatus.PROVED else None,
                False,
            )
            observed_customers.add(facts.customer_continuity)
        for product in ProductContinuityStatus:
            exact = product in {
                ProductContinuityStatus.EXACT_ES,
                ProductContinuityStatus.EXACT_MFG_OE,
            }
            facts = ReplacementFacts(
                CustomerContinuityStatus.UNKNOWN,
                product,
                parent if exact else None,
                replacement if exact else None,
                exact,
            )
            observed_products.add(facts.product_continuity)
        self.assertEqual(observed_customers, set(CustomerContinuityStatus))
        self.assertEqual(observed_products, set(ProductContinuityStatus))

    def test_replacement_fact_proofs_require_distinct_ids_and_complete_lines(self) -> None:
        parent = OrderId("SYN-ORDER-PARENT-000001")
        replacement = OrderId("SYN-ORDER-REPLACEMENT-000001")
        with self.assertRaisesRegex(SalesCreditValidationError, "customer_proof"):
            ReplacementFacts(
                CustomerContinuityStatus.PROVED,
                ProductContinuityStatus.UNKNOWN,
                None,
                None,
                False,
            )
        with self.assertRaisesRegex(SalesCreditValidationError, "distinct_orders"):
            ReplacementFacts(
                CustomerContinuityStatus.PROVED,
                ProductContinuityStatus.EXACT_ES,
                parent,
                parent,
                True,
            )
        with self.assertRaisesRegex(SalesCreditValidationError, "product_proof"):
            ReplacementFacts(
                CustomerContinuityStatus.UNKNOWN,
                ProductContinuityStatus.EXACT_MFG_OE,
                parent,
                replacement,
                False,
            )

    def test_replacement_candidate_input_is_strict_and_redacted(self) -> None:
        candidate = valid_candidate_input()
        self.assertNotIn(candidate.snapshot.snapshot_id.value, repr(candidate))
        for overrides in (
            {"snapshot": "SYN-SNAPSHOT-REPLACEMENT-000001"},
            {"line_universe_complete": 1},
            {"possible_nonexact_continuity": 0},
            {
                "snapshot": valid_snapshot(
                    extraction_status=SnapshotStatus.INVALID,
                    order_id=None,
                )
            },
        ):
            with self.subTest(fields=tuple(overrides)):
                with self.assertRaises(SalesCreditValidationError):
                    valid_candidate_input(**overrides)

        incomplete_lines = valid_snapshot(
            extraction_status=SnapshotStatus.PARTIAL,
            warnings=("LINES_INCOMPLETE",),
        )
        with self.assertRaisesRegex(SalesCreditValidationError, "line_completeness"):
            valid_candidate_input(snapshot=incomplete_lines)
        self.assertFalse(
            valid_candidate_input(
                snapshot=incomplete_lines,
                line_universe_complete=False,
            ).line_universe_complete
        )

    def test_candidate_results_have_closed_partitions_and_reasons(self) -> None:
        cases = (
            valid_candidate_result(
                status=ReplacementStatus.EXACT_RELEVANT,
                customer_continuity=CustomerContinuityStatus.PROVED,
                product_continuity=ProductContinuityStatus.EXACT_ES,
                reasons=(SalesCreditReason.EXACT_ES_PRODUCT_CONTINUITY,),
            ),
            valid_candidate_result(
                status=ReplacementStatus.EXACT_RELEVANT,
                customer_continuity=CustomerContinuityStatus.PROVED,
                product_continuity=ProductContinuityStatus.EXACT_MFG_OE,
                reasons=(SalesCreditReason.EXACT_MFG_OE_PRODUCT_CONTINUITY,),
            ),
            valid_candidate_result(
                status=ReplacementStatus.POSSIBLE_REVIEW,
                customer_continuity=CustomerContinuityStatus.PROVED,
                product_continuity=ProductContinuityStatus.NONEXACT,
                reasons=(
                    SalesCreditReason.NONEXACT_PRODUCT_CONTINUITY_REQUIRES_REVIEW,
                ),
            ),
            valid_candidate_result(),
            valid_candidate_result(
                customer_continuity=CustomerContinuityStatus.PROVED,
                product_continuity=ProductContinuityStatus.ABSENT,
                reasons=(SalesCreditReason.NO_PRODUCT_CONTINUITY,),
            ),
            valid_candidate_result(
                customer_continuity=CustomerContinuityStatus.UNKNOWN,
                product_continuity=ProductContinuityStatus.UNKNOWN,
                reasons=(SalesCreditReason.ORDER_AFTER_REPLACEMENT_WINDOW,),
            ),
            valid_candidate_result(
                status=ReplacementStatus.BLOCKED,
                customer_continuity=CustomerContinuityStatus.UNKNOWN,
                product_continuity=ProductContinuityStatus.UNKNOWN,
                reasons=(SalesCreditReason.SNAPSHOT_PARTIAL_DEPENDENCY_BLOCKED,),
            ),
        )
        self.assertEqual(
            {candidate.status for candidate in cases},
            {
                ReplacementStatus.BLOCKED,
                ReplacementStatus.EXACT_RELEVANT,
                ReplacementStatus.NOT_CONTINUATION,
                ReplacementStatus.POSSIBLE_REVIEW,
            },
        )
        for candidate in cases:
            with self.subTest(status=candidate.status.value):
                self.assertEqual(
                    candidate.to_dict()["status"],
                    candidate.status.value,
                )
                self.assertEqual(repr(candidate), "ReplacementCandidateResult(<redacted>)")

    def test_candidate_results_reject_open_or_incoherent_conclusions(self) -> None:
        invalid = (
            {"status": ReplacementStatus.WINDOW_ACTIVE},
            {"status": "NOT_CONTINUATION"},
            {"order_id": "SYN-ORDER-REPLACEMENT-000001"},
            {"snapshot_id": "SYN-SNAPSHOT-REPLACEMENT-000001"},
            {"reasons": ()},
            {"reasons": [SalesCreditReason.CUSTOMER_CONTINUITY_MISMATCH]},
            {
                "status": ReplacementStatus.EXACT_RELEVANT,
                "customer_continuity": CustomerContinuityStatus.PROVED,
                "product_continuity": ProductContinuityStatus.EXACT_ES,
                "reasons": (SalesCreditReason.EXACT_MFG_OE_PRODUCT_CONTINUITY,),
            },
            {
                "status": ReplacementStatus.POSSIBLE_REVIEW,
                "customer_continuity": CustomerContinuityStatus.UNKNOWN,
                "product_continuity": ProductContinuityStatus.NONEXACT,
                "reasons": (
                    SalesCreditReason.NONEXACT_PRODUCT_CONTINUITY_REQUIRES_REVIEW,
                ),
            },
            {
                "status": ReplacementStatus.BLOCKED,
                "customer_continuity": CustomerContinuityStatus.UNKNOWN,
                "product_continuity": ProductContinuityStatus.UNKNOWN,
                "reasons": (SalesCreditReason.NO_PRODUCT_CONTINUITY,),
            },
            {
                "status": ReplacementStatus.NOT_CONTINUATION,
                "customer_continuity": CustomerContinuityStatus.PROVED,
                "product_continuity": ProductContinuityStatus.EXACT_ES,
                "reasons": (SalesCreditReason.EXACT_ES_PRODUCT_CONTINUITY,),
            },
            {
                "status": ReplacementStatus.NOT_CONTINUATION,
                "customer_continuity": CustomerContinuityStatus.PROVED,
                "product_continuity": ProductContinuityStatus.EXACT_ES,
                "reasons": (
                    SalesCreditReason.ORDER_AFTER_REPLACEMENT_WINDOW,
                    SalesCreditReason.ORDER_BEFORE_CANCELLATION,
                ),
            },
            {
                "status": ReplacementStatus.EXACT_RELEVANT,
                "customer_continuity": CustomerContinuityStatus.PROVED,
                "product_continuity": ProductContinuityStatus.EXACT_ES,
                "reasons": (SalesCreditReason.ORDER_AFTER_REPLACEMENT_WINDOW,),
            },
            {
                "status": ReplacementStatus.NOT_CONTINUATION,
                "customer_continuity": CustomerContinuityStatus.PROVED,
                "product_continuity": ProductContinuityStatus.EXACT_ES,
                "reasons": (SalesCreditReason.ORDER_AFTER_REVIEW_WINDOW,),
            },
        )
        for overrides in invalid:
            with self.subTest(fields=tuple(overrides)):
                with self.assertRaises(SalesCreditValidationError):
                    valid_candidate_result(**overrides)

    def test_every_replacement_status_has_a_coherent_partition(self) -> None:
        run_id = RunId("SYN-RUN-REPLACEMENT-000001")
        exact = valid_candidate_result(
            status=ReplacementStatus.EXACT_RELEVANT,
            customer_continuity=CustomerContinuityStatus.PROVED,
            product_continuity=ProductContinuityStatus.EXACT_ES,
            reasons=(SalesCreditReason.EXACT_ES_PRODUCT_CONTINUITY,),
        )
        possible = valid_candidate_result(
            status=ReplacementStatus.POSSIBLE_REVIEW,
            customer_continuity=CustomerContinuityStatus.PROVED,
            product_continuity=ProductContinuityStatus.NONEXACT,
            reasons=(SalesCreditReason.NONEXACT_PRODUCT_CONTINUITY_REQUIRES_REVIEW,),
        )
        blocked = valid_candidate_result(
            status=ReplacementStatus.BLOCKED,
            customer_continuity=CustomerContinuityStatus.UNKNOWN,
            product_continuity=ProductContinuityStatus.UNKNOWN,
            reasons=(SalesCreditReason.SNAPSHOT_PARTIAL_DEPENDENCY_BLOCKED,),
        )
        cases = (
            valid_replacement(),
            valid_replacement(status=ReplacementStatus.WINDOW_ACTIVE),
            valid_replacement(
                status=ReplacementStatus.WINDOW_EXPIRED,
                search_run_id=run_id,
                enumeration_complete=True,
            ),
            valid_replacement(
                status=ReplacementStatus.EXACT_RELEVANT,
                customer_continuity=CustomerContinuityStatus.PROVED,
                product_continuity=ProductContinuityStatus.EXACT_ES,
                search_run_id=run_id,
                enumeration_complete=True,
                candidate_results=(exact,),
            ),
            valid_replacement(
                status=ReplacementStatus.POSSIBLE_REVIEW,
                customer_continuity=CustomerContinuityStatus.PROVED,
                product_continuity=ProductContinuityStatus.NONEXACT,
                search_run_id=run_id,
                enumeration_complete=True,
                candidate_results=(possible,),
            ),
            valid_replacement(
                status=ReplacementStatus.NOT_CONTINUATION,
                customer_continuity=CustomerContinuityStatus.ABSENT,
                search_run_id=run_id,
                enumeration_complete=True,
                candidate_results=(valid_candidate_result(),),
            ),
            valid_replacement(
                status=ReplacementStatus.BLOCKED,
                search_run_id=run_id,
                enumeration_complete=True,
                candidate_results=(blocked,),
            ),
        )
        self.assertEqual({decision.status for decision in cases}, set(ReplacementStatus))

    def test_terminal_window_expiry_requires_complete_all_nonmatches(self) -> None:
        run_id = RunId("SYN-RUN-REPLACEMENT-000001")
        terminal = valid_replacement(
            status=ReplacementStatus.WINDOW_EXPIRED,
            search_run_id=run_id,
            enumeration_complete=True,
            candidate_results=(valid_candidate_result(),),
        )
        self.assertTrue(terminal.enumeration_complete)
        self.assertEqual(terminal.search_run_id, run_id)
        for overrides in (
            {"search_run_id": None},
            {"enumeration_complete": False},
            {
                "candidate_results": (
                    valid_candidate_result(
                        status=ReplacementStatus.EXACT_RELEVANT,
                        customer_continuity=CustomerContinuityStatus.PROVED,
                        product_continuity=ProductContinuityStatus.EXACT_ES,
                        reasons=(SalesCreditReason.EXACT_ES_PRODUCT_CONTINUITY,),
                    ),
                )
            },
            {
                "candidate_results": (
                    valid_candidate_result(
                        status=ReplacementStatus.POSSIBLE_REVIEW,
                        customer_continuity=CustomerContinuityStatus.PROVED,
                        product_continuity=ProductContinuityStatus.NONEXACT,
                        reasons=(
                            SalesCreditReason.NONEXACT_PRODUCT_CONTINUITY_REQUIRES_REVIEW,
                        ),
                    ),
                )
            },
            {
                "candidate_results": (
                    valid_candidate_result(
                        status=ReplacementStatus.BLOCKED,
                        customer_continuity=CustomerContinuityStatus.UNKNOWN,
                        product_continuity=ProductContinuityStatus.UNKNOWN,
                        reasons=(SalesCreditReason.CONTRADICTORY_FACTS,),
                    ),
                )
            },
        ):
            with self.subTest(fields=tuple(overrides)):
                with self.assertRaises(SalesCreditValidationError):
                    replace(terminal, **overrides)

    def test_candidate_results_are_sorted_unique_and_owned_by_ids(self) -> None:
        first = valid_candidate_result()
        second = valid_candidate_result(
            order_id=OrderId("SYN-ORDER-REPLACEMENT-000002"),
            snapshot_id=SnapshotId("SYN-SNAPSHOT-REPLACEMENT-000002"),
        )
        run_id = RunId("SYN-RUN-REPLACEMENT-000001")
        valid_replacement(
            status=ReplacementStatus.WINDOW_ACTIVE,
            search_run_id=run_id,
            enumeration_complete=True,
            candidate_results=(first, second),
        )
        invalid = (
            (second, first),
            (first, first),
            (first, replace(second, order_id=first.order_id)),
            (first, replace(second, snapshot_id=first.snapshot_id)),
            [first, second],
        )
        for results in invalid:
            with self.subTest(shape=type(results).__name__):
                with self.assertRaisesRegex(
                    SalesCreditValidationError,
                    "candidate_results",
                ):
                    valid_replacement(
                        status=ReplacementStatus.WINDOW_ACTIVE,
                        search_run_id=run_id,
                        enumeration_complete=True,
                        candidate_results=results,
                    )

    def test_exact_candidate_dominates_later_nonmatches(self) -> None:
        nonmatch = valid_candidate_result()
        exact = valid_candidate_result(
            order_id=OrderId("SYN-ORDER-REPLACEMENT-000002"),
            snapshot_id=SnapshotId("SYN-SNAPSHOT-REPLACEMENT-000002"),
            status=ReplacementStatus.EXACT_RELEVANT,
            customer_continuity=CustomerContinuityStatus.PROVED,
            product_continuity=ProductContinuityStatus.EXACT_ES,
            reasons=(SalesCreditReason.EXACT_ES_PRODUCT_CONTINUITY,),
        )
        decision = valid_replacement(
            status=ReplacementStatus.EXACT_RELEVANT,
            customer_continuity=CustomerContinuityStatus.PROVED,
            product_continuity=ProductContinuityStatus.EXACT_ES,
            search_run_id=RunId("SYN-RUN-REPLACEMENT-000001"),
            enumeration_complete=True,
            candidate_results=(nonmatch, exact),
        )
        self.assertIs(decision.status, ReplacementStatus.EXACT_RELEVANT)
        with self.assertRaisesRegex(SalesCreditValidationError, "aggregate_mismatch"):
            replace(
                decision,
                status=ReplacementStatus.NOT_CONTINUATION,
                customer_continuity=CustomerContinuityStatus.ABSENT,
                product_continuity=ProductContinuityStatus.UNKNOWN,
            )

    def test_replacement_decision_canonical_shape_and_repr_are_closed(self) -> None:
        decision = valid_replacement()
        self.assertEqual(
            decision.to_dict(),
            {
                "candidate_results": [],
                "customer_continuity": "UNKNOWN",
                "enumeration_complete": False,
                "product_continuity": "UNKNOWN",
                "search_run_id": None,
                "status": "NOT_APPLICABLE",
            },
        )
        self.assertEqual(repr(decision), "ReplacementDecision(<redacted>)")

    def test_incoherent_replacement_decisions_fail_closed(self) -> None:
        for status, customer, product in (
            (
                ReplacementStatus.EXACT_RELEVANT,
                CustomerContinuityStatus.UNKNOWN,
                ProductContinuityStatus.EXACT_ES,
            ),
            (
                ReplacementStatus.POSSIBLE_REVIEW,
                CustomerContinuityStatus.ABSENT,
                ProductContinuityStatus.NONEXACT,
            ),
            (
                ReplacementStatus.NOT_CONTINUATION,
                CustomerContinuityStatus.PROVED,
                ProductContinuityStatus.EXACT_ES,
            ),
        ):
            with self.subTest(status=status.value):
                with self.assertRaises(SalesCreditValidationError):
                    ReplacementDecision(status, customer, product)


class SalesCreditEvaluationTests(unittest.TestCase):
    def test_canceled_no_replacement_requires_retained_terminal_authority(self) -> None:
        terminal = valid_replacement(
            status=ReplacementStatus.WINDOW_EXPIRED,
            search_run_id=RunId("SYN-RUN-REPLACEMENT-000001"),
            enumeration_complete=True,
            candidate_results=(valid_candidate_result(),),
        )
        result = valid_evaluation(
            workflow_state=WorkflowState.CANCELED_NO_REPLACEMENT,
            replacement=terminal,
            reasons=sorted_reasons(
                SalesCreditReason.PLACED_VALUE_PROVED,
                SalesCreditReason.REPLACEMENT_WINDOW_EXPIRED,
                SalesCreditReason.TARGET_REP,
            ),
        )
        self.assertIs(result.replacement.status, ReplacementStatus.WINDOW_EXPIRED)

        with self.assertRaisesRegex(
            SalesCreditValidationError,
            "replacement_terminal_state",
        ):
            valid_evaluation(workflow_state=WorkflowState.CANCELED_NO_REPLACEMENT)
        with self.assertRaisesRegex(
            SalesCreditValidationError,
            "replacement_terminal_reason",
        ):
            valid_evaluation(replacement=terminal)

    def test_closed_explanation_collections_accept_every_enum_member(self) -> None:
        evaluation = valid_evaluation(
            supplied_facts=tuple(sorted(SalesCreditFact, key=lambda item: item.value)),
            validations=tuple(
                sorted(SalesCreditValidation, key=lambda item: item.value)
            ),
            rules_evaluated=tuple(
                sorted(SalesCreditRule, key=lambda item: item.value)
            ),
            rules_fired=tuple(sorted(SalesCreditRule, key=lambda item: item.value)),
            persistence_effects=(
                SalesCreditEffect.ACTIVE_CASE_CLASSIFICATION,
                SalesCreditEffect.NO_PERSISTENCE_MILESTONE_2,
            ),
        )
        self.assertEqual(
            set(evaluation.reasons),
            {SalesCreditReason.PLACED_VALUE_PROVED, SalesCreditReason.TARGET_REP},
        )
        self.assertEqual(set(evaluation.supplied_facts), set(SalesCreditFact))
        self.assertEqual(set(evaluation.validations), set(SalesCreditValidation))
        self.assertEqual(set(evaluation.rules_evaluated), set(SalesCreditRule))
        self.assertEqual(
            set(evaluation.persistence_effects),
            {
                SalesCreditEffect.ACTIVE_CASE_CLASSIFICATION,
                SalesCreditEffect.NO_PERSISTENCE_MILESTONE_2,
            },
        )

    def test_explanation_collections_are_exact_sorted_unique_tuples(self) -> None:
        cases = (
            ("reasons", (SalesCreditReason.TARGET_REP, SalesCreditReason.REP_MISSING)),
            ("reasons", (SalesCreditReason.TARGET_REP, SalesCreditReason.TARGET_REP)),
            ("reasons", [SalesCreditReason.TARGET_REP]),
            ("supplied_facts", (SalesCreditFact.SNAPSHOT, SalesCreditFact.ORDER_REP)),
            ("validations", (SalesCreditValidation.SNAPSHOT_REJECTED,) * 2),
            ("rules_evaluated", (SalesCreditRule.PLACED_VALUE, "ORDER_WINDOW")),
            ("rules_fired", [SalesCreditRule.ORDER_REP_ATTRIBUTION]),
            (
                "persistence_effects",
                (
                    SalesCreditEffect.NO_PERSISTENCE_MILESTONE_2,
                    SalesCreditEffect.ACTIVE_CASE_CLASSIFICATION,
                ),
            ),
        )
        for field_name, value in cases:
            with self.subTest(field=field_name, shape=type(value).__name__):
                with self.assertRaises(SalesCreditValidationError):
                    valid_evaluation(**{field_name: value})

    def test_rules_fired_must_be_a_subset_of_rules_evaluated(self) -> None:
        with self.assertRaisesRegex(SalesCreditValidationError, "rule_subset"):
            valid_evaluation(
                rules_fired=(SalesCreditRule.CONTACT_EVIDENCE,),
            )

    def test_human_review_flag_and_effects_match_the_workflow(self) -> None:
        review = valid_evaluation(
            workflow_state=WorkflowState.MANUAL_REVIEW_REQUIRED,
            human_review_required=True,
            persistence_effects=(
                SalesCreditEffect.HUMAN_REVIEW_REQUIRED,
                SalesCreditEffect.NO_PERSISTENCE_MILESTONE_2,
            ),
        )
        self.assertTrue(review.human_review_required)
        invalid = (
            {
                "workflow_state": WorkflowState.MANUAL_REVIEW_REQUIRED,
                "human_review_required": False,
            },
            {
                "workflow_state": WorkflowState.CREDIT_CONFIRMED_TARGET_REP,
                "human_review_required": True,
            },
            {
                "persistence_effects": (
                    SalesCreditEffect.ACTIVE_CASE_CLASSIFICATION,
                ),
            },
            {
                "persistence_effects": (
                    SalesCreditEffect.HUMAN_REVIEW_REQUIRED,
                    SalesCreditEffect.NO_PERSISTENCE_MILESTONE_2,
                ),
            },
        )
        for overrides in invalid:
            with self.subTest(fields=tuple(overrides)):
                with self.assertRaises(SalesCreditValidationError):
                    valid_evaluation(**overrides)

    def test_identity_and_decision_fields_reject_type_aliases(self) -> None:
        invalid = (
            {"evaluation_id": "SYN-EVALUATION-000001"},
            {"order_id": "SYN-ORDER-000001"},
            {"snapshot_id": "SYN-SNAPSHOT-000001"},
            {"workflow_state": "CREDIT_CONFIRMED_TARGET_REP"},
            {"attribution": AttributionClassification.TARGET_REP},
            {"value": OrderValueStatus.PLACED_VALUE_VERIFIED},
            {"replacement": ReplacementStatus.NOT_APPLICABLE},
            {"human_review_required": 0},
        )
        for overrides in invalid:
            with self.subTest(fields=tuple(overrides)):
                with self.assertRaises(SalesCreditValidationError):
                    valid_evaluation(**overrides)


class ManagerOutcomeTests(unittest.TestCase):
    def test_all_five_human_outcomes_have_separate_coherent_records(self) -> None:
        cases = {
            HumanOutcomeType.APPROVED: usd(),
            HumanOutcomeType.DENIED: None,
            HumanOutcomeType.PARTIAL: usd(1),
            HumanOutcomeType.OTHER_REP: None,
            HumanOutcomeType.NOT_PURSUED: None,
        }
        for outcome, amount in cases.items():
            with self.subTest(outcome=outcome.value):
                record = valid_manager(outcome=outcome, approved_amount=amount)
                self.assertIs(record.outcome, outcome)
                self.assertEqual(record.approved_amount, amount)
        self.assertEqual(set(cases), set(HumanOutcomeType))

    def test_amount_partitions_and_time_order_are_fail_closed(self) -> None:
        invalid = (
            {"outcome": HumanOutcomeType.PARTIAL, "approved_amount": None},
            {"outcome": HumanOutcomeType.PARTIAL, "approved_amount": usd(0)},
            {"outcome": HumanOutcomeType.DENIED, "approved_amount": usd(1)},
            {"outcome": HumanOutcomeType.OTHER_REP, "approved_amount": usd(1)},
            {"approved_amount": usd(-1)},
            {
                "decided_at": ts("2026-08-22T16:01:00Z"),
                "recorded_at": ts("2026-08-22T16:00:00Z"),
            },
        )
        for overrides in invalid:
            with self.subTest(fields=tuple(overrides)):
                with self.assertRaises(SalesCreditValidationError):
                    valid_manager(**overrides)

    def test_manager_types_are_closed_without_coercion(self) -> None:
        invalid = (
            {"occurrence_id": "SYN-EVIDENCE-MANAGER-000001"},
            {"outcome": "DENIED"},
            {"decided_at": "2026-08-22T16:00:00Z"},
            {"actor": "SYN-REP-MANAGER-000001"},
            {"recorded_at": "2026-08-22T16:05:00Z"},
            {"controlled_reason": "OTHER_KNOWN_REP"},
        )
        for overrides in invalid:
            with self.subTest(fields=tuple(overrides)):
                with self.assertRaises(SalesCreditValidationError):
                    valid_manager(**overrides)

    def test_active_note_is_bound_but_redacted_and_rejection_retains_no_cause(self) -> None:
        marker = "synthetic: private manager marker"
        outcome = valid_manager(active_note=marker)
        self.assertNotIn(marker, repr(outcome))
        self.assertIn(marker.encode("ascii"), outcome.canonical_bytes())
        prohibited = "synthetic: private.marker@" + "outside.invalid"
        with self.assertRaises(SalesCreditValidationError) as raised:
            valid_manager(active_note=prohibited)
        self.assertNotIn(prohibited, str(raised.exception))
        self.assertIsNone(raised.exception.__cause__)
        self.assertIsNone(raised.exception.__context__)


class SalesCreditCaseTests(unittest.TestCase):
    def test_case_identity_collections_are_sorted_unique_and_strict(self) -> None:
        interaction_one = InteractionId("SYN-INTERACTION-000001")
        interaction_two = InteractionId("SYN-INTERACTION-000002")
        valid_case(interaction_ids=(interaction_one, interaction_two))
        for values in (
            (interaction_two, interaction_one),
            (interaction_one, interaction_one),
            [interaction_one],
        ):
            with self.subTest(shape=type(values).__name__):
                with self.assertRaisesRegex(SalesCreditValidationError, "interactions"):
                    valid_case(interaction_ids=values)

    def test_active_and_system_closed_cases_do_not_invent_human_outcomes(self) -> None:
        self.assertIsNone(valid_case().manager_outcome)
        system_closed = valid_case(
            workflow_state=WorkflowState.CLOSED,
            manager_outcome=None,
        )
        self.assertIsNone(system_closed.manager_outcome)
        human_closed = valid_case(
            workflow_state=WorkflowState.CLOSED,
            manager_outcome=valid_manager(),
        )
        self.assertIsNotNone(human_closed.manager_outcome)
        with self.assertRaisesRegex(SalesCreditValidationError, "outcome_workflow"):
            valid_case(manager_outcome=valid_manager())

    def test_case_time_money_types_and_private_note_are_strict(self) -> None:
        with self.assertRaisesRegex(SalesCreditValidationError, "time_order"):
            valid_case(
                created_at=ts("2026-08-22T16:00:00Z"),
                updated_at=ts("2026-08-21T16:00:00Z"),
            )
        with self.assertRaisesRegex(SalesCreditValidationError, "placed_value"):
            valid_case(placed_value=usd(-1))
        with self.assertRaisesRegex(SalesCreditValidationError, "attribution"):
            valid_case(attribution="TARGET_REP")
        marker = "synthetic: private case marker"
        case = valid_case(active_note=marker)
        self.assertNotIn(marker, repr(case))
        prohibited = "synthetic: private.marker@" + "outside.invalid"
        with self.assertRaises(SalesCreditValidationError) as raised:
            valid_case(active_note=prohibited)
        self.assertNotIn(prohibited, str(raised.exception))
        self.assertIsNone(raised.exception.__cause__)
        self.assertIsNone(raised.exception.__context__)


class ClosedAuditRecordTests(unittest.TestCase):
    def test_system_terminal_record_has_no_fabricated_human_outcome(self) -> None:
        record = valid_closed(
            system_workflow_before_close=WorkflowState.CREDIT_CONFIRMED_TARGET_REP,
            human_outcome=None,
            human_decided_at=None,
            human_recorded_at=None,
            decision_actor=None,
            approved_amount=None,
            controlled_reason=None,
            concise_note=ClosedNoteCode.AUTOMATIC_CLASSIFICATION_CLOSED,
        )
        self.assertIsNone(record.human_outcome)
        self.assertIsNone(record.decision_actor)
        self.assertIs(
            record.concise_note,
            ClosedNoteCode.AUTOMATIC_CLASSIFICATION_CLOSED,
        )
        with self.assertRaisesRegex(SalesCreditValidationError, "concise_note"):
            valid_closed(concise_note=ClosedNoteCode.CANCELED_NO_REPLACEMENT)

    def test_all_human_outcomes_retain_only_controlled_decision_metadata(self) -> None:
        cases = {
            HumanOutcomeType.APPROVED: usd(),
            HumanOutcomeType.DENIED: None,
            HumanOutcomeType.PARTIAL: usd(1),
            HumanOutcomeType.OTHER_REP: None,
            HumanOutcomeType.NOT_PURSUED: None,
        }
        for outcome, amount in cases.items():
            with self.subTest(outcome=outcome.value):
                record = valid_closed(human_outcome=outcome, approved_amount=amount)
                self.assertIs(record.human_outcome, outcome)
                self.assertEqual(record.approved_amount, amount)

    def test_human_metadata_amount_and_time_partitions_are_fail_closed(self) -> None:
        invalid = (
            {"human_outcome": None},
            {"human_decided_at": None},
            {"decision_actor": None},
            {
                "human_outcome": None,
                "human_decided_at": None,
                "human_recorded_at": None,
                "decision_actor": None,
                "approved_amount": usd(1),
            },
            {"human_outcome": HumanOutcomeType.PARTIAL, "approved_amount": None},
            {"human_outcome": HumanOutcomeType.PARTIAL, "approved_amount": usd(0)},
            {"human_outcome": HumanOutcomeType.DENIED, "approved_amount": usd(1)},
            {"approved_amount": usd(-1)},
            {
                "human_decided_at": ts("2026-08-22T16:01:00Z"),
                "human_recorded_at": ts("2026-08-22T16:00:00Z"),
            },
            {"human_decided_at": ts("2026-08-20T15:59:59.999999999Z")},
            {"human_recorded_at": ts("2026-08-23T16:00:00Z")},
        )
        for overrides in invalid:
            with self.subTest(fields=tuple(overrides)):
                with self.assertRaises(SalesCreditValidationError):
                    valid_closed(**overrides)

    def test_closed_record_collections_are_sorted_unique_exact_tuples(self) -> None:
        invalid = (
            {
                "interaction_precisions": (
                    TimestampPrecision.EXACT,
                    TimestampPrecision.CORRECTED,
                )
            },
            {
                "evidence_source_types": (
                    EvidenceSourceType.SYNTHETIC_EMAIL,
                    EvidenceSourceType.SYNTHETIC_EMAIL,
                )
            },
            {
                "evidence_classifications": [
                    EvidenceClassification.INBOUND_EVIDENCE_HUMAN_REVIEW
                ]
            },
            {
                "reasons": (
                    SalesCreditReason.TARGET_REP,
                    SalesCreditReason.OTHER_KNOWN_REP,
                )
            },
        )
        for overrides in invalid:
            with self.subTest(fields=tuple(overrides)):
                with self.assertRaises(SalesCreditValidationError):
                    valid_closed(**overrides)

    def test_closed_record_is_minimized_and_excludes_active_content(self) -> None:
        field_names = {item.name for item in fields(ClosedAuditRecord)}
        disallowed = {
            "active_note",
            "active_excerpt",
            "email",
            "phone",
            "snapshot_ids",
            "line_items",
            "message_content",
            "customer_ids",
        }
        self.assertTrue(field_names.isdisjoint(disallowed))
        canonical = valid_closed().canonical_bytes()
        for forbidden in (b"example.test", b"555-", b"synthetic: private"):
            self.assertNotIn(forbidden, canonical)

    def test_closed_prior_state_and_timestamps_are_strict(self) -> None:
        with self.assertRaisesRegex(SalesCreditValidationError, "prior_workflow"):
            valid_closed(system_workflow_before_close=WorkflowState.CLOSED)
        with self.assertRaisesRegex(SalesCreditValidationError, "time_order"):
            valid_closed(closed_at=ts("2026-08-19T16:00:00Z"))
        with self.assertRaisesRegex(SalesCreditValidationError, "attribution"):
            valid_closed(attribution="OTHER_REP")


EXPECTED_EVALUATION_CANONICAL = (
    b'{"attribution":{"classification":"TARGET_REP","raw_order_rep_present":true},'
    b'"evaluation_id":"SYN-EVALUATION-000001","human_review_required":false,'
    b'"order_id":"SYN-ORDER-000001","persistence_effects":['
    b'"ACTIVE_CASE_CLASSIFICATION","NO_PERSISTENCE_MILESTONE_2"],'
    b'"reasons":["PLACED_VALUE_PROVED","TARGET_REP"],"replacement":{'
    b'"candidate_results":[],"customer_continuity":"UNKNOWN",'
    b'"enumeration_complete":false,"product_continuity":"UNKNOWN",'
    b'"search_run_id":null,"status":"NOT_APPLICABLE"},"rule_pack_version":'
    b'"synthetic-sales-credit-rules/v1","rules_evaluated":['
    b'"ORDER_REP_ATTRIBUTION","PLACED_VALUE"],"rules_fired":['
    b'"ORDER_REP_ATTRIBUTION"],"schema_version":'
    b'"synthetic-sales-credit-domain/v1","snapshot_id":'
    b'"SYN-SNAPSHOT-000001","supplied_facts":["ORDER_REP","ORDER_VALUE"],'
    b'"validations":["SNAPSHOT_ACCEPTED"],"value":{"active_value":{'
    b'"amount":"123.45","currency_code":"USD","currency_registry_version":'
    b'"synthetic-iso-style-currency-registry/v1","currency_scale":2},'
    b'"material_changes":[],"placed_value":{"amount":"123.45",'
    b'"currency_code":"USD","currency_registry_version":'
    b'"synthetic-iso-style-currency-registry/v1","currency_scale":2},'
    b'"status":"PLACED_VALUE_VERIFIED"},"workflow_state":'
    b'"CREDIT_CONFIRMED_TARGET_REP"}'
)
EXPECTED_MANAGER_CANONICAL = (
    b'{"active_note":"synthetic: manager working note","actor":'
    b'"SYN-REP-MANAGER-000001","approved_amount":null,"controlled_reason":'
    b'"OTHER_KNOWN_REP","decided_at":"2026-08-22T16:00:00Z",'
    b'"occurrence_id":"SYN-EVIDENCE-MANAGER-000001","outcome":"DENIED",'
    b'"recorded_at":"2026-08-22T16:05:00Z","schema_version":'
    b'"synthetic-sales-credit-domain/v1"}'
)
EXPECTED_CLOSED_CANONICAL = (
    b'{"approved_amount":null,"attribution":"OTHER_REP","closed_at":'
    b'"2026-08-22T16:00:00Z","concise_note":"HUMAN_OUTCOME_RECORDED",'
    b'"controlled_reason":"OTHER_KNOWN_REP",'
    b'"decision_actor":"SYN-REP-MANAGER-000001","evidence_classifications":['
    b'"INBOUND_EVIDENCE_HUMAN_REVIEW"],"evidence_source_types":['
    b'"SYNTHETIC_EMAIL"],"human_decided_at":"2026-08-22T15:55:00Z",'
    b'"human_outcome":"DENIED","human_recorded_at":"2026-08-22T16:00:00Z",'
    b'"interaction_precisions":["CORRECTED","EXACT"],"opened_at":'
    b'"2026-08-20T16:00:00Z","order_id":"SYN-ORDER-000001",'
    b'"order_value_status":"PLACED_VALUE_VERIFIED","reasons":['
    b'"OTHER_KNOWN_REP"],"retention_policy_version":'
    b'"sales-credit-retention-elapsed-90d/v1","rule_pack_version":'
    b'"synthetic-sales-credit-rules/v1","schema_version":'
    b'"synthetic-sales-credit-domain/v1","system_workflow_before_close":'
    b'"OTHER_REP_HUMAN_REVIEW"}'
)


class CanonicalSalesCreditPreimageTests(unittest.TestCase):
    def _assert_binding(
        self,
        value: object,
        expected_domain: str,
        expected_canonical: bytes,
        expected_sha256: str,
    ) -> None:
        canonical = value.canonical_bytes()  # type: ignore[attr-defined]
        binding = value.hash_binding()  # type: ignore[attr-defined]
        self.assertEqual(canonical, expected_canonical)
        self.assertEqual(binding.domain, expected_domain)
        self.assertEqual(binding.sha256, expected_sha256)
        self.assertEqual(binding.canonical_bytes, canonical)
        self.assertEqual(
            binding.preimage,
            expected_domain.encode("ascii") + b"\n" + expected_canonical,
        )

    def test_evaluation_binding_uses_exact_domain_lf_and_canonical_json(self) -> None:
        self._assert_binding(
            valid_evaluation(),
            SalesCreditEvaluation.HASH_DOMAIN,
            EXPECTED_EVALUATION_CANONICAL,
            "f052b54929b0055dda929fb9e488da8dd41430956861e92a2333a5f9880ccba3",
        )

    def test_manager_binding_uses_exact_domain_lf_and_canonical_json(self) -> None:
        self._assert_binding(
            valid_manager(),
            ManagerOutcome.HASH_DOMAIN,
            EXPECTED_MANAGER_CANONICAL,
            "90f9965bd52923f31b938b39fa4735e5c13c7c4f85dc110ed1b192f06400c4b4",
        )

    def test_closed_binding_uses_exact_domain_lf_and_canonical_json(self) -> None:
        self._assert_binding(
            valid_closed(),
            ClosedAuditRecord.HASH_DOMAIN,
            EXPECTED_CLOSED_CANONICAL,
            "a66835db90d1304d0c1734f90b0c1261497ab67b52770f0af3eed1023d493e23",
        )
