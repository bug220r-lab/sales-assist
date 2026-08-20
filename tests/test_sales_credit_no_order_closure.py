from __future__ import annotations

import hashlib
import json
import unittest
from dataclasses import FrozenInstanceError, fields, replace
from datetime import date
from unittest.mock import patch

import synthetic_sales_assist.sales_credit.discovery as discovery_module
from synthetic_sales_assist.domain.identities import (
    EvaluationId,
    EvidenceId,
    InteractionId,
    OrderId,
    RunId,
    SnapshotId,
)
from synthetic_sales_assist.domain.records import VersionBinding
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp
from synthetic_sales_assist.sales_credit.discovery import (
    CandidateInteractionDisposition,
    IdentifierSearchResult,
    InMemoryNoOrderStateLedger,
    InMemorySearchRunAuthority,
    InteractionSearchDisposition,
    ManualDiscoveryTransitionResult,
    NoOrderLedgerError,
    NoOrderTransitionResult,
    OrderSearchRun,
    PostEvaluationCommitResult,
    SearchCompleteness,
    SearchRunOwnerPartition,
    SearchRunPartitionKind,
    SelectorOwnedCandidateEvaluation,
    plan_discovery,
)
from synthetic_sales_assist.sales_credit.evaluator import (
    KNOWN_OTHER_REP_CATALOG,
    evaluate_sales_credit,
)
from synthetic_sales_assist.sales_credit.fixtures import milestone2_case_mutation
from synthetic_sales_assist.sales_credit.models import (
    ClosedNoteCode,
    InteractionRecord,
    SalesCreditReason,
    SearchTriggerType,
    TimestampPrecision,
    WorkflowState,
)
from synthetic_sales_assist.sales_credit.retention import (
    NoOrderClosedAuditRecord,
    NoOrderClosureResult,
    NoOrderClosureProjection,
    RetentionDecisionError,
    build_no_order_closure_projection,
    purge_eligible,
)


NO_ORDER_CANONICAL_JSON = (
    '{"closed_at":"2026-08-17T16:00:00.000000001Z","concise_note":"REVIEW_WINDOW_'
    'CLOSED_NO_ORDER","enumeration_complete":true,"identifiers_attempted":2,"identifiers_'
    'completed":2,"identifiers_required":2,"interaction_count":2,"interaction_precisions"'
    ':["EXACT","HISTORICAL_APPROXIMATION"],"latest_review_window_end":"2026-08-16","'
    'opened_at":"2026-08-01T14:00:00Z","reasons":["NO_ORDER_WINDOW_CLOSED"],"retention_'
    'policy_version":"sales-credit-retention-elapsed-90d/v1","rule_pack_version":"'
    'synthetic-sales-credit-rules/v1","schema_version":"sales-credit-no-order-closed-audit/'
    'v1","search_adapter_version":"sales-credit-search-adapter/v1","search_run_schema_'
    'version":"sales-credit-order-search-run/v1","search_trigger":"NORMAL","system_'
    'workflow_before_close":"REVIEW_WINDOW_CLOSED_NO_ORDER"}'
)
NO_ORDER_SHA256 = "76e433cc36bafc21b6c0128445afde4c8f41a17d53bcde3d1c853d2b6d0004a3"


def ts(value: str) -> CanonicalTimestamp:
    return CanonicalTimestamp(value)


def no_order_ledger() -> InMemoryNoOrderStateLedger:
    return InMemoryNoOrderStateLedger(
        search_run_authority=InMemorySearchRunAuthority()
    )


def interaction(
    index: int,
    *,
    email: str | None = None,
    phone: str | None = None,
    recorded_at: str,
    review_window_start: date,
    precision: TimestampPrecision,
) -> InteractionRecord:
    return InteractionRecord(
        interaction_id=InteractionId(f"SYN-INTERACTION-NO-ORDER-{index:04d}"),
        source_ref=EvidenceId(f"SYN-EVIDENCE-NO-ORDER-SOURCE-{index:04d}"),
        recorded_at=ts(recorded_at),
        timestamp_precision=precision,
        review_window_start=review_window_start,
        review_window_end=date.fromordinal(review_window_start.toordinal() + 14),
        workflow_state=WorkflowState.AWAITING_SOURCE_REVIEW,
        provenance=VersionBinding(
            "sales_credit_interaction_source",
            "sales-credit-interaction-source/v1",
        ),
        email=email,
        phone=phone,
        vin_like_reference=f"synthetic: VIN-LIKE-CANARY-{index}",
        part_request=f"synthetic: PART-CANARY-{index}",
        active_notes=f"synthetic: ACTIVE-NOTE-CANARY-{index}",
    )


def terminal_run(*, identity_variant: int = 0) -> OrderSearchRun:
    email = (
        "closed.no.order@example.test"
        if identity_variant == 0
        else "alternate.closed@example.test"
    )
    phone = "212-555-0198" if identity_variant == 0 else "646-555-0197"
    interactions = (
        interaction(
            1 + identity_variant * 10,
            email=email,
            recorded_at="2026-08-01T14:00:00Z",
            review_window_start=date(2026, 8, 1),
            precision=TimestampPrecision.EXACT,
        ),
        interaction(
            2 + identity_variant * 10,
            phone=phone,
            recorded_at="2026-08-02T15:00:00Z",
            review_window_start=date(2026, 8, 2),
            precision=TimestampPrecision.HISTORICAL_APPROXIMATION,
        ),
    )
    plan = plan_discovery(
        email_values=(email,),
        phone_values=(phone,),
    )
    return OrderSearchRun(
        run_id=RunId(f"SYN-RUN-NO-ORDER-{identity_variant + 1:04d}"),
        trigger=SearchTriggerType.NORMAL,
        interactions=interactions,
        native_result_sets=tuple(
            IdentifierSearchResult(
                identifier=identifier,
                completeness=SearchCompleteness.COMPLETE,
                order_ids=(),
            )
            for identifier in plan.identifiers
        ),
        adapter=VersionBinding(
            "sales_credit_search_adapter",
            OrderSearchRun.ADAPTER_VERSION,
        ),
        started_at=ts("2026-08-17T15:59:59.999999999Z"),
        completed_at=ts("2026-08-17T16:00:00.000000001Z"),
        warnings=("SYNTHETIC_RUN_WARNING",),
    )


def terminal_closure(*, identity_variant: int = 0) -> NoOrderClosureResult:
    result = no_order_ledger().apply_run(
        terminal_run(identity_variant=identity_variant)
    )
    if type(result) is not NoOrderClosureResult:
        raise AssertionError("terminal run did not produce a minimized closure")
    return result


def run_with_outcome(
    *,
    completed_at: str,
    completeness: SearchCompleteness = SearchCompleteness.COMPLETE,
) -> OrderSearchRun:
    interactions = (
        interaction(
            31,
            email="outcome.branch@example.test",
            recorded_at="2026-08-01T14:00:00Z",
            review_window_start=date(2026, 8, 1),
            precision=TimestampPrecision.EXACT,
        ),
    )
    plan = plan_discovery(email_values=(interactions[0].email,))
    return OrderSearchRun(
        run_id=RunId("SYN-RUN-NO-ORDER-BRANCH-0001"),
        trigger=SearchTriggerType.NORMAL,
        interactions=interactions,
        native_result_sets=(
            IdentifierSearchResult(
                identifier=plan.identifiers[0],
                completeness=completeness,
                order_ids=(),
            ),
        ),
        adapter=VersionBinding(
            "sales_credit_search_adapter",
            OrderSearchRun.ADAPTER_VERSION,
        ),
        started_at=ts(completed_at),
        completed_at=ts(completed_at),
    )


class NoOrderClosureProjectionTests(unittest.TestCase):
    def test_terminal_run_derives_the_identity_free_minimized_root(self) -> None:
        run = terminal_run()
        closure = no_order_ledger().apply_run(run)
        self.assertIs(type(closure), NoOrderClosureResult)
        projection = closure.projection  # type: ignore[union-attr]
        record = projection.record

        self.assertEqual(
            (
                projection.interactions_removed,
                projection.identifiers_removed,
                projection.native_result_sets_removed,
            ),
            (2, 2, 2),
        )
        self.assertEqual(record.opened_at, ts("2026-08-01T14:00:00Z"))
        self.assertEqual(record.closed_at, run.completed_at)
        self.assertEqual(record.latest_review_window_end, date(2026, 8, 16))
        self.assertEqual(record.interaction_count, 2)
        self.assertEqual(
            record.interaction_precisions,
            (
                TimestampPrecision.EXACT,
                TimestampPrecision.HISTORICAL_APPROXIMATION,
            ),
        )
        self.assertIs(
            record.system_workflow_before_close,
            WorkflowState.REVIEW_WINDOW_CLOSED_NO_ORDER,
        )
        self.assertEqual(record.reasons, (SalesCreditReason.NO_ORDER_WINDOW_CLOSED,))
        self.assertIs(
            record.concise_note,
            ClosedNoteCode.REVIEW_WINDOW_CLOSED_NO_ORDER,
        )
        self.assertNotIn("order_id", {item.name for item in fields(record)})
        self.assertFalse(hasattr(record, "order_id"))

    def test_canonical_survivor_excludes_every_run_and_interaction_identity(self) -> None:
        run = terminal_run()
        record = terminal_closure().projection.record
        serialized = record.canonical_bytes().decode("utf-8")
        prohibited = (
            run.run_id.value,
            *(item.interaction_id.value for item in run.interactions),
            *(item.source_ref.value for item in run.interactions),
            *(item.email for item in run.interactions if item.email is not None),
            *(item.phone for item in run.interactions if item.phone is not None),
            *(item.vin_like_reference for item in run.interactions),
            *(item.part_request for item in run.interactions),
            *(item.active_notes for item in run.interactions),
            *(item.value for item in run.attempted_identifiers),
            *run.warnings,
        )
        for canary in prohibited:
            with self.subTest(canary=canary):
                self.assertNotIn(canary, serialized)

        decoded = json.loads(serialized)
        self.assertFalse(
            {
                "order_id",
                "run_id",
                "interaction_ids",
                "contacts",
                "email",
                "phone",
                "source_ref",
                "warnings",
                "force_explanation",
                "notes",
            }
            & set(decoded)
        )

    def test_hash_is_deterministic_and_independent_of_removed_identity(self) -> None:
        first = terminal_closure().projection.record
        identity_variant = terminal_closure(identity_variant=1).projection.record
        self.assertEqual(first.canonical_bytes(), identity_variant.canonical_bytes())
        self.assertEqual(first.hash_binding(), identity_variant.hash_binding())
        binding = first.hash_binding()
        self.assertEqual(binding.domain, NoOrderClosedAuditRecord.HASH_DOMAIN)
        self.assertEqual(binding.canonical_bytes, first.canonical_bytes())
        self.assertEqual(
            binding.sha256,
            hashlib.sha256(binding.preimage).hexdigest(),
        )

    def test_exact_known_answer_preimage_and_digest(self) -> None:
        record = terminal_closure().projection.record
        canonical = NO_ORDER_CANONICAL_JSON.encode("utf-8")
        independently_encoded = json.dumps(
            json.loads(NO_ORDER_CANONICAL_JSON),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        self.assertEqual(independently_encoded, canonical)
        self.assertEqual(record.canonical_bytes(), canonical)
        expected_preimage = (
            NoOrderClosedAuditRecord.HASH_DOMAIN.encode("ascii") + b"\n" + canonical
        )
        self.assertEqual(expected_preimage.count(b"\n"), 1)
        self.assertEqual(record.hash_binding().preimage, expected_preimage)
        self.assertEqual(hashlib.sha256(expected_preimage).hexdigest(), NO_ORDER_SHA256)
        self.assertEqual(record.hash_binding().sha256, NO_ORDER_SHA256)

    def test_nonterminal_and_incomplete_runs_cannot_close(self) -> None:
        active = run_with_outcome(completed_at="2026-08-10T16:00:00Z")
        incomplete = run_with_outcome(
            completed_at="2026-08-16T16:00:00Z",
            completeness=SearchCompleteness.INCOMPLETE,
        )
        active_transition = no_order_ledger().apply_run(active)
        with self.assertRaisesRegex(
            RetentionDecisionError,
            "no_order_transition_type",
        ):
            build_no_order_closure_projection(transition=active_transition)
        with self.assertRaisesRegex(
            NoOrderLedgerError,
            "no_order_result_not_complete_empty",
        ):
            no_order_ledger().apply_run(incomplete)

    def test_active_transition_capability_cannot_mint_a_terminal_projection(
        self,
    ) -> None:
        active = no_order_ledger().apply_run(
            run_with_outcome(completed_at="2026-08-10T16:00:00Z")
        )
        self.assertIs(type(active), NoOrderTransitionResult)
        with self.assertRaisesRegex(
            RetentionDecisionError,
            "no_order_transition_type",
        ):
            build_no_order_closure_projection(transition=active)
        public_fields = {item.name for item in fields(active)}
        self.assertTrue(
            public_fields.isdisjoint(
                {"run", "interactions", "_commit_capability", "_committing_ledger"}
            )
        )

        self.assertFalse(
            hasattr(discovery_module, "_NO_ORDER_LEDGER_COMMIT_CAPABILITY")
        )

    def test_derived_run_material_must_match_the_exact_factual_run(self) -> None:
        forged = terminal_run()
        object.__setattr__(forged, "attempted_identifiers", ())
        with self.assertRaisesRegex(
            NoOrderLedgerError,
            "no_order_run_derived_material",
        ):
            no_order_ledger().apply_run(forged)
        with self.assertRaisesRegex(
            RetentionDecisionError,
            "no_order_transition_type",
        ):
            build_no_order_closure_projection(  # type: ignore[arg-type]
                transition=object()
            )

    def test_record_and_projection_are_closed_strictly_typed_values(self) -> None:
        projection = terminal_closure().projection
        record = projection.record
        invalid_records = (
            ("system_workflow_before_close", WorkflowState.CHECKED_NO_ORDER_WINDOW_ACTIVE),
            ("reasons", (SalesCreditReason.NO_ORDER_WINDOW_ACTIVE,)),
            ("concise_note", ClosedNoteCode.AUTOMATIC_CLASSIFICATION_CLOSED),
            ("enumeration_complete", False),
            ("identifiers_completed", 1),
            ("interaction_count", True),
            ("latest_review_window_end", date(2026, 8, 17)),
            ("search_adapter_version", "closed.no.order@example.test"),
        )
        for member, value in invalid_records:
            with self.subTest(member=member):
                with self.assertRaises(RetentionDecisionError) as raised:
                    replace(record, **{member: value})
                self.assertNotIn("closed.no.order@example.test", str(raised.exception))

        with self.assertRaisesRegex(
            RetentionDecisionError,
            "no_order_projection_count",
        ):
            replace(projection, interactions_removed=True)
        with self.assertRaisesRegex(
            RetentionDecisionError,
            "no_order_closure_result_receipt",
        ):
            replace(terminal_closure(), receipt_id="SYN-RUN-NO-ORDER-0001")
        with self.assertRaises(FrozenInstanceError):
            projection.interactions_removed = 0  # type: ignore[misc]
        self.assertEqual(repr(record), "NoOrderClosedAuditRecord(<minimized>)")

    def test_exact_ninety_elapsed_day_purge_boundary_uses_run_completion(self) -> None:
        record = terminal_closure().projection.record
        self.assertFalse(
            purge_eligible(
                closed_at=record.closed_at,
                now=ts("2026-11-15T16:00:00Z"),
            )
        )
        self.assertTrue(
            purge_eligible(
                closed_at=record.closed_at,
                now=ts("2026-11-15T16:00:00.000000001Z"),
            )
        )

    def test_terminal_apply_removes_contact_state_and_keeps_only_minimized_replay(self) -> None:
        authority = InMemorySearchRunAuthority()
        ledger = InMemoryNoOrderStateLedger(search_run_authority=authority)
        base = terminal_run()
        active_run = replace(
            base,
            run_id=RunId("SYN-RUN-NO-ORDER-ACTIVE-0001"),
            started_at=ts("2026-08-10T16:00:00Z"),
            completed_at=ts("2026-08-10T16:00:01Z"),
        )
        active = ledger.apply_run(active_run)
        self.assertIs(type(active), NoOrderTransitionResult)
        self.assertEqual(ledger.active_receipt_count, 1)
        self.assertIn(
            b"closed.no.order@example.test",
            ledger.retained_active_replay_material[0],
        )
        self.assertIn(
            b"closed.no.order@example.test",
            authority.retained_canonical_material[0],
        )

        terminal = replace(
            base,
            run_id=RunId("SYN-RUN-NO-ORDER-TERMINAL-0001"),
            trigger=SearchTriggerType.AUTOMATIC_RECHECK,
            interactions=ledger.retained_interactions,
        )
        closed = ledger.apply_run(terminal)
        self.assertIs(type(closed), NoOrderClosureResult)
        self.assertEqual(ledger.retained_interactions, ())
        self.assertEqual(ledger.retained_active_replay_material, ())
        self.assertEqual(ledger.active_receipt_count, 0)
        self.assertEqual(ledger.closure_receipt_count, 1)
        self.assertEqual(ledger.receipt_count, 1)
        self.assertEqual(authority.retained_canonical_material, ())
        self.assertEqual(
            authority.retired_run_ids,
            (
                active_run.run_id,
                terminal.run_id,
            ),
        )

        minimized = closed.projection.record.canonical_bytes()  # type: ignore[union-attr]
        for interaction_value in base.interactions:
            self.assertNotIn(interaction_value.interaction_id.value.encode(), minimized)
            self.assertNotIn(interaction_value.source_ref.value.encode(), minimized)
            if interaction_value.email is not None:
                self.assertNotIn(interaction_value.email.encode(), minimized)
            if interaction_value.phone is not None:
                self.assertNotIn(interaction_value.phone.encode(), minimized)

        command_replay = ledger.apply_run(terminal)
        self.assertIs(type(command_replay), NoOrderClosureResult)
        self.assertTrue(command_replay.replayed)  # type: ignore[union-attr]
        self.assertEqual(
            command_replay.receipt_id,  # type: ignore[union-attr]
            closed.receipt_id,  # type: ignore[union-attr]
        )
        self.assertEqual(
            command_replay.projection,  # type: ignore[union-attr]
            closed.projection,  # type: ignore[union-attr]
        )
        with self.assertRaisesRegex(
            NoOrderLedgerError,
            "no_order_run_replay_conflict",
        ):
            ledger.apply_run(
                replace(terminal, warnings=("CHANGED_MATERIAL",))
            )
        replay = ledger.replay_closure(closed)
        self.assertIs(type(replay), NoOrderClosureResult)
        self.assertTrue(replay.replayed)  # type: ignore[union-attr]
        self.assertEqual(
            replay.projection,  # type: ignore[union-attr]
            closed.projection,  # type: ignore[union-attr]
        )
        self.assertEqual(ledger.retained_interactions, ())
        self.assertEqual(ledger.retained_active_replay_material, ())

        active_replay = ledger.apply_run(active_run)
        self.assertIs(type(active_replay), NoOrderTransitionResult)
        self.assertTrue(active_replay.replayed)  # type: ignore[union-attr]
        self.assertFalse(hasattr(active_replay, "interactions"))
        duplicate_ledger = no_order_ledger()
        first_duplicate = duplicate_ledger.apply_run(terminal_run())
        distinct_closed = duplicate_ledger.apply_run(
            terminal_run(identity_variant=1)
        )
        self.assertIs(type(distinct_closed), NoOrderClosureResult)
        self.assertNotEqual(
            first_duplicate.receipt_id,  # type: ignore[union-attr]
            distinct_closed.receipt_id,  # type: ignore[union-attr]
        )
        self.assertEqual(
            first_duplicate.projection,  # type: ignore[union-attr]
            distinct_closed.projection,  # type: ignore[union-attr]
        )
        distinct_replay = duplicate_ledger.replay_closure(distinct_closed)
        self.assertTrue(distinct_replay.replayed)  # type: ignore[union-attr]
        self.assertEqual(ledger.retained_interactions, ())
        self.assertEqual(authority.retained_canonical_material, ())
        self.assertEqual(duplicate_ledger.closure_receipt_count, 2)

    def test_terminal_projection_failure_rolls_back_state_and_receipts(self) -> None:
        ledger = no_order_ledger()
        base = terminal_run()
        active_run = replace(
            base,
            run_id=RunId("SYN-RUN-NO-ORDER-ROLLBACK-ACTIVE"),
            started_at=ts("2026-08-10T16:00:00Z"),
            completed_at=ts("2026-08-10T16:00:01Z"),
        )
        active = ledger.apply_run(active_run)
        terminal = replace(
            base,
            run_id=RunId("SYN-RUN-NO-ORDER-ROLLBACK-CLOSED"),
            trigger=SearchTriggerType.AUTOMATIC_RECHECK,
            interactions=ledger.retained_interactions,
        )
        before_interactions = ledger.retained_interactions
        before_replay = ledger.retained_active_replay_material
        before_counts = (
            ledger.active_receipt_count,
            ledger.closure_receipt_count,
        )
        with patch(
            "synthetic_sales_assist.sales_credit.retention."
            "build_no_order_closure_projection",
            side_effect=RetentionDecisionError("synthetic_projection_failure"),
        ):
            with self.assertRaisesRegex(
                NoOrderLedgerError,
                "no_order_closure_projection_failed",
            ):
                ledger.apply_run(terminal)

        self.assertEqual(ledger.retained_interactions, before_interactions)
        self.assertEqual(ledger.retained_active_replay_material, before_replay)
        self.assertEqual(
            (ledger.active_receipt_count, ledger.closure_receipt_count),
            before_counts,
        )
        retry = ledger.apply_run(terminal)
        self.assertIs(type(retry), NoOrderClosureResult)
        self.assertEqual(ledger.retained_interactions, ())

    def test_minimized_closure_receipt_purges_at_exact_ninety_elapsed_days(self) -> None:
        authority = InMemorySearchRunAuthority()
        ledger = InMemoryNoOrderStateLedger(search_run_authority=authority)
        run = terminal_run()
        closed = ledger.apply_run(run)
        self.assertIs(type(closed), NoOrderClosureResult)
        self.assertEqual(ledger.closure_receipt_count, 1)
        self.assertEqual(authority.retained_canonical_material, ())
        self.assertEqual(authority.retired_run_ids, (terminal_run().run_id,))
        self.assertEqual(
            ledger.purge_closed(now=ts("2026-11-15T16:00:00Z")),
            0,
        )
        boundary_replay = ledger.apply_run(run)
        self.assertIs(type(boundary_replay), NoOrderClosureResult)
        self.assertTrue(boundary_replay.replayed)  # type: ignore[union-attr]
        self.assertEqual(ledger.closure_receipt_count, 1)
        self.assertEqual(
            ledger.purge_closed(now=ts("2026-11-15T16:00:00.000000001Z")),
            1,
        )
        self.assertEqual(ledger.closure_receipt_count, 0)
        self.assertEqual(authority.retired_run_ids, ())
        self.assertEqual(
            ledger.purge_closed(now=ts("2026-11-15T16:00:00.000000002Z")),
            0,
        )
        with self.assertRaisesRegex(
            NoOrderLedgerError,
            "no_order_closure_replay_missing",
        ):
            ledger.replay_closure(closed)
        with self.assertRaisesRegex(
            NoOrderLedgerError,
            "no_order_purge_timestamp",
        ):
            ledger.purge_closed(now="2026-11-15T16:00:00Z")  # type: ignore[arg-type]


class PostEvaluationNoOrderReducerTests(unittest.TestCase):
    def _all_nonqualifying_run(
        self,
    ) -> tuple[
        OrderSearchRun,
        tuple[SelectorOwnedCandidateEvaluation, ...],
    ]:
        shared_email = "all.nonqualifying@example.test"
        interactions = (
            interaction(
                201,
                email=shared_email,
                recorded_at="2026-08-01T16:00:00Z",
                review_window_start=date(2026, 8, 1),
                precision=TimestampPrecision.EXACT,
            ),
            interaction(
                202,
                email=shared_email,
                recorded_at="2026-08-20T16:00:00Z",
                review_window_start=date(2026, 8, 20),
                precision=TimestampPrecision.EXACT,
            ),
        )
        mutation = milestone2_case_mutation()
        snapshot = replace(
            mutation.snapshots[0],
            placed_at=ts("2026-07-31T16:00:00Z"),
        )
        plan = plan_discovery(email_values=(shared_email,))
        run = OrderSearchRun(
            run_id=RunId("SYN-RUN-POST-EVALUATION-MIXED-WINDOW-0001"),
            trigger=SearchTriggerType.NORMAL,
            interactions=interactions,
            native_result_sets=(
                IdentifierSearchResult(
                    identifier=plan.identifiers[0],
                    completeness=SearchCompleteness.COMPLETE,
                    order_ids=(mutation.order_id,),
                ),
            ),
            adapter=VersionBinding(
                "sales_credit_search_adapter",
                OrderSearchRun.ADAPTER_VERSION,
            ),
            started_at=ts("2026-08-23T16:00:00Z"),
            completed_at=ts("2026-08-23T16:00:01Z"),
        )
        evaluations = tuple(
            SelectorOwnedCandidateEvaluation(
                interaction_id=scoped.interaction_id,
                snapshot=snapshot,
                evaluated_at=run.completed_at,
                evaluation=evaluate_sales_credit(
                    evaluation_id=EvaluationId(
                        f"SYN-EVALUATION-ALL-NONQUALIFYING-{index:04d}"
                    ),
                    expected_order_id=mutation.order_id,
                    snapshot=snapshot,
                    evaluated_at=run.completed_at,
                    known_other_reps=KNOWN_OTHER_REP_CATALOG,
                    interactions=(scoped,),
                ),
            )
            for index, scoped in enumerate(interactions, start=1)
        )
        return run, evaluations

    def _shared_candidate_run(
        self,
        *,
        completeness: SearchCompleteness = SearchCompleteness.COMPLETE,
        started_at: str = "2026-08-23T16:00:00Z",
        completed_at: str = "2026-08-23T16:00:01Z",
        run_id: str = "SYN-RUN-POST-EVALUATION-0001",
    ) -> tuple[
        OrderSearchRun,
        tuple[SelectorOwnedCandidateEvaluation, ...],
    ]:
        shared_email = "selector.shared@example.test"
        first = interaction(
            101,
            email=shared_email,
            recorded_at="2026-08-20T16:00:00Z",
            review_window_start=date(2026, 8, 20),
            precision=TimestampPrecision.EXACT,
        )
        second = interaction(
            102,
            email=shared_email,
            recorded_at="2026-08-22T16:00:00Z",
            review_window_start=date(2026, 8, 22),
            precision=TimestampPrecision.EXACT,
        )
        mutation = milestone2_case_mutation()
        snapshot = mutation.snapshots[0]
        order_id = mutation.order_id
        plan = plan_discovery(email_values=(shared_email,))
        run = OrderSearchRun(
            run_id=RunId(run_id),
            trigger=SearchTriggerType.NORMAL,
            interactions=(first, second),
            native_result_sets=(
                IdentifierSearchResult(
                    identifier=plan.identifiers[0],
                    completeness=completeness,
                    order_ids=(order_id,),
                ),
            ),
            adapter=VersionBinding(
                "sales_credit_search_adapter",
                OrderSearchRun.ADAPTER_VERSION,
            ),
            started_at=ts(started_at),
            completed_at=ts(completed_at),
        )
        evaluated_at = ts(completed_at)
        candidate_evaluations = tuple(
            SelectorOwnedCandidateEvaluation(
                interaction_id=scoped.interaction_id,
                snapshot=snapshot,
                evaluated_at=evaluated_at,
                evaluation=evaluate_sales_credit(
                    evaluation_id=EvaluationId(
                        f"SYN-EVALUATION-POST-SCOPE-{index:04d}"
                    ),
                    expected_order_id=order_id,
                    snapshot=snapshot,
                    evaluated_at=evaluated_at,
                    known_other_reps=KNOWN_OTHER_REP_CATALOG,
                    interactions=(scoped,),
                ),
            )
            for index, scoped in enumerate(run.interactions, start=1)
        )
        return run, candidate_evaluations

    def _stage_and_seal(
        self,
        *,
        ledger: InMemoryNoOrderStateLedger,
        authority: InMemorySearchRunAuthority,
        run: OrderSearchRun,
        evaluations: tuple[SelectorOwnedCandidateEvaluation, ...],
    ) -> tuple[object, object, object, object]:
        coordinator_owner = authority.new_owner()
        claim = authority.claim(run, owner=coordinator_owner)
        stage = ledger.stage_post_evaluation_run(
            run,
            evaluations,
            authority_claim=claim,
        )
        has_case_scope = any(
            scope.positive_interaction_ids or scope.preserved_interaction_ids
            for scope in stage.candidate_scopes
        )
        partitions: tuple[SearchRunOwnerPartition, ...] = ()
        if has_case_scope:
            partitions = (
                authority.new_partition(
                    owner=coordinator_owner,
                    kind=SearchRunPartitionKind.POSITIVE_CASE_ACTIVE,
                ),
            )
        if stage.required_partition is not None:
            partitions = (*partitions, stage.required_partition)
        seal = authority.seal_run((claim,), partitions=partitions)
        return coordinator_owner, claim, stage, seal

    def test_shared_identifier_scope_attaches_only_qualifying_interaction(self) -> None:
        authority = InMemorySearchRunAuthority()
        ledger = InMemoryNoOrderStateLedger(
            search_run_authority=authority,
            coordinator_required=True,
        )
        run, evaluations = self._shared_candidate_run()
        owner, _, stage, seal = self._stage_and_seal(
            ledger=ledger,
            authority=authority,
            run=run,
            evaluations=evaluations,
        )

        self.assertEqual(len(stage.candidate_scopes), 1)
        scope = stage.candidate_scopes[0]
        self.assertEqual(
            scope.positive_interaction_ids,
            (run.interactions[0].interaction_id,),
        )
        self.assertEqual(scope.preserved_interaction_ids, ())
        self.assertEqual(
            scope.nonqualifying_interaction_ids,
            (run.interactions[1].interaction_id,),
        )
        self.assertIsNotNone(stage.required_partition)
        self.assertIs(
            stage.required_partition.kind,  # type: ignore[union-attr]
            SearchRunPartitionKind.NO_ORDER_ACTIVE,
        )
        self.assertEqual(
            tuple(result.disposition for result in stage.interaction_results),
            (
                InteractionSearchDisposition.POSITIVE_CANDIDATE,
                InteractionSearchDisposition.NO_ORDER_WINDOW_ACTIVE,
            ),
        )

        result = ledger.commit_post_evaluation_stage(stage, seal=seal)
        self.assertIs(type(result), PostEvaluationCommitResult)
        self.assertEqual(len(result.active_no_order), 1)
        self.assertEqual(result.manual_review, ())
        self.assertEqual(result.terminal_no_order, ())
        authority.commit_seal(seal)
        ledger.finalize_post_evaluation_stage(stage)

        self.assertEqual(authority.retained_canonical_material, ())
        self.assertEqual(authority.sealed_run_ids, (run.run_id,))
        self.assertEqual(
            tuple(item.interaction_id for item in ledger.retained_interactions),
            (run.interactions[1].interaction_id,),
        )
        self.assertIs(
            ledger.retained_interactions[0].workflow_state,
            WorkflowState.CHECKED_NO_ORDER_WINDOW_ACTIVE,
        )
        exact_claim = authority.claim(run, owner=owner)
        replay_stage = ledger.stage_post_evaluation_run(
            run,
            evaluations,
            authority_claim=exact_claim,
        )
        self.assertIsNone(replay_stage.required_partition)
        replay = ledger.commit_post_evaluation_stage(replay_stage, seal=None)
        self.assertTrue(replay.replayed)

        changed_evaluations = (
            replace(
                evaluations[0],
                evaluation=replace(
                    evaluations[0].evaluation,
                    evaluation_id=EvaluationId(
                        "SYN-EVALUATION-POST-SCOPE-CHANGED-0001"
                    ),
                ),
            ),
            evaluations[1],
        )
        with self.assertRaisesRegex(
            NoOrderLedgerError,
            "post_evaluation_replay_conflict",
        ):
            ledger.stage_post_evaluation_run(
                run,
                changed_evaluations,
                authority_claim=exact_claim,
            )

    def test_terminal_nonqualifying_root_closes_independently(self) -> None:
        authority = InMemorySearchRunAuthority()
        ledger = InMemoryNoOrderStateLedger(
            search_run_authority=authority,
            coordinator_required=True,
        )
        run, evaluations = self._shared_candidate_run(
            started_at="2026-09-06T16:00:00Z",
            completed_at="2026-09-06T16:00:01Z",
            run_id="SYN-RUN-POST-EVALUATION-CLOSED-0001",
        )
        _, _, stage, seal = self._stage_and_seal(
            ledger=ledger,
            authority=authority,
            run=run,
            evaluations=evaluations,
        )
        self.assertIs(
            stage.required_partition.kind,  # type: ignore[union-attr]
            SearchRunPartitionKind.NO_ORDER_MINIMIZED,
        )
        result = ledger.commit_post_evaluation_stage(stage, seal=seal)
        authority.commit_seal(seal)
        ledger.finalize_post_evaluation_stage(stage)

        self.assertEqual(result.active_no_order, ())
        self.assertEqual(result.manual_review, ())
        self.assertEqual(len(result.terminal_no_order), 1)
        closure = result.terminal_no_order[0]
        self.assertIs(type(closure), NoOrderClosureResult)
        self.assertEqual(
            closure.projection.record.interaction_count,  # type: ignore[attr-defined]
            1,
        )
        self.assertEqual(
            closure.projection.record.opened_at,  # type: ignore[attr-defined]
            run.interactions[1].effective_at,
        )
        self.assertEqual(ledger.retained_interactions, ())
        self.assertEqual(authority.retained_canonical_material, ())
        rendered = repr(result) + repr(closure)
        self.assertNotIn("selector.shared@example.test", rendered)
        self.assertNotIn(run.interactions[1].interaction_id.value, rendered)

    def test_all_terminal_candidate_snapshot_is_erased_but_replay_stays_bound(
        self,
    ) -> None:
        authority = InMemorySearchRunAuthority()
        ledger = InMemoryNoOrderStateLedger(
            search_run_authority=authority,
            coordinator_required=True,
        )
        mixed_run, mixed_evaluations = self._all_nonqualifying_run()
        root = mixed_run.interactions[0]
        run = OrderSearchRun(
            run_id=RunId("SYN-RUN-POST-EVALUATION-ALL-TERMINAL-0001"),
            trigger=SearchTriggerType.NORMAL,
            interactions=(root,),
            native_result_sets=mixed_run.native_result_sets,
            adapter=mixed_run.adapter,
            started_at=mixed_run.started_at,
            completed_at=mixed_run.completed_at,
        )
        evaluation = mixed_evaluations[0]
        _, _, stage, seal = self._stage_and_seal(
            ledger=ledger,
            authority=authority,
            run=run,
            evaluations=(evaluation,),
        )
        committed = ledger.commit_post_evaluation_stage(stage, seal=seal)
        authority.commit_seal(seal)
        ledger.finalize_post_evaluation_stage(stage)
        self.assertEqual(len(committed.terminal_no_order), 1)
        self.assertEqual(ledger.retained_interactions, ())
        self.assertEqual(ledger.retained_snapshot_count, 0)
        self.assertEqual(authority.retained_canonical_material, ())

        replay_stage = ledger.stage_post_evaluation_run(run, (evaluation,))
        replay = ledger.commit_post_evaluation_stage(replay_stage, seal=None)
        self.assertTrue(replay.replayed)
        changed = replace(
            evaluation,
            evaluation=replace(
                evaluation.evaluation,
                evaluation_id=EvaluationId(
                    "SYN-EVALUATION-ALL-TERMINAL-CHANGED-0001"
                ),
            ),
        )
        with self.assertRaisesRegex(
            NoOrderLedgerError,
            "post_evaluation_replay_conflict",
        ):
            ledger.stage_post_evaluation_run(run, (changed,))
        self.assertEqual(ledger.retained_snapshot_count, 0)

    def test_mixed_terminal_active_roots_purge_at_each_exact_boundary(self) -> None:
        authority = InMemorySearchRunAuthority()
        ledger = InMemoryNoOrderStateLedger(
            search_run_authority=authority,
            coordinator_required=True,
        )
        first_run, first_evaluations = self._all_nonqualifying_run()
        first_owner, _, first_stage, first_seal = self._stage_and_seal(
            ledger=ledger,
            authority=authority,
            run=first_run,
            evaluations=first_evaluations,
        )
        first_scope = first_stage.candidate_scopes[0]
        self.assertEqual(first_scope.positive_interaction_ids, ())
        self.assertEqual(first_scope.preserved_interaction_ids, ())
        self.assertEqual(
            first_scope.nonqualifying_interaction_ids,
            first_run.interaction_ids,
        )
        self.assertEqual(
            tuple(result.disposition for result in first_stage.interaction_results),
            (
                InteractionSearchDisposition.NO_ORDER_WINDOW_CLOSED,
                InteractionSearchDisposition.NO_ORDER_WINDOW_ACTIVE,
            ),
        )
        first_result = ledger.commit_post_evaluation_stage(
            first_stage,
            seal=first_seal,
        )
        authority.commit_seal(first_seal)
        ledger.finalize_post_evaluation_stage(first_stage)
        self.assertEqual(len(first_result.terminal_no_order), 1)
        self.assertEqual(len(first_result.active_no_order), 1)
        self.assertEqual(
            tuple(item.interaction_id for item in ledger.retained_interactions),
            (first_run.interactions[1].interaction_id,),
        )

        active_interaction = ledger.retained_interactions[0]
        plan = plan_discovery(email_values=(active_interaction.email,))
        second_run = OrderSearchRun(
            run_id=RunId("SYN-RUN-POST-EVALUATION-MIXED-WINDOW-0002"),
            trigger=SearchTriggerType.AUTOMATIC_RECHECK,
            interactions=(active_interaction,),
            native_result_sets=(
                IdentifierSearchResult(
                    identifier=plan.identifiers[0],
                    completeness=SearchCompleteness.COMPLETE,
                    order_ids=(first_evaluations[0].evaluation.order_id,),
                ),
            ),
            adapter=VersionBinding(
                "sales_credit_search_adapter",
                OrderSearchRun.ADAPTER_VERSION,
            ),
            started_at=ts("2026-09-04T16:00:00Z"),
            completed_at=ts("2026-09-04T16:00:01Z"),
        )
        second_evaluation = SelectorOwnedCandidateEvaluation(
            interaction_id=active_interaction.interaction_id,
            snapshot=first_evaluations[0].snapshot,
            evaluated_at=second_run.completed_at,
            evaluation=evaluate_sales_credit(
                evaluation_id=EvaluationId(
                    "SYN-EVALUATION-ALL-NONQUALIFYING-RECHECK-0001"
                ),
                expected_order_id=first_evaluations[0].evaluation.order_id,
                snapshot=first_evaluations[0].snapshot,
                evaluated_at=second_run.completed_at,
                known_other_reps=KNOWN_OTHER_REP_CATALOG,
                interactions=(active_interaction,),
            ),
        )
        second_owner, _, second_stage, second_seal = self._stage_and_seal(
            ledger=ledger,
            authority=authority,
            run=second_run,
            evaluations=(second_evaluation,),
        )
        second_result = ledger.commit_post_evaluation_stage(
            second_stage,
            seal=second_seal,
        )
        authority.commit_seal(second_seal)
        ledger.finalize_post_evaluation_stage(second_stage)
        self.assertEqual(len(second_result.terminal_no_order), 1)
        self.assertEqual(ledger.retained_interactions, ())

        self.assertEqual(
            ledger.purge_closed(now=ts("2026-11-21T16:00:00Z")),
            0,
        )
        self.assertEqual(
            ledger.purge_closed(now=ts("2026-11-21T16:00:01Z")),
            1,
        )
        replay_stage = ledger.stage_post_evaluation_run(
            first_run,
            first_evaluations,
        )
        replay = ledger.commit_post_evaluation_stage(replay_stage, seal=None)
        self.assertTrue(replay.replayed)
        self.assertEqual(replay.terminal_no_order, ())
        self.assertEqual(len(replay.active_no_order), 1)
        self.assertEqual(
            authority.sealed_run_ids,
            (first_run.run_id, second_run.run_id),
        )
        self.assertEqual(
            ledger.purge_closed(now=ts("2026-12-03T16:00:00Z")),
            0,
        )
        self.assertEqual(
            ledger.purge_closed(now=ts("2026-12-03T16:00:01Z")),
            1,
        )
        self.assertEqual(authority.sealed_run_ids, ())

    def test_incomplete_enumeration_applies_governed_manual_state(self) -> None:
        authority = InMemorySearchRunAuthority()
        ledger = InMemoryNoOrderStateLedger(
            search_run_authority=authority,
            coordinator_required=True,
        )
        run, evaluations = self._shared_candidate_run(
            completeness=SearchCompleteness.INCOMPLETE,
            run_id="SYN-RUN-POST-EVALUATION-INCOMPLETE-0001",
        )
        _, _, stage, seal = self._stage_and_seal(
            ledger=ledger,
            authority=authority,
            run=run,
            evaluations=evaluations,
        )
        self.assertTrue(stage.candidate_scopes[0].positive_interaction_ids)
        self.assertEqual(
            tuple(result.disposition for result in stage.interaction_results),
            (
                InteractionSearchDisposition.MANUAL_REVIEW_REQUIRED,
                InteractionSearchDisposition.MANUAL_REVIEW_REQUIRED,
            ),
        )
        committed = ledger.commit_post_evaluation_stage(stage, seal=seal)
        authority.commit_seal(seal)
        ledger.finalize_post_evaluation_stage(stage)

        self.assertEqual(len(committed.manual_review), 2)
        self.assertTrue(
            all(
                result.reasons
                == (SalesCreditReason.IDENTIFIER_SEARCH_INCOMPLETE,)
                for result in committed.manual_review
            )
        )
        self.assertEqual(
            tuple(item.workflow_state for item in ledger.retained_interactions),
            (
                WorkflowState.MANUAL_REVIEW_REQUIRED,
                WorkflowState.MANUAL_REVIEW_REQUIRED,
            ),
        )
        self.assertEqual(authority.retained_canonical_material, ())

    def test_identifierless_manual_transition_is_applied_and_replay_safe(self) -> None:
        ledger = no_order_ledger()
        root = interaction(
            151,
            recorded_at="2026-08-20T16:00:00Z",
            review_window_start=date(2026, 8, 20),
            precision=TimestampPrecision.EXACT,
        )
        decided_at = ts("2026-08-20T17:00:00Z")
        result = ledger.apply_manual_interaction(root, decided_at=decided_at)
        self.assertIs(type(result), ManualDiscoveryTransitionResult)
        self.assertEqual(
            result.reasons,
            (SalesCreditReason.NO_USABLE_SEARCH_IDENTIFIER,),
        )
        self.assertIs(
            ledger.retained_interactions[0].workflow_state,
            WorkflowState.MANUAL_REVIEW_REQUIRED,
        )
        self.assertIsNone(ledger.retained_interactions[0].last_check_at)
        replay = ledger.apply_manual_interaction(root, decided_at=decided_at)
        self.assertTrue(replay.replayed)
        with self.assertRaisesRegex(
            NoOrderLedgerError,
            "manual_interaction_replay_conflict",
        ):
            ledger.apply_manual_interaction(
                root,
                decided_at=ts("2026-08-20T17:00:01Z"),
            )
        rendered = repr(result)
        self.assertNotIn(root.interaction_id.value, rendered)
        self.assertNotIn("PART-CANARY", rendered)

    def test_coordinated_mode_closes_direct_legacy_entrypoints(self) -> None:
        authority = InMemorySearchRunAuthority()
        coordinated = InMemoryNoOrderStateLedger(
            search_run_authority=authority,
            coordinator_required=True,
        )
        run, _ = self._shared_candidate_run(
            run_id="SYN-RUN-COORDINATOR-GUARD-0001"
        )
        with self.assertRaisesRegex(
            NoOrderLedgerError,
            "no_order_coordinator_required",
        ):
            coordinated.apply_run(run)

        standalone = InMemoryNoOrderStateLedger(
            search_run_authority=InMemorySearchRunAuthority()
        )
        with self.assertRaisesRegex(
            NoOrderLedgerError,
            "no_order_coordinator_required",
        ):
            standalone.stage_post_evaluation_run(  # type: ignore[arg-type]
                run,
                (),
                authority_claim=None,
            )

    def test_all_positive_receipt_survives_purge_while_case_partition_is_live(
        self,
    ) -> None:
        authority = InMemorySearchRunAuthority()
        ledger = InMemoryNoOrderStateLedger(
            search_run_authority=authority,
            coordinator_required=True,
        )
        shared_run, evaluations = self._shared_candidate_run(
            run_id="SYN-RUN-ALL-POSITIVE-0001"
        )
        scoped = shared_run.interactions[0]
        run = OrderSearchRun(
            run_id=shared_run.run_id,
            trigger=shared_run.trigger,
            interactions=(scoped,),
            native_result_sets=shared_run.native_result_sets,
            adapter=shared_run.adapter,
            started_at=shared_run.started_at,
            completed_at=shared_run.completed_at,
        )
        owner, _, stage, seal = self._stage_and_seal(
            ledger=ledger,
            authority=authority,
            run=run,
            evaluations=(evaluations[0],),
        )
        self.assertIsNone(stage.required_partition)
        result = ledger.commit_post_evaluation_stage(stage, seal=seal)
        authority.commit_seal(seal)
        ledger.finalize_post_evaluation_stage(stage)
        self.assertEqual(result.active_no_order, ())
        self.assertEqual(result.manual_review, ())
        self.assertEqual(result.terminal_no_order, ())

        self.assertEqual(
            ledger.purge_closed(now=ts("2026-08-24T16:00:01Z")),
            0,
        )
        replay_stage = ledger.stage_post_evaluation_run(
            run,
            (evaluations[0],),
        )
        replay = ledger.commit_post_evaluation_stage(replay_stage, seal=None)
        self.assertTrue(replay.replayed)

        authority.release_run(run.run_id, owner=owner)
        self.assertEqual(
            ledger.purge_closed(now=ts("2026-08-24T16:00:02Z")),
            0,
        )
        with self.assertRaisesRegex(
            NoOrderLedgerError,
            "post_evaluation_authority_claim",
        ):
            ledger.stage_post_evaluation_run(run, (evaluations[0],))

    def test_active_roots_split_into_distinct_positive_case_partitions(self) -> None:
        authority = InMemorySearchRunAuthority()
        ledger = InMemoryNoOrderStateLedger(
            search_run_authority=authority,
            coordinator_required=True,
        )
        shared_email = "partition.split@example.test"
        roots = (
            interaction(
                301,
                email=shared_email,
                recorded_at="2026-08-20T16:00:00Z",
                review_window_start=date(2026, 8, 20),
                precision=TimestampPrecision.EXACT,
            ),
            interaction(
                302,
                email=shared_email,
                recorded_at="2026-08-21T14:00:00Z",
                review_window_start=date(2026, 8, 21),
                precision=TimestampPrecision.EXACT,
            ),
        )
        mutation = milestone2_case_mutation()
        negative_snapshot = replace(
            mutation.snapshots[0],
            snapshot_id=SnapshotId("SYN-SNAPSHOT-SPLIT-NEGATIVE-0001"),
            placed_at=ts("2026-08-19T16:00:00Z"),
        )
        search_plan = plan_discovery(email_values=(shared_email,))
        first_run = OrderSearchRun(
            run_id=RunId("SYN-RUN-PARTITION-SPLIT-0001"),
            trigger=SearchTriggerType.NORMAL,
            interactions=roots,
            native_result_sets=(
                IdentifierSearchResult(
                    identifier=search_plan.identifiers[0],
                    completeness=SearchCompleteness.COMPLETE,
                    order_ids=(mutation.order_id,),
                ),
            ),
            adapter=VersionBinding(
                "sales_credit_search_adapter",
                OrderSearchRun.ADAPTER_VERSION,
            ),
            started_at=ts("2026-08-23T16:00:00Z"),
            completed_at=ts("2026-08-23T16:00:01Z"),
        )
        first_evaluations = tuple(
            SelectorOwnedCandidateEvaluation(
                interaction_id=root.interaction_id,
                snapshot=negative_snapshot,
                evaluated_at=first_run.completed_at,
                evaluation=evaluate_sales_credit(
                    evaluation_id=EvaluationId(
                        f"SYN-EVALUATION-PARTITION-NEGATIVE-{index:04d}"
                    ),
                    expected_order_id=mutation.order_id,
                    snapshot=negative_snapshot,
                    evaluated_at=first_run.completed_at,
                    known_other_reps=KNOWN_OTHER_REP_CATALOG,
                    interactions=(root,),
                ),
            )
            for index, root in enumerate(roots, start=1)
        )
        _, _, first_stage, first_seal = self._stage_and_seal(
            ledger=ledger,
            authority=authority,
            run=first_run,
            evaluations=first_evaluations,
        )
        ledger.commit_post_evaluation_stage(first_stage, seal=first_seal)
        authority.commit_seal(first_seal)
        ledger.finalize_post_evaluation_stage(first_stage)
        self.assertEqual(len(ledger.retained_interactions), 2)
        self.assertEqual(ledger.retained_snapshot_count, 1)

        incoming_partitions: list[SearchRunOwnerPartition] = []
        incoming_owners: list[object] = []
        for index, retained in enumerate(tuple(ledger.retained_interactions), start=2):
            positive_snapshot = replace(
                mutation.snapshots[0],
                snapshot_id=SnapshotId(
                    f"SYN-SNAPSHOT-SPLIT-POSITIVE-{index:04d}"
                ),
            )
            positive_run = OrderSearchRun(
                run_id=RunId(f"SYN-RUN-PARTITION-SPLIT-{index:04d}"),
                trigger=SearchTriggerType.AUTOMATIC_RECHECK,
                interactions=(retained,),
                native_result_sets=(
                    IdentifierSearchResult(
                        identifier=search_plan.identifiers[0],
                        completeness=SearchCompleteness.COMPLETE,
                        order_ids=(mutation.order_id,),
                    ),
                ),
                adapter=first_run.adapter,
                started_at=ts(f"2026-08-{22 + index:02d}T16:00:00Z"),
                completed_at=ts(f"2026-08-{22 + index:02d}T16:00:01Z"),
            )
            positive_evaluation = SelectorOwnedCandidateEvaluation(
                interaction_id=retained.interaction_id,
                snapshot=positive_snapshot,
                evaluated_at=positive_run.completed_at,
                evaluation=evaluate_sales_credit(
                    evaluation_id=EvaluationId(
                        f"SYN-EVALUATION-PARTITION-POSITIVE-{index:04d}"
                    ),
                    expected_order_id=mutation.order_id,
                    snapshot=positive_snapshot,
                    evaluated_at=positive_run.completed_at,
                    known_other_reps=KNOWN_OTHER_REP_CATALOG,
                    interactions=(retained,),
                ),
            )
            case_owner = authority.new_owner()
            claim = authority.claim(positive_run, owner=case_owner)
            stage = ledger.stage_post_evaluation_run(
                positive_run,
                (positive_evaluation,),
                authority_claim=claim,
            )
            self.assertEqual(len(stage.positive_transfers), 1)
            requested_transfer = stage.positive_transfers[0]
            self.assertEqual(
                requested_transfer.roots[0].interaction_id,
                retained.interaction_id,
            )
            self.assertIs(requested_transfer.retain_outgoing, index == 2)
            current_partition = authority.new_partition(
                owner=case_owner,
                kind=SearchRunPartitionKind.POSITIVE_CASE_ACTIVE,
            )
            incoming_partition = authority.new_partition(
                owner=case_owner,
                kind=SearchRunPartitionKind.POSITIVE_CASE_ACTIVE,
            )
            incoming_partitions.append(incoming_partition)
            incoming_owners.append(case_owner)
            seal = authority.seal_run(
                (claim,),
                partitions=(current_partition,),
            )
            transfer = authority.stage_partition_transfer(
                first_run.run_id,
                outgoing_partition=requested_transfer.outgoing_partition,
                incoming_partitions=(incoming_partition,),
                retain_outgoing=requested_transfer.retain_outgoing,
            )
            ledger.commit_post_evaluation_stage(
                stage,
                seal=seal,
                partition_transfers=(transfer,),
            )
            authority.commit_seal(seal)
            authority.commit_partition_transfer(transfer)
            ledger.finalize_post_evaluation_stage(stage)

        self.assertEqual(ledger.retained_interactions, ())
        self.assertEqual(ledger.retained_snapshot_count, 0)
        authority.release_partition(
            first_run.run_id,
            incoming_partitions[0],
            owner=incoming_owners[0],
        )
        replay_stage = ledger.stage_post_evaluation_run(
            first_run,
            first_evaluations,
        )
        replay = ledger.commit_post_evaluation_stage(replay_stage, seal=None)
        self.assertTrue(replay.replayed)
        authority.release_partition(
            first_run.run_id,
            incoming_partitions[1],
            owner=incoming_owners[1],
        )
        ledger.purge_closed(now=ts("2026-08-26T16:00:02Z"))
        with self.assertRaisesRegex(
            NoOrderLedgerError,
            "post_evaluation_authority_claim",
        ):
            ledger.stage_post_evaluation_run(first_run, first_evaluations)

    def test_aggregate_timing_evaluation_cannot_claim_per_owner_authority(self) -> None:
        authority = InMemorySearchRunAuthority()
        ledger = InMemoryNoOrderStateLedger(
            search_run_authority=authority,
            coordinator_required=True,
        )
        run, evaluations = self._shared_candidate_run(
            run_id="SYN-RUN-POST-EVALUATION-AGGREGATE-0001"
        )
        aggregate = evaluate_sales_credit(
            evaluation_id=EvaluationId(
                "SYN-EVALUATION-POST-SCOPE-AGGREGATE-0001"
            ),
            expected_order_id=evaluations[0].evaluation.order_id,
            snapshot=evaluations[0].snapshot,
            evaluated_at=run.completed_at,
            known_other_reps=KNOWN_OTHER_REP_CATALOG,
            interactions=run.interactions,
        )
        forged_pairs = (
            replace(evaluations[0], evaluation=aggregate),
            replace(
                evaluations[1],
                evaluation=replace(
                    aggregate,
                    evaluation_id=EvaluationId(
                        "SYN-EVALUATION-POST-SCOPE-AGGREGATE-0002"
                    ),
                ),
            ),
        )
        owner = authority.new_owner()
        claim = authority.claim(run, owner=owner)
        with self.assertRaisesRegex(
            NoOrderLedgerError,
            "candidate_evaluation_recompute",
        ):
            ledger.stage_post_evaluation_run(
                run,
                forged_pairs,
                authority_claim=claim,
            )
        authority.rollback(claim)

    def test_snapshot_identity_cannot_be_reused_across_candidate_orders(self) -> None:
        authority = InMemorySearchRunAuthority()
        ledger = InMemoryNoOrderStateLedger(
            search_run_authority=authority,
            coordinator_required=True,
        )
        mutation = milestone2_case_mutation()
        scoped = interaction(
            251,
            email="snapshot.owner@example.test",
            recorded_at="2026-08-20T16:00:00Z",
            review_window_start=date(2026, 8, 20),
            precision=TimestampPrecision.EXACT,
        )
        second_order = OrderId("SYN-ORDER-M2-KAT-0002")
        second_snapshot = replace(
            mutation.snapshots[0],
            order_id=second_order,
        )
        plan = plan_discovery(email_values=(scoped.email,))
        run = OrderSearchRun(
            run_id=RunId("SYN-RUN-POST-SNAPSHOT-OWNER-0001"),
            trigger=SearchTriggerType.NORMAL,
            interactions=(scoped,),
            native_result_sets=(
                IdentifierSearchResult(
                    identifier=plan.identifiers[0],
                    completeness=SearchCompleteness.COMPLETE,
                    order_ids=(mutation.order_id, second_order),
                ),
            ),
            adapter=VersionBinding(
                "sales_credit_search_adapter",
                OrderSearchRun.ADAPTER_VERSION,
            ),
            started_at=ts("2026-08-23T16:00:00Z"),
            completed_at=ts("2026-08-23T16:00:01Z"),
        )
        pairs = tuple(
            SelectorOwnedCandidateEvaluation(
                interaction_id=scoped.interaction_id,
                snapshot=snapshot,
                evaluated_at=run.completed_at,
                evaluation=evaluate_sales_credit(
                    evaluation_id=EvaluationId(
                        f"SYN-EVALUATION-SNAPSHOT-OWNER-{index:04d}"
                    ),
                    expected_order_id=order_id,
                    snapshot=snapshot,
                    evaluated_at=run.completed_at,
                    known_other_reps=KNOWN_OTHER_REP_CATALOG,
                    interactions=(scoped,),
                ),
            )
            for index, (order_id, snapshot) in enumerate(
                (
                    (mutation.order_id, mutation.snapshots[0]),
                    (second_order, second_snapshot),
                ),
                start=1,
            )
        )
        owner = authority.new_owner()
        claim = authority.claim(run, owner=owner)
        with self.assertRaisesRegex(
            NoOrderLedgerError,
            "candidate_snapshot_owner_conflict",
        ):
            ledger.stage_post_evaluation_run(
                run,
                pairs,
                authority_claim=claim,
            )
        authority.rollback(claim)

    def test_terminal_hash_verification_failure_rolls_back_composed_stage(self) -> None:
        authority = InMemorySearchRunAuthority()
        ledger = InMemoryNoOrderStateLedger(
            search_run_authority=authority,
            coordinator_required=True,
        )
        run, evaluations = self._shared_candidate_run(
            started_at="2026-09-06T16:00:00Z",
            completed_at="2026-09-06T16:00:01Z",
            run_id="SYN-RUN-POST-HASH-ROLLBACK-0001",
        )
        _, claim, stage, seal = self._stage_and_seal(
            ledger=ledger,
            authority=authority,
            run=run,
            evaluations=evaluations,
        )
        with patch.object(
            NoOrderClosedAuditRecord,
            "hash_binding",
            side_effect=ValueError("synthetic hash failure"),
        ):
            with self.assertRaisesRegex(
                NoOrderLedgerError,
                "post_evaluation_result_failed",
            ):
                ledger.commit_post_evaluation_stage(stage, seal=seal)
        authority.rollback_seal(seal)
        ledger.rollback_post_evaluation_stage(stage)
        authority.rollback(claim)
        self.assertEqual(ledger.retained_interactions, ())
        self.assertEqual(ledger.closure_receipt_count, 0)
        self.assertEqual(authority.retained_canonical_material, ())


if __name__ == "__main__":
    unittest.main()
