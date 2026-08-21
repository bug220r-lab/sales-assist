from __future__ import annotations

import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from unittest.mock import patch
from zoneinfo import ZoneInfoNotFoundError

from synthetic_sales_assist.doi.identities import DoiOrderId
from synthetic_sales_assist.doi.interventions import (
    DOIIntervention,
    SystemExactValueRecord,
    ValueCorrectionKind,
    ValueEvent,
    append_resulting_link_revision,
    append_value_event,
    record_verified_intervention,
)
from synthetic_sales_assist.doi.models import (
    ActionVerificationState,
    CaseLifecycleState,
    InterventionType,
    TerminalClosureReason,
    ValueEventType,
)
from synthetic_sales_assist.doi.retention import (
    DOI_RETENTION_POLICY_VERSION,
    DOI_TIMEZONE_DATABASE_BINDING,
    DOICaseGraph,
    DoiRetentionError,
    IdentityRetentionKind,
    IdentityRetentionState,
    InMemoryDoiRetentionState,
    KPIContributionHistory,
    NonidentifyingKPIBucket,
    PurgeResult,
    RETENTION_HASH_KNOWN_ANSWERS,
    RetainedKPIContribution,
    VerifiedCurrencyEnvelope,
    build_retained_kpi_contribution,
    business_action_date,
    calendar90,
    cancel_retention_on_reopen,
    finalize_case_purge,
    finalize_identity_purge,
    retention_hash_contracts,
    retention_hash_fixtures,
    reduce_kpi_contribution,
    schedule_retention,
    schedule_identity_retention,
)
from synthetic_sales_assist.doi.source import source_hash_fixture_records
from synthetic_sales_assist.domain.canonical import canonical_json_bytes, domain_hash
from synthetic_sales_assist.domain.identities import (
    EvidenceId,
    OrderId,
)
from synthetic_sales_assist.domain.numeric import (
    CURRENCY_REGISTRY_VERSION,
    Money,
)
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp
from tests.test_doi_interventions import (
    NOW as INTERVENTION_NOW,
    _action as _verified_action,
    _completed_context_for,
    _mapping,
    _order_source as _intervention_order_source,
    _revision,
    _value_event,
)


NOW = CanonicalTimestamp("2026-08-20T12:00:00Z")


def _money(cents: int, currency: str = "USD") -> Money:
    scale = 0 if currency == "JPY" else 2
    return Money.from_minor_units(
        cents,
        currency_code=currency,
        registry_version=CURRENCY_REGISTRY_VERSION,
        scale=scale,
    )


def _binding(domain: str, marker: str):  # type: ignore[no-untyped-def]
    value = {"marker": marker}
    return domain_hash(domain, canonical_json_bytes(value, expected_members=set(value)))


def _intervention(
    intervention_type: InterventionType,
    *,
    verified_cents: int | None,
    action_at: CanonicalTimestamp | None = NOW,
    currency: str = "USD",
    suffix: str = "DEFAULT",
    verification: ActionVerificationState = ActionVerificationState.SYSTEM_VERIFIED,
):
    intervention_id = EvidenceId(f"SYN-EVIDENCE-KPI-INTERVENTION-{suffix}")
    action = _verified_action(
        verification=verification,
        event_id=f"SYN-EVIDENCE-KPI-ACTION-EVENT-{suffix}",
        evidence_id=f"SYN-EVIDENCE-KPI-ACTION-PROOF-{suffix}",
        key_id=f"SYN-EVIDENCE-KPI-ACTION-KEY-{suffix}",
        intervention_type=intervention_type,
        marker=suffix,
        occurred_at=action_at,
        intervention_id=intervention_id,
    )
    intervention = record_verified_intervention(None, action).intervention
    if verified_cents is None or intervention_type is InterventionType.DS_SEPARATION:
        return intervention
    context = _completed_context_for(intervention, marker=suffix)
    record = SystemExactValueRecord.from_order_observation(
        record_id=EvidenceId(f"SYN-EVIDENCE-KPI-VALUE-OCCURRENCE-{suffix}"),
        intervention=intervention,
        completed_action_context=context,
        event_type=ValueEventType.INITIAL_VERIFIED_VALUE,
        amount=_money(verified_cents, currency),
        predecessor_event=None,
        correction_kind=None,
        observed_at=INTERVENTION_NOW,
        source=_intervention_order_source(
            context.order_id,
            f"KPI-VALUE-{suffix}",
        ),
    )
    value = ValueEvent.from_system_record(
        event_id=EvidenceId(f"SYN-EVIDENCE-KPI-VALUE-EVENT-{suffix}"),
        key_id=EvidenceId(f"SYN-EVIDENCE-KPI-VALUE-KEY-{suffix}"),
        record=record,
    )
    return append_value_event(intervention, value).intervention


def _link(
    intervention: DOIIntervention,
    *,
    order_rep_verified: bool,
    line_rep_verified: bool,
    suffix: str = "DEFAULT",
):
    link_id = EvidenceId(f"SYN-EVIDENCE-KPI-LINK-{suffix}")
    child = DoiOrderId(OrderId(f"SYN-ORDER-KPI-CHILD-{suffix}"))
    evidence = _revision(
        revision_id=f"SYN-EVIDENCE-KPI-LINK-REVISION-{suffix}",
        mappings=_mapping(
            intervention=intervention,
            link_id=link_id,
            child=child,
            rep_verified=line_rep_verified,
            marker=suffix,
        ),
        predecessor=None,
        intervention=intervention,
        link_id=link_id,
        child=child,
        rep_verified=order_rep_verified,
        marker=suffix,
    )
    return append_resulting_link_revision(
        None,
        revision_id=EvidenceId(f"SYN-EVIDENCE-KPI-LINK-REVISION-{suffix}"),
        intervention=intervention,
        evidence=evidence,
    ).link


def _currency_envelope(
    intervention: DOIIntervention,
    *,
    suffix: str,
    currency: str = "USD",
) -> VerifiedCurrencyEnvelope:
    context = _completed_context_for(intervention, marker=suffix)
    return VerifiedCurrencyEnvelope.from_order_observation(
        evidence_id=EvidenceId(f"SYN-EVIDENCE-KPI-CURRENCY-{suffix}"),
        intervention=intervention,
        completed_action_context=context,
        currency_code=currency,
        registry_version=CURRENCY_REGISTRY_VERSION,
        scale=0 if currency == "JPY" else 2,
        observed_at=INTERVENTION_NOW,
        source=_intervention_order_source(
            context.order_id,
            f"KPI-CURRENCY-{suffix}",
        ),
    )


def _contribution(
    cents: int,
    *,
    currency: str = "USD",
    suffix: str = "DEFAULT",
) -> RetainedKPIContribution:
    intervention = _intervention(
        InterventionType.PRODUCT_SUBSTITUTION,
        verified_cents=cents,
        currency=currency,
        suffix=suffix,
    )
    decision = build_retained_kpi_contribution(
        intervention,
        event_id=EvidenceId(f"SYN-EVIDENCE-KPI-CONTRIBUTION-{suffix}"),
        resulting_link=_link(
            intervention,
            order_rep_verified=False,
            line_rep_verified=True,
            suffix=suffix,
        ),
    )
    if decision.contribution is None:
        raise AssertionError("test contribution must be retained")
    return decision.contribution


def _retention(case_id: EvidenceId, closed_at: CanonicalTimestamp = NOW):
    return schedule_retention(
        case_id=case_id,
        closure_event_id=EvidenceId("SYN-EVIDENCE-CLOSURE-EVENT"),
        lifecycle_state=CaseLifecycleState.CLOSED_REVERSIBLE,
        closure_reason=TerminalClosureReason.REP_TRANSFERRED,
        closed_at=closed_at,
        projection_revision=1,
        projection_sha256="a" * 64,
    )


class TestDoiRetention(unittest.TestCase):
    def test_calendar90_preserves_local_wall_time_across_offset_change(self) -> None:
        closed = CanonicalTimestamp("2026-01-15T15:30:00Z")
        self.assertEqual(calendar90(closed).value, "2026-04-15T14:30:00Z")

    def test_calendar90_spring_gap_uses_first_valid_instant(self) -> None:
        closed = CanonicalTimestamp("2025-12-08T07:30:00Z")
        self.assertEqual(calendar90(closed).value, "2026-03-08T07:00:00Z")

    def test_calendar90_fall_overlap_uses_later_occurrence(self) -> None:
        closed = CanonicalTimestamp("2026-08-03T05:30:00Z")
        self.assertEqual(calendar90(closed).value, "2026-11-01T06:30:00Z")

    def test_retention_binds_policy_timezone_and_exact_deadline(self) -> None:
        projection = _retention(EvidenceId("SYN-EVIDENCE-CASE-RETENTION"))
        self.assertEqual(projection.binding.retention_policy_version, DOI_RETENTION_POLICY_VERSION)
        self.assertEqual(
            projection.binding.timezone_database_binding,
            DOI_TIMEZONE_DATABASE_BINDING,
        )
        self.assertEqual(projection.purge_eligible_at, calendar90(NOW))
        self.assertEqual(
            tuple(reason.code for reason in projection.reasons.reasons),
            ("RC-079",),
        )

    def test_reversible_reopen_requires_byte_equal_prior_binding(self) -> None:
        projection = _retention(EvidenceId("SYN-EVIDENCE-CASE-REOPEN"))
        canceled = cancel_retention_on_reopen(
            projection,
            supplied_binding=projection.binding,
            reopen_event_id=EvidenceId("SYN-EVIDENCE-REOPEN-EVENT"),
        )
        self.assertIsNone(canceled.purge_eligible_at)
        self.assertEqual(
            tuple(reason.code for reason in canceled.reasons.reasons),
            ("RC-078", "RC-080"),
        )
        changed = replace(projection.binding, projection_sha256="b" * 64)
        with self.assertRaisesRegex(
            DoiRetentionError,
            "PRIOR_CLOSURE_BINDING_MISMATCH",
        ) as caught:
            cancel_retention_on_reopen(
                projection,
                supplied_binding=changed,
                reopen_event_id=EvidenceId("SYN-EVIDENCE-REOPEN-CHANGED"),
            )
        self.assertEqual(
            tuple(reason.code for reason in caught.exception.reasons.reasons),
            ("RC-113",),
        )

    def test_hard_closure_never_reopens(self) -> None:
        projection = schedule_retention(
            case_id=EvidenceId("SYN-EVIDENCE-HARD-CASE"),
            closure_event_id=EvidenceId("SYN-EVIDENCE-HARD-CLOSURE"),
            lifecycle_state=CaseLifecycleState.CLOSED_HARD,
            closure_reason=TerminalClosureReason.SHIPPED,
            closed_at=NOW,
            projection_revision=1,
            projection_sha256="c" * 64,
        )
        with self.assertRaisesRegex(DoiRetentionError, "HARD_CLOSURE_CANNOT_REOPEN"):
            cancel_retention_on_reopen(
                projection,
                supplied_binding=projection.binding,
                reopen_event_id=EvidenceId("SYN-EVIDENCE-HARD-REOPEN"),
            )

    def test_verified_substitution_contributes_once_on_new_york_action_date(self) -> None:
        intervention = _intervention(
            InterventionType.PRODUCT_SUBSTITUTION,
            verified_cents=12_345,
        )
        link = _link(
            intervention,
            order_rep_verified=False,
            line_rep_verified=True,
        )
        decision = build_retained_kpi_contribution(
            intervention,
            event_id=EvidenceId("SYN-EVIDENCE-KPI-CONTRIBUTION-DEFAULT"),
            resulting_link=link,
        )
        self.assertIsNotNone(decision.contribution)
        assert decision.contribution is not None
        self.assertEqual(decision.contribution.current_value, _money(12_345))
        self.assertEqual(decision.contribution.intervention_count, 1)
        self.assertEqual(decision.contribution.action_date, business_action_date(NOW))
        self.assertEqual(
            decision.contribution.action_occurred_at,
            intervention.action_occurred_at,
        )
        self.assertEqual(
            decision.contribution.intervention_action_binding,
            intervention.action_events[0].hash_binding(),
        )
        self.assertEqual(
            decision.contribution.resulting_link_binding,
            link.hash_binding(),
        )
        self.assertEqual(decision.reasons.reasons, ())

    def test_kpi_history_reduces_correction_reversal_and_replay_exactly_once(self) -> None:
        suffix = "VALUE-HISTORY"
        intervention = _intervention(
            InterventionType.PRODUCT_SUBSTITUTION,
            verified_cents=10_000,
            suffix=suffix,
        )
        link = _link(
            intervention,
            order_rep_verified=False,
            line_rep_verified=True,
            suffix=suffix,
        )
        first = build_retained_kpi_contribution(
            intervention,
            event_id=EvidenceId("SYN-EVIDENCE-KPI-HISTORY-001"),
            resulting_link=link,
        )
        assert first.history is not None
        original = intervention.value_events[-1]
        correction = _value_event(
            intervention=intervention,
            event_id="SYN-EVIDENCE-KPI-VALUE-CORRECTION",
            event_type=ValueEventType.CORRECTION,
            cents=9_000,
            predecessor=original,
            correction_kind=ValueCorrectionKind.ORIGINAL_VALUE_CORRECTED,
            marker=suffix,
        )
        corrected = append_value_event(intervention, correction).intervention
        second = reduce_kpi_contribution(
            first.history,
            event_id=EvidenceId("SYN-EVIDENCE-KPI-HISTORY-002"),
            intervention=corrected,
            resulting_link=link,
        )
        assert second.contribution is not None and second.history is not None
        self.assertEqual(second.contribution.current_value, _money(9_000))
        self.assertEqual(second.contribution.intervention_count, 1)
        self.assertEqual(second.contribution.revision, 2)

        replay = reduce_kpi_contribution(
            second.history,
            event_id=EvidenceId("SYN-EVIDENCE-KPI-HISTORY-002"),
            intervention=corrected,
            resulting_link=link,
        )
        self.assertTrue(replay.replayed)
        self.assertEqual(len(replay.history.events), 2)

        reversal = _value_event(
            intervention=corrected,
            event_id="SYN-EVIDENCE-KPI-VALUE-REVERSAL",
            event_type=ValueEventType.PARTIAL_REVERSAL,
            cents=2_000,
            predecessor=correction,
            marker=suffix,
        )
        reversed_intervention = append_value_event(corrected, reversal).intervention
        third = reduce_kpi_contribution(
            second.history,
            event_id=EvidenceId("SYN-EVIDENCE-KPI-HISTORY-003"),
            intervention=reversed_intervention,
            resulting_link=link,
        )
        assert third.contribution is not None and third.history is not None
        self.assertEqual(third.contribution.current_value, _money(7_000))
        self.assertEqual(third.contribution.intervention_count, 1)
        self.assertEqual(third.contribution.revision, 3)

        void = _value_event(
            intervention=reversed_intervention,
            event_id="SYN-EVIDENCE-KPI-VALUE-REVERSAL-VOID",
            event_type=ValueEventType.CORRECTION,
            cents=0,
            predecessor=reversal,
            correction_kind=ValueCorrectionKind.REVERSAL_VOIDED,
            marker=suffix,
        )
        restored_intervention = append_value_event(
            reversed_intervention,
            void,
        ).intervention
        fourth = reduce_kpi_contribution(
            third.history,
            event_id=EvidenceId("SYN-EVIDENCE-KPI-HISTORY-004"),
            intervention=restored_intervention,
            resulting_link=link,
        )
        assert fourth.contribution is not None
        self.assertEqual(fourth.contribution.current_value, _money(9_000))
        self.assertEqual(fourth.contribution.intervention_count, 1)
        self.assertEqual(fourth.contribution.revision, 4)

        with self.assertRaisesRegex(DoiRetentionError, "KPI_VALUE_HISTORY_GAP") as gap:
            reduce_kpi_contribution(
                KPIContributionHistory(
                    intervention_id=restored_intervention.intervention_id,
                    intervention_type=restored_intervention.intervention_type,
                ),
                event_id=EvidenceId("SYN-EVIDENCE-KPI-HISTORY-GAP"),
                intervention=restored_intervention,
                resulting_link=link,
            )
        self.assertEqual(
            tuple(reason.code for reason in gap.exception.reasons.reasons),
            ("RC-111",),
        )

    def test_kpi_rejects_cross_intervention_link_and_direct_contribution_forgery(self) -> None:
        first = _intervention(
            InterventionType.PRODUCT_SUBSTITUTION,
            verified_cents=1_000,
            suffix="BINDING-A",
        )
        second = _intervention(
            InterventionType.PRODUCT_SUBSTITUTION,
            verified_cents=1_000,
            suffix="BINDING-B",
        )
        link = _link(
            first,
            order_rep_verified=False,
            line_rep_verified=True,
            suffix="BINDING-A",
        )
        with self.assertRaisesRegex(
            DoiRetentionError,
            "KPI_RESULTING_LINK_BINDING_INVALID",
        ) as raised:
            build_retained_kpi_contribution(
                second,
                event_id=EvidenceId("SYN-EVIDENCE-KPI-CONTRIBUTION-CROSS"),
                resulting_link=link,
            )
        self.assertEqual(
            tuple(reason.code for reason in raised.exception.reasons.reasons),
            ("RC-081",),
        )
        with self.assertRaisesRegex(DoiRetentionError, "REDUCER_REQUIRED"):
            RetainedKPIContribution()

    def test_split_rep_proof_is_resulting_order_scoped(self) -> None:
        intervention = _intervention(InterventionType.FULFILLMENT_SPLIT, verified_cents=5_000)
        link = _link(
            intervention,
            order_rep_verified=False,
            line_rep_verified=True,
        )
        decision = build_retained_kpi_contribution(
            intervention,
            event_id=EvidenceId("SYN-EVIDENCE-KPI-CONTRIBUTION-SPLIT"),
            resulting_link=link,
        )
        self.assertIsNotNone(decision.contribution)
        assert decision.contribution is not None
        self.assertEqual(decision.contribution.current_value, _money(0))
        self.assertEqual(tuple(reason.code for reason in decision.reasons.reasons), ("RC-074",))
        substitution = _intervention(
            InterventionType.PRODUCT_SUBSTITUTION,
            verified_cents=5_000,
            suffix="SUB-REP-SCOPE",
        )
        substitution_decision = build_retained_kpi_contribution(
            substitution,
            event_id=EvidenceId("SYN-EVIDENCE-KPI-CONTRIBUTION-SUB-SCOPE"),
            resulting_link=_link(
                substitution,
                order_rep_verified=True,
                line_rep_verified=False,
                suffix="SUB-REP-SCOPE",
            ),
        )
        self.assertEqual(
            tuple(reason.code for reason in substitution_decision.reasons.reasons),
            ("RC-075",),
        )

    def test_unverified_value_is_zero_and_action_date_unavailable_has_no_row(self) -> None:
        intervention = _intervention(
            InterventionType.PRODUCT_SUBSTITUTION,
            verified_cents=None,
        )
        link = _link(
            intervention,
            order_rep_verified=False,
            line_rep_verified=True,
        )
        zero = build_retained_kpi_contribution(
            intervention,
            event_id=EvidenceId("SYN-EVIDENCE-KPI-CONTRIBUTION-UNVERIFIED"),
            currency_evidence=_currency_envelope(
                intervention,
                suffix="DEFAULT",
            ),
            resulting_link=link,
        )
        self.assertIsNotNone(zero.contribution)
        self.assertEqual(tuple(reason.code for reason in zero.reasons.reasons), ("RC-063",))
        no_date_intervention = _intervention(
            InterventionType.PRODUCT_SUBSTITUTION,
            verified_cents=None,
            action_at=None,
            suffix="NO-DATE",
        )
        no_date = build_retained_kpi_contribution(
            no_date_intervention,
            event_id=EvidenceId("SYN-EVIDENCE-KPI-CONTRIBUTION-NO-DATE"),
            currency_evidence=_currency_envelope(
                no_date_intervention,
                suffix="NO-DATE",
            ),
            resulting_link=_link(
                no_date_intervention,
                order_rep_verified=False,
                line_rep_verified=True,
                suffix="NO-DATE",
            ),
        )
        self.assertIsNone(no_date.contribution)
        self.assertEqual(
            tuple(reason.code for reason in no_date.reasons.reasons),
            ("RC-063", "RC-099"),
        )
        human_no_date_intervention = _intervention(
            InterventionType.PRODUCT_SUBSTITUTION,
            verified_cents=None,
            action_at=None,
            suffix="HUMAN-NO-DATE",
            verification=ActionVerificationState.HUMAN_VERIFIED,
        )
        human_no_date = build_retained_kpi_contribution(
            human_no_date_intervention,
            event_id=EvidenceId("SYN-EVIDENCE-KPI-CONTRIBUTION-HUMAN-NO-DATE"),
            currency_evidence=_currency_envelope(
                human_no_date_intervention,
                suffix="HUMAN-NO-DATE",
            ),
            resulting_link=_link(
                human_no_date_intervention,
                order_rep_verified=False,
                line_rep_verified=True,
                suffix="HUMAN-NO-DATE",
            ),
        )
        self.assertIsNone(human_no_date.contribution)
        self.assertEqual(
            tuple(reason.code for reason in human_no_date.reasons.reasons),
            ("RC-063", "RC-099"),
        )

    def test_ds_separation_has_exact_empty_kpi_history_and_no_row(self) -> None:
        intervention = _intervention(
            InterventionType.DS_SEPARATION,
            verified_cents=None,
            suffix="DS-NO-ROW",
        )
        decision = build_retained_kpi_contribution(
            intervention,
            event_id=EvidenceId("SYN-EVIDENCE-KPI-CONTRIBUTION-DS-NO-ROW"),
        )
        self.assertIsNone(decision.contribution)
        self.assertIsNone(decision.event)
        self.assertEqual(decision.reasons.to_json_value(), [])
        self.assertEqual(
            decision.history,
            KPIContributionHistory(
                intervention_id=intervention.intervention_id,
                intervention_type=InterventionType.DS_SEPARATION,
            ),
        )
        replay = reduce_kpi_contribution(
            decision.history,
            event_id=EvidenceId("SYN-EVIDENCE-KPI-CONTRIBUTION-DS-REPLAY"),
            intervention=intervention,
            resulting_link=None,
        )
        self.assertIsNone(replay.contribution)
        self.assertIsNone(replay.event)
        self.assertEqual(replay.history, decision.history)
        self.assertEqual(replay.history.events, ())

    def test_atomic_purge_finalizes_bucket_and_leaves_no_drillthrough_identity(self) -> None:
        case_id = EvidenceId("SYN-EVIDENCE-PURGE-CASE")
        contribution = _contribution(4_321, suffix="PURGE")
        graph = DOICaseGraph(
            case_id=case_id,
            order_id=DoiOrderId(OrderId("SYN-ORDER-PURGE-001")),
            identity_nodes=(EvidenceId("SYN-EVIDENCE-PURGE-LINK"),),
            retention=_retention(case_id),
            contribution=contribution,
        )
        state = InMemoryDoiRetentionState()
        state.retain(graph)
        result = state.purge(
            case_id,
            now=calendar90(NOW),
            expected_contribution=contribution,
        )
        self.assertTrue(result.graph_deleted)
        self.assertEqual(
            tuple(reason.code for reason in result.reasons.reasons),
            ("RC-086", "RC-088"),
        )
        self.assertIsNone(state.graph(case_id))
        self.assertEqual(state.identity_graph_count, 0)
        self.assertEqual(len(state.buckets), 1)
        bucket_bytes = state.buckets[0].canonical_bytes()
        for prohibited in (b"SYN-ORDER-", b"SYN-EVIDENCE-", b"case_id", b"link"):
            self.assertNotIn(prohibited, bucket_bytes)
        bucket_count = len(state.buckets)
        replay = state.purge(
            case_id,
            now=calendar90(NOW),
            expected_contribution=contribution,
        )
        self.assertFalse(replay.graph_deleted)
        self.assertTrue(replay.absence_noop)
        self.assertEqual(replay.removed_identity_count, 0)
        self.assertEqual(len(state.buckets), bucket_count)

    def test_reconciliation_mismatch_and_fault_roll_back_transfer_and_delete(self) -> None:
        case_id = EvidenceId("SYN-EVIDENCE-ROLLBACK-CASE")
        contribution = _contribution(1_000, suffix="ROLLBACK")
        graph = DOICaseGraph(
            case_id=case_id,
            order_id=DoiOrderId(OrderId("SYN-ORDER-ROLLBACK")),
            identity_nodes=(),
            retention=_retention(case_id),
            contribution=contribution,
        )
        state = InMemoryDoiRetentionState()
        state.retain(graph)
        with self.assertRaisesRegex(
            DoiRetentionError,
            "KPI_FINALIZATION_CONFLICT",
        ) as mismatch:
            state.purge(case_id, now=calendar90(NOW), expected_contribution=None)
        self.assertEqual(
            tuple(reason.code for reason in mismatch.exception.reasons.reasons),
            ("RC-101",),
        )
        self.assertEqual(state.graph(case_id), graph)
        self.assertEqual(state.buckets, ())

        def fail(_: object) -> None:
            raise RuntimeError("injected")

        with self.assertRaisesRegex(RuntimeError, "injected"):
            state.purge(
                case_id,
                now=calendar90(NOW),
                expected_contribution=contribution,
                fault_injector=fail,
            )
        self.assertEqual(state.graph(case_id), graph)
        self.assertEqual(state.buckets, ())

    def test_concurrent_purge_replay_finalizes_exactly_once_then_absence_noops(self) -> None:
        case_id = EvidenceId("SYN-EVIDENCE-CONCURRENT-PURGE-CASE")
        contribution = _contribution(2_500, suffix="CONCURRENT-PURGE")
        state = InMemoryDoiRetentionState()
        state.retain(
            DOICaseGraph(
                case_id=case_id,
                order_id=DoiOrderId(OrderId("SYN-ORDER-CONCURRENT-PURGE")),
                identity_nodes=(),
                retention=_retention(case_id),
                contribution=contribution,
            )
        )

        def purge_once() -> PurgeResult:
            return state.purge(
                case_id,
                now=calendar90(NOW),
                expected_contribution=contribution,
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = tuple(executor.map(lambda _: purge_once(), range(2)))
        self.assertEqual(sum(result.graph_deleted for result in results), 1)
        self.assertEqual(sum(result.absence_noop for result in results), 1)
        self.assertEqual(len(state.buckets), 1)
        self.assertEqual(state.buckets[0].current_value, contribution.current_value)

    def test_mixed_currencies_remain_separate_buckets(self) -> None:
        state = InMemoryDoiRetentionState()
        for suffix, currency in (("USD", "USD"), ("JPY", "JPY")):
            case_id = EvidenceId(f"SYN-EVIDENCE-CURRENCY-CASE-{suffix}")
            contribution = _contribution(
                100,
                currency=currency,
                suffix=f"CURRENCY-{suffix}",
            )
            state.retain(
                DOICaseGraph(
                    case_id=case_id,
                    order_id=DoiOrderId(OrderId(f"SYN-ORDER-CURRENCY-{suffix}")),
                    identity_nodes=(),
                    retention=_retention(case_id),
                    contribution=contribution,
                )
            )
            state.purge(
                case_id,
                now=calendar90(NOW),
                expected_contribution=contribution,
            )
        self.assertEqual(len(state.buckets), 2)
        self.assertEqual(
            {bucket.current_value.currency_code for bucket in state.buckets},
            {"JPY", "USD"},
        )

    def test_finalization_function_rejects_mixed_bucket_identity(self) -> None:
        case_id = EvidenceId("SYN-EVIDENCE-MIXED-CONFLICT-CASE")
        contribution = _contribution(100, currency="USD", suffix="MIXED-CONFLICT")
        graph = DOICaseGraph(
            case_id=case_id,
            order_id=DoiOrderId(OrderId("SYN-ORDER-MIXED-CONFLICT")),
            identity_nodes=(),
            retention=_retention(case_id),
            contribution=contribution,
        )
        wrong = NonidentifyingKPIBucket(
            action_date=contribution.action_date,
            intervention_type=contribution.intervention_type,
            current_value=_money(100, "JPY"),
            intervention_count=1,
        )
        with self.assertRaisesRegex(
            DoiRetentionError,
            "KPI_BUCKET_IDENTITY_CONFLICT",
        ) as mismatch:
            finalize_case_purge(
                graph,
                now=calendar90(NOW),
                existing_bucket=wrong,
                expected_contribution=contribution,
            )
        self.assertEqual(
            tuple(reason.code for reason in mismatch.exception.reasons.reasons),
            ("RC-100",),
        )

    def test_noncase_identity_schedule_and_transaction_local_purge_reasons(self) -> None:
        fixture_bindings = {
            name: domain_hash(domain, canonical)
            for name, domain, canonical, _ in source_hash_fixture_records()
        }
        cases = (
            (
                IdentityRetentionKind.REJECTED_SOURCE_RECORD,
                fixture_bindings["DOIRejectedSourceRecord"],
                ("RC-092",),
                ("RC-093",),
            ),
            (
                IdentityRetentionKind.SOURCE_IMPORT_ATTEMPT,
                fixture_bindings["DOISourceImportAttempt"],
                (),
                ("RC-114",),
            ),
        )
        for kind, binding, scheduled_reasons, purge_reasons in cases:
            with self.subTest(kind=kind.value):
                scheduled = schedule_identity_retention(
                    kind=kind,
                    identity_binding=binding,
                    run_completed_at=NOW,
                )
                self.assertIs(scheduled.state, IdentityRetentionState.SCHEDULED)
                self.assertEqual(
                    tuple(
                        reason.code
                        for reason in scheduled.transaction_reasons.reasons
                    ),
                    scheduled_reasons,
                )
                purged = finalize_identity_purge(
                    scheduled,
                    now=scheduled.purge_eligible_at,
                )
                self.assertIs(purged.state, IdentityRetentionState.PURGED)
                self.assertIsNone(purged.retained_identity_binding)
                self.assertEqual(
                    tuple(reason.code for reason in purged.transaction_reasons.reasons),
                    purge_reasons,
                )

    def test_retention_clock_failure_emits_rc096(self) -> None:
        with patch(
            "synthetic_sales_assist.doi.retention.ZoneInfo",
            side_effect=ZoneInfoNotFoundError,
        ), self.assertRaisesRegex(
            DoiRetentionError,
            "RETENTION_TIMEZONE_UNAVAILABLE",
        ) as raised:
            calendar90(NOW)
        self.assertEqual(
            tuple(reason.code for reason in raised.exception.reasons.reasons),
            ("RC-096",),
        )

    def test_retention_hash_inventory_has_only_expected_survivor_domain(self) -> None:
        contracts = retention_hash_contracts()
        self.assertEqual(len(contracts), 5)
        self.assertEqual(
            contracts["NonidentifyingKPIBucket"],
            "doi-nonidentifying-kpi-bucket/v1",
        )

    def test_hash_fixtures_cover_every_retention_hash_record(self) -> None:
        fixtures = retention_hash_fixtures()
        self.assertEqual(
            {name for name, _, _, _ in fixtures},
            set(retention_hash_contracts()),
        )
        self.assertEqual(len(fixtures), 5)
        self.assertEqual(
            {name: digest for name, _, _, digest in fixtures},
            dict(RETENTION_HASH_KNOWN_ANSWERS),
        )
        for _, domain, canonical_bytes, digest in fixtures:
            self.assertEqual(domain_hash(domain, canonical_bytes).sha256, digest)


if __name__ == "__main__":
    unittest.main()
