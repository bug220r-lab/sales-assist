from __future__ import annotations

import dataclasses
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from synthetic_sales_assist.doi.evaluator import evaluate_doi
from synthetic_sales_assist.doi.case_attention import (
    CaseOwnerHistory,
    issue_case_creation_decision,
)
from synthetic_sales_assist.doi.extraction import (
    DOIExtractionAttempt,
    DOIExtractionResult,
    ExtractionStatus,
    extract_order_snapshot,
)
from synthetic_sales_assist.doi.identities import (
    AcceptedCommandId,
    DoiOrderId,
    DoiRunId,
    ExtractionAttemptId,
    ExtractionOccurrenceId,
    RunInvocationId,
)
from synthetic_sales_assist.doi.interventions import (
    DOIResultingOrderLinkSearchHistory,
    ResultingLinkSearchEvidence,
    ValueCorrectionKind,
    append_resulting_link_search,
    append_value_event,
)
from synthetic_sales_assist.doi.models import (
    AlternateRelationshipType,
    AttentionCondition,
    CaseLifecycleState,
    CompatibilityDecision,
    DOIEvaluationInput,
    InterventionType,
    LineAvailability,
    OrderState,
    QuantityAvailability,
    RepRelation,
    SourcePresence,
    ValueEventType,
)
from synthetic_sales_assist.doi.retention import (
    build_retained_kpi_contribution,
    cancel_retention_on_reopen,
    schedule_retention,
)
from synthetic_sales_assist.doi.source import (
    DOIRunWorkDisposition,
    InMemoryDOIRunControl,
    RunStatus,
    RunType,
    accept_no_retry_command,
    ingest_synthetic_queue,
)
from synthetic_sales_assist.domain.identities import (
    EvaluationId,
    EvidenceId,
    InteractionId,
    OrderId,
    RepId,
    RunId,
)
from synthetic_sales_assist.domain.numeric import (
    CURRENCY_REGISTRY_VERSION,
    NonNegativeCount,
)
from synthetic_sales_assist.domain.records import ReasonSet
from synthetic_sales_assist.domain.registries import load_doi_registries
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp
from synthetic_sales_assist.persistence.database import SQLiteDatabase
from synthetic_sales_assist.persistence.doi_repository import (
    DOIPersistenceConflict,
    DOIPersistenceError,
)
from synthetic_sales_assist.persistence.doi_services import DOIPersistenceService
from synthetic_sales_assist.persistence.faults import (
    FaultInjector,
    FaultPoint,
    InjectedPersistenceFault,
)
from tests.test_doi_evaluator import (
    evaluation_input,
    relationship_candidate,
    split_lines,
)
from tests.test_doi_extraction import _surface as extraction_surface
from tests.test_doi_interventions import (
    _order_source as intervention_order_source,
    _value_event,
)
from tests.test_doi_models import make_line, order_source
from tests.test_doi_retention import (
    _intervention,
    _link,
)
from tests.test_doi_source import (
    _batch_id,
    _command_id,
    _evaluation_record,
    _image,
    _review_start,
    _row,
    _source_id,
)


NOW = CanonicalTimestamp("2026-08-20T14:15:16Z")


def _failed_control() -> tuple[InMemoryDOIRunControl, object, object]:
    control = InMemoryDOIRunControl()
    started = _review_start(control)
    assert started.source_attempt is not None
    image = _image((_row(1, "SYN-ORDER-INVALID"),))
    failed = control.commit_import_result(
        attempt_id=started.source_attempt.attempt_id,
        result=ingest_synthetic_queue(
            image,
            image,
            candidate_batch_id=_batch_id(),
        ),
        completed_at=CanonicalTimestamp("2026-08-10T12:01:00Z"),
    )
    return control, started, failed


class Milestone4DOIRequiredInvariantTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.database = SQLiteDatabase(
            Path(self.temporary.name) / "doi-required.sqlite3",
            busy_timeout_ms=10_000,
        )
        self.database.initialize()
        self.service = DOIPersistenceService(self.database)

    def _persist_failed_attempt(self) -> tuple[object, object, object]:
        control, started, failed = _failed_control()
        self.service.invoke_run(started)
        assert started.source_attempt is not None
        assert started.source_attempt_event is not None
        self.service.import_source_attempt(
            started.source_attempt,
            started.source_attempt_event,
        )
        self.service.import_source_attempt(
            failed,
            control.attempt_events(failed.attempt_id)[-1],
        )
        return control, started, failed

    def _recheck_start(self, suffix: str):  # type: ignore[no-untyped-def]
        control = InMemoryDOIRunControl()
        start = control.begin_recheck_run(
            run_id=RunId(f"SYN-RUN-DOI-M4-{suffix}"),
            invocation_id=RunInvocationId(
                InteractionId(f"SYN-INTERACTION-DOI-M4-{suffix}")
            ),
            run_type=RunType.RECHECK_ORDER,
            order_id=OrderId("SYN-ORDER-DOI-M4-RACE"),
            accepted_at=NOW,
        )
        return control, start

    def _persist_request(
        self,
        request: DOIEvaluationInput,
        case_id: EvidenceId,
        suffix: str,
    ):
        control = InMemoryDOIRunControl()
        start = control.begin_recheck_run(
            run_id=request.snapshot.run_id.value,
            invocation_id=RunInvocationId(
                InteractionId(f"SYN-INTERACTION-DOI-M4-EVAL-{suffix}")
            ),
            run_type=RunType.RECHECK_ORDER,
            order_id=request.snapshot.order_id.value,
            accepted_at=request.evaluated_at,
        )
        self.service.invoke_run(start)
        evaluation = evaluate_doi(request)
        self.service.append_snapshot_evaluation(
            case_id=case_id,
            snapshot=request.snapshot,
            evaluation=evaluation,
            created_at=request.evaluated_at,
        )
        return evaluation

    def _substitution_graph(
        self,
        *,
        persist_intervention: bool = True,
    ):  # type: ignore[no-untyped-def]
        source = order_source(OrderId("SYN-ORDER-DOI-0001"))
        lines = (make_line(1, source),)
        base = evaluation_input(
            lines,
            evaluation_suffix="INTERVENTION-SUBSTITUTION-BASE",
        )
        candidate = relationship_candidate(
            base,
            relationship_type=AlternateRelationshipType.EXACT_MFG,
            compatibility=CompatibilityDecision.NOT_REQUIRED,
            suffix="INTERVENTION-SUBSTITUTION",
        )
        request = evaluation_input(
            lines,
            evaluation_suffix="INTERVENTION-SUBSTITUTION-OWNER",
            alternate_candidates=(candidate,),
        )
        case_id = EvidenceId("SYN-EVIDENCE-DOI-M4-INTERVENTION-CASE")
        evaluation = self._persist_request(request, case_id, "INTERVENTION")
        intervention = _intervention(
            InterventionType.PRODUCT_SUBSTITUTION,
            verified_cents=4_321,
            suffix="M4-SQL",
        )
        self.assertIn(
            intervention.opportunity_id,
            {item.opportunity_id for item in evaluation.opportunities},
        )
        if persist_intervention:
            self.service.record_intervention(
                case_id=case_id,
                intervention=intervention,
                created_at=NOW,
            )
        link = _link(
            intervention,
            order_rep_verified=False,
            line_rep_verified=True,
            suffix="M4-SQL",
        )
        decision = build_retained_kpi_contribution(
            intervention,
            event_id=EvidenceId("SYN-EVIDENCE-DOI-M4-KPI-EVENT"),
            resulting_link=link,
        )
        assert decision.event is not None
        assert decision.contribution is not None
        return case_id, request, intervention, link, decision

    def _persist_case_admission_graph(self):  # type: ignore[no-untyped-def]
        control = InMemoryDOIRunControl()
        started = _review_start(control)
        assert started.source_attempt is not None
        assert started.source_attempt_event is not None
        self.service.invoke_run(started)
        self.service.import_source_attempt(
            started.source_attempt,
            started.source_attempt_event,
        )
        image = _image((_row(1, "SYN-ORDER-1"),))
        result = ingest_synthetic_queue(
            image,
            image,
            candidate_batch_id=_batch_id(),
        )
        attempt = control.commit_import_result(
            attempt_id=started.source_attempt.attempt_id,
            result=result,
            completed_at=CanonicalTimestamp("2026-08-10T12:01:00Z"),
        )
        work_items = control.work_items(started.run.run_id)
        self.service.import_source_attempt(
            attempt,
            control.attempt_events(attempt.attempt_id)[-1],
            result=result,
            run=control.run(started.run.run_id),
            work_items=work_items,
        )
        assert result.batch is not None
        case_id = EvidenceId("SYN-EVIDENCE-DOI-M4-ADMITTED-CASE")
        decision = issue_case_creation_decision(
            history=CaseOwnerHistory(case_id, DoiOrderId(work_items[0].order_id)),
            event_id=EvidenceId("SYN-EVIDENCE-DOI-M4-CASE-CREATED"),
            binding_id=EvidenceId("SYN-EVIDENCE-DOI-M4-CASE-BINDING"),
            admission_proof_id=EvidenceId(
                "SYN-EVIDENCE-DOI-M4-CASE-ADMISSION"
            ),
            source_result=result,
            staged_order=result.batch.staged_orders[0],
            work_item=work_items[0],
            admitted_at=CanonicalTimestamp("2026-08-10T12:02:00Z"),
        )
        return decision, attempt, control

    def _admitted_lines(self):  # type: ignore[no-untyped-def]
        source = order_source(OrderId("SYN-ORDER-1"))
        return (
            make_line(
                1,
                source,
                availability=LineAvailability.IN_STOCK,
                quantity_availability=QuantityAvailability.FULL,
                explicitly_available=2,
            ),
            make_line(2, source),
        )

    def _admitted_request(self, suffix: str) -> DOIEvaluationInput:
        source = order_source(OrderId("SYN-ORDER-1"))
        extracted = extract_order_snapshot(
            extraction_surface(lines=self._admitted_lines(), source=source)
        )
        if extracted.snapshot is None:
            raise AssertionError("admitted snapshot fixture must extract")
        return DOIEvaluationInput(
            evaluation_id=EvaluationId(f"SYN-EVALUATION-DOI-{suffix}"),
            snapshot=extracted.snapshot,
            evaluated_at=NOW,
        )

    def _persist_admitted_evaluation(self):  # type: ignore[no-untyped-def]
        decision, attempt, control = self._persist_case_admission_graph()
        self.service.apply_case_owner_decision(decision)
        request = self._admitted_request("M4-ADMITTED-EVALUATION")
        evaluation = self._persist_request(
            request,
            decision.stream_id,
            "ADMITTED-EVALUATION",
        )
        return decision, attempt, control, request, evaluation

    def _result_search_history(
        self,
        intervention: object,
        link: object,
        suffix: str,
    ):  # type: ignore[no-untyped-def]
        search_id = EvidenceId(f"SYN-EVIDENCE-DOI-M4-SEARCH-{suffix}")
        evidence = ResultingLinkSearchEvidence.from_complete_search(
            evidence_id=EvidenceId(
                f"SYN-EVIDENCE-DOI-M4-SEARCH-EVIDENCE-{suffix}"
            ),
            search_id=search_id,
            parent_order_id=link.parent_order_id,  # type: ignore[attr-defined]
            intervention_type=(
                intervention.intervention_type  # type: ignore[attr-defined]
            ),
            candidate_order_ids=(),
            disproved_candidate_order_ids=(),
            observed_at=NOW,
            source=intervention_order_source(
                link.parent_order_id,  # type: ignore[attr-defined]
                f"M4-SEARCH-{suffix}",
            ),
        )
        history = DOIResultingOrderLinkSearchHistory(
            search_id=search_id,
            parent_order_id=link.parent_order_id,  # type: ignore[attr-defined]
            intervention_type=(
                intervention.intervention_type  # type: ignore[attr-defined]
            ),
        )
        return append_resulting_link_search(
            history,
            event_id=EvidenceId(f"SYN-EVIDENCE-DOI-M4-SEARCH-EVENT-{suffix}"),
            evidence=evidence,
        ).history

    def _persist_failed_extraction(self, suffix: str):  # type: ignore[no-untyped-def]
        _, start = self._recheck_start(f"EXTRACTION-{suffix}")
        self.service.invoke_run(start)
        registry = load_doi_registries()
        attempt = DOIExtractionAttempt(
            attempt_id=ExtractionAttemptId(
                InteractionId(f"SYN-INTERACTION-DOI-M4-EXTRACTION-{suffix}")
            ),
            run_id=DoiRunId(start.run.run_id),
            order_id=DoiOrderId(OrderId("SYN-ORDER-DOI-M4-RACE")),
            started_at=NOW,
            completed_at=NOW,
            status=ExtractionStatus.FAILED,
            snapshot_id=None,
            reasons=ReasonSet(
                tuple(
                    registry.reason_ref(code)
                    for code in ("RC-011", "RC-014", "RC-015")
                )
            ),
            portal_read_count=NonNegativeCount(1),
        )
        result = DOIExtractionResult(
            attempt,
            None,
            (AttentionCondition.RECHECK_REQUIRED,),
        )
        case_id = EvidenceId(f"SYN-EVIDENCE-DOI-M4-EXTRACTION-{suffix}-CASE")
        self.service.complete_extraction(
            case_id=case_id,
            result=result,
            created_at=NOW,
        )
        return case_id, result

    def test_source_import_failure_does_not_terminalize_parent_run(self) -> None:
        _, started, _ = self._persist_failed_attempt()
        with self.database.read() as connection:
            status = connection.execute(
                "SELECT status FROM doi_run_projections WHERE run_id=?",
                (started.run.run_id.value,),
            ).fetchone()[0]
            receipts = connection.execute(
                "SELECT COUNT(*) FROM doi_run_control_receipts"
            ).fetchone()[0]
        self.assertEqual(status, RunStatus.IN_PROGRESS.value)
        self.assertEqual(receipts, 0)

    def test_case_admission_and_snapshot_proofs_are_atomic_and_replayable(self) -> None:
        decision, _, _ = self._persist_case_admission_graph()
        with self.assertRaises(InjectedPersistenceFault):
            self.service.apply_case_owner_decision(
                decision,
                fault_injector=FaultInjector(
                    frozenset({FaultPoint.BEFORE_COMMIT})
                ),
            )
        with self.database.read() as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM doi_case_source_batch_references"
                ).fetchone()[0],
                0,
            )
        first = self.service.apply_case_owner_decision(decision)
        replay = self.service.apply_case_owner_decision(decision)
        self.assertFalse(first.replayed)
        self.assertTrue(replay.replayed)
        request = self._admitted_request("M4-ADMISSION-PROOFS")
        self._persist_request(
            request,
            decision.stream_id,
            "ADMISSION-PROOFS",
        )
        with self.database.read() as connection:
            counts = tuple(
                connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in (
                    "doi_case_source_batch_references",
                    "doi_snapshot_completeness_proof_references",
                    "doi_line_continuity_proof_references",
                )
            )
            artifact_kinds = tuple(
                row[0]
                for row in connection.execute(
                    "SELECT artifact_kind FROM doi_case_artifacts WHERE "
                    "artifact_kind IN ('CASE_ADMISSION_PROOF', "
                    "'CASE_SOURCE_BINDING', 'COMPLETENESS_PROOF', "
                    "'LINE_CONTINUITY_PROOF') ORDER BY artifact_kind"
                ).fetchall()
            )
        self.assertEqual(counts, (1, 1, 2))
        self.assertEqual(
            artifact_kinds,
            (
                "CASE_ADMISSION_PROOF",
                "CASE_SOURCE_BINDING",
                "COMPLETENESS_PROOF",
                "LINE_CONTINUITY_PROOF",
                "LINE_CONTINUITY_PROOF",
            ),
        )
        self.assertTrue(self.service.verify_projections().ok)

    def test_normalized_source_evaluation_and_proof_children_are_immutable(self) -> None:
        self._persist_admitted_evaluation()
        statements = (
            "UPDATE doi_attempt_batch_references SET batch_id=batch_id",
            "UPDATE doi_staged_order_source_refs SET ordinal=ordinal",
            "UPDATE doi_case_source_batch_references "
            "SET binding_artifact_pk=binding_artifact_pk",
            "UPDATE doi_snapshot_completeness_proof_references "
            "SET proof_artifact_pk=proof_artifact_pk",
            "UPDATE doi_line_continuity_proof_references "
            "SET proof_artifact_pk=proof_artifact_pk",
            "UPDATE doi_evaluation_reasons SET ordinal=ordinal",
            "UPDATE doi_opportunity_scope_components SET ordinal=ordinal",
        )
        for statement in statements:
            with self.subTest(statement=statement):
                with self.assertRaisesRegex(
                    sqlite3.IntegrityError,
                    "DOI_IMMUTABLE_RECORD",
                ):
                    with self.database.write() as connection:
                        connection.execute(statement)

    def test_deep_verifier_detects_deleted_staged_source_reference(self) -> None:
        self._persist_admitted_evaluation()
        with self.database.write() as connection:
            connection.execute("DELETE FROM doi_staged_order_source_refs")
        self.assertIn(
            "DOI_SOURCE_NORMALIZED_CHILD_MISMATCH",
            self.service.verify_projections().errors,
        )

    def test_deep_verifier_detects_deleted_snapshot_proof_reference(self) -> None:
        self._persist_admitted_evaluation()
        with self.database.write() as connection:
            connection.execute(
                "DELETE FROM doi_snapshot_completeness_proof_references"
            )
        self.assertIn(
            "DOI_SNAPSHOT_PROOF_CHILD_MISMATCH",
            self.service.verify_projections().errors,
        )

    def test_deep_verifier_detects_deleted_evaluation_reason(self) -> None:
        self._persist_admitted_evaluation()
        with self.database.write() as connection:
            connection.execute(
                "DELETE FROM doi_evaluation_reasons WHERE ordinal=1"
            )
        self.assertIn(
            "DOI_EVALUATION_NORMALIZED_CHILD_MISMATCH",
            self.service.verify_projections().errors,
        )

    def test_deep_verifier_detects_deleted_attempt_batch_reference(self) -> None:
        _, attempt, _ = self._persist_case_admission_graph()
        with self.database.write() as connection:
            connection.execute(
                "DELETE FROM doi_attempt_batch_references WHERE attempt_id=?",
                (attempt.attempt_id.to_json_value(),),
            )
        self.assertIn(
            "DOI_SOURCE_BATCH_REFERENCE_MISMATCH",
            self.service.verify_projections().errors,
        )

    def test_deep_verifier_detects_deleted_run_work_item(self) -> None:
        _, attempt, _ = self._persist_case_admission_graph()
        with self.database.write() as connection:
            connection.execute(
                "DELETE FROM doi_run_work_items WHERE run_id=?",
                (attempt.run_id.value,),
            )
        self.assertIn(
            "DOI_RUN_WORK_CHILD_MISMATCH",
            self.service.verify_projections().errors,
        )

    def test_deep_verifier_detects_deleted_case_admission_proof_graph(self) -> None:
        decision, _, _ = self._persist_case_admission_graph()
        self.service.apply_case_owner_decision(decision)
        with self.database.write() as connection:
            connection.execute(
                "DELETE FROM doi_case_artifacts WHERE artifact_kind IN "
                "('CASE_ADMISSION_PROOF', 'CASE_SOURCE_BINDING')"
            )
        self.assertIn(
            "DOI_CASE_SOURCE_PROOF_MISMATCH",
            self.service.verify_projections().errors,
        )

    def test_successful_source_import_persists_complete_normalized_graph(self) -> None:
        control = InMemoryDOIRunControl()
        started = _review_start(control)
        assert started.source_attempt is not None
        assert started.source_attempt_event is not None
        self.service.invoke_run(started)
        self.service.import_source_attempt(
            started.source_attempt,
            started.source_attempt_event,
        )
        image = _image(
            (
                _row(1, "SYN-ORDER-1"),
                _row(2, "SYN-ORDER-2"),
                _row(3, "SYN-ORDER-2", "OTHER_REP"),
            )
        )
        result = ingest_synthetic_queue(
            image,
            image,
            candidate_batch_id=_batch_id(),
        )
        attempt = control.commit_import_result(
            attempt_id=started.source_attempt.attempt_id,
            result=result,
            completed_at=CanonicalTimestamp("2026-08-10T12:01:00Z"),
        )
        values = {
            "result": result,
            "run": control.run(started.run.run_id),
            "work_items": control.work_items(started.run.run_id),
        }
        with self.assertRaises(InjectedPersistenceFault):
            self.service.import_source_attempt(
                attempt,
                control.attempt_events(attempt.attempt_id)[-1],
                **values,
                fault_injector=FaultInjector(
                    frozenset({FaultPoint.BEFORE_COMMIT})
                ),
            )
        with self.database.read() as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM doi_source_batches"
                ).fetchone()[0],
                0,
            )
        first = self.service.import_source_attempt(
            attempt,
            control.attempt_events(attempt.attempt_id)[-1],
            **values,
        )
        replay = self.service.import_source_attempt(
            attempt,
            control.attempt_events(attempt.attempt_id)[-1],
            **values,
        )
        self.assertFalse(first.replayed)
        self.assertTrue(replay.replayed)
        with self.database.read() as connection:
            counts = tuple(
                connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in (
                    "doi_source_batches",
                    "doi_attempt_batch_references",
                    "doi_staged_orders",
                    "doi_staged_order_source_refs",
                    "doi_rejected_source_records",
                    "doi_run_work_items",
                    "doi_source_import_aggregates",
                )
            )
        self.assertEqual(counts, (1, 1, 1, 1, 1, 1, 1))
        with self.assertRaisesRegex(
            sqlite3.IntegrityError,
            "DOI_IMMUTABLE_RECORD",
        ):
            with self.database.write() as connection:
                connection.execute(
                    "UPDATE doi_rejected_source_records "
                    "SET record_payload=record_payload"
                )
        with self.database.write() as connection:
            connection.execute(
                "UPDATE doi_rejected_source_records "
                "SET retention_state=retention_state"
            )
        self.assertTrue(self.service.verify_projections().ok)

    def test_source_attempt_retention_purges_without_identity_tombstone(self) -> None:
        control = InMemoryDOIRunControl()
        started = _review_start(control)
        assert started.source_attempt is not None
        assert started.source_attempt_event is not None
        self.service.invoke_run(started)
        self.service.import_source_attempt(
            started.source_attempt,
            started.source_attempt_event,
        )
        image = _image((_row(1, "SYN-ORDER-INVALID"),))
        result = ingest_synthetic_queue(
            image,
            image,
            candidate_batch_id=_batch_id(),
        )
        failed = control.commit_import_result(
            attempt_id=started.source_attempt.attempt_id,
            result=result,
            completed_at=CanonicalTimestamp("2026-08-10T12:01:00Z"),
        )
        self.service.import_source_attempt(
            failed,
            control.attempt_events(failed.attempt_id)[-1],
            result=result,
            run=control.run(started.run.run_id),
            work_items=(),
        )
        command = accept_no_retry_command(
            command_id=_command_id("M4-SOURCE-PURGE-NO-RETRY"),
            run_id=started.run.run_id,
            greatest_failed_attempt_id=failed.attempt_id,
            accepted_actor_id=RepId("SYN-REP-AUTHORIZED-0001"),
            accepted_at=CanonicalTimestamp("2026-08-10T12:02:00Z"),
        )
        receipt = control.finalize_failed_source_import_no_retry(command)
        terminal = control.run(started.run.run_id)
        self.service.explicit_no_retry_finalization(
            command=command,
            receipt=receipt,
            run=terminal,
            event=control.run_events(started.run.run_id)[-1],
        )
        identity = started.run.run_id.value
        self.assertGreater(self.service.identity_occurrences(identity), 0)
        assert terminal.purge_eligible_at is not None
        first = self.service.purge_terminal_run(
            terminal.run_id,
            now=terminal.purge_eligible_at,
        )
        replay = self.service.purge_terminal_run(
            terminal.run_id,
            now=terminal.purge_eligible_at,
        )
        self.assertFalse(first.replayed)
        self.assertTrue(replay.replayed)
        self.assertEqual(self.service.identity_occurrences(identity), 0)
        with self.database.read() as connection:
            aggregate = connection.execute(
                "SELECT attempt_count FROM doi_source_import_aggregates "
                "WHERE outcome_class='FAILED'"
            ).fetchone()[0]
            self.assertEqual(aggregate, 1)

    def test_rejected_source_retention_is_bound_to_terminal_run_purge(self) -> None:
        control = InMemoryDOIRunControl()
        started = _review_start(control)
        assert started.source_attempt is not None
        assert started.source_attempt_event is not None
        self.service.invoke_run(started)
        self.service.import_source_attempt(
            started.source_attempt,
            started.source_attempt_event,
        )
        image = _image(
            (
                _row(1, "SYN-ORDER-1"),
                _row(2, "SYN-ORDER-2"),
                _row(3, "SYN-ORDER-2", "OTHER_REP"),
            )
        )
        result = ingest_synthetic_queue(
            image,
            image,
            candidate_batch_id=_batch_id(),
        )
        attempt = control.commit_import_result(
            attempt_id=started.source_attempt.attempt_id,
            result=result,
            completed_at=CanonicalTimestamp("2026-08-10T12:01:00Z"),
        )
        work_items = control.work_items(started.run.run_id)
        self.service.import_source_attempt(
            attempt,
            control.attempt_events(attempt.attempt_id)[-1],
            result=result,
            run=control.run(started.run.run_id),
            work_items=work_items,
        )
        disposition = DOIRunWorkDisposition.successful_evaluation(
            work_item=work_items[0],
            evaluation=_evaluation_record(),
            occurred_at=CanonicalTimestamp("2026-08-10T12:02:00Z"),
        )
        control.record_work_disposition(disposition)
        with self.assertRaises(InjectedPersistenceFault):
            self.service.record_run_work_disposition(
                disposition,
                fault_injector=FaultInjector(
                    frozenset({FaultPoint.BEFORE_COMMIT})
                ),
            )
        with self.database.read() as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM doi_run_work_dispositions"
                ).fetchone()[0],
                0,
            )
        first_disposition = self.service.record_run_work_disposition(disposition)
        replayed_disposition = self.service.record_run_work_disposition(disposition)
        self.assertFalse(first_disposition.replayed)
        self.assertTrue(replayed_disposition.replayed)
        terminal = control.finalize_processing(
            run_id=started.run.run_id,
            completed_at=CanonicalTimestamp("2026-08-10T12:03:00Z"),
        )
        with self.assertRaises(InjectedPersistenceFault):
            self.service.finalize_run_processing(
                run=terminal.run,
                event=terminal.run_event,
                fault_injector=FaultInjector(
                    frozenset({FaultPoint.BEFORE_COMMIT})
                ),
            )
        with self.database.read() as connection:
            status = connection.execute(
                "SELECT status FROM doi_run_projections"
            ).fetchone()[0]
        self.assertEqual(status, RunStatus.IN_PROGRESS.value)
        self.service.finalize_run_processing(
            run=terminal.run,
            event=terminal.run_event,
        )
        with self.database.read() as connection:
            retention = tuple(
                connection.execute(
                    "SELECT retention_state, purge_eligible_at "
                    "FROM doi_rejected_source_records"
                ).fetchone()
            )
        assert terminal.run.purge_eligible_at is not None
        self.assertEqual(
            retention,
            ("RETAINED_UNTIL", terminal.run.purge_eligible_at.value),
        )
        with self.assertRaises(InjectedPersistenceFault):
            self.service.purge_terminal_run(
                terminal.run.run_id,
                now=terminal.run.purge_eligible_at,
                fault_injector=FaultInjector(
                    frozenset({FaultPoint.DURING_CASE_PURGE})
                ),
            )
        self.assertGreater(self.service.identity_occurrences("SYN-ORDER-2"), 0)
        self.service.purge_terminal_run(
            terminal.run.run_id,
            now=terminal.run.purge_eligible_at,
        )
        self.assertEqual(self.service.identity_occurrences("SYN-ORDER-2"), 0)
        with self.database.read() as connection:
            aggregate = connection.execute(
                "SELECT attempt_count FROM doi_source_import_aggregates "
                "WHERE outcome_class='SUCCEEDED'"
            ).fetchone()[0]
        self.assertEqual(aggregate, 1)

    def test_source_attempt_projection_replay_rejects_tampered_head(self) -> None:
        decision, attempt, control = self._persist_case_admission_graph()
        with self.database.write() as connection:
            connection.execute(
                "UPDATE doi_source_import_attempts SET head_sha256=? "
                "WHERE attempt_id=?",
                ("f" * 64, attempt.attempt_id.to_json_value()),
            )
        result = decision._inputs[0]  # type: ignore[attr-defined]
        with self.assertRaises(DOIPersistenceConflict):
            self.service.import_source_attempt(
                attempt,
                control.attempt_events(attempt.attempt_id)[-1],
                result=result,
                run=control.run(attempt.run_id),
                work_items=control.work_items(attempt.run_id),
            )

    def test_run_refresh_replay_rejects_unowned_material_event_head(self) -> None:
        decision, attempt, control = self._persist_case_admission_graph()
        with self.database.write() as connection:
            connection.execute(
                "UPDATE doi_run_projections SET material_event_sha256=? "
                "WHERE run_id=?",
                ("e" * 64, attempt.run_id.value),
            )
        result = decision._inputs[0]  # type: ignore[attr-defined]
        with self.assertRaises(DOIPersistenceError):
            self.service.import_source_attempt(
                attempt,
                control.attempt_events(attempt.attempt_id)[-1],
                result=result,
                run=control.run(attempt.run_id),
                work_items=control.work_items(attempt.run_id),
            )

    def test_run_exact_replay_rejects_normalized_projection_drift(self) -> None:
        _, start = self._recheck_start("RUN-NORMALIZED-DRIFT")
        self.service.invoke_run(start)
        with self.database.write() as connection:
            connection.execute(
                "UPDATE doi_run_projections SET "
                "source_attempt_count=source_attempt_count+1"
            )
        with self.assertRaises(DOIPersistenceError):
            self.service.invoke_run(start)
        self.assertIn(
            "DOI_RUN_PROJECTION_RECORD_MISMATCH",
            self.service.verify_projections().errors,
        )

    def test_run_material_version_inflation_is_not_replayable(self) -> None:
        _, start = self._recheck_start("RUN-MATERIAL-VERSION-DRIFT")
        self.service.invoke_run(start)
        with self.database.write() as connection:
            connection.execute(
                "UPDATE doi_run_projections SET material_version=material_version+7"
            )
        with self.assertRaises(DOIPersistenceError):
            self.service.invoke_run(start)
        self.assertIn(
            "DOI_RUN_MATERIAL_HISTORY_MISMATCH",
            self.service.verify_projections().errors,
        )

    def test_source_exact_replay_rejects_normalized_state_drift(self) -> None:
        control, _, attempt = self._persist_failed_attempt()
        with self.database.write() as connection:
            connection.execute(
                "UPDATE doi_source_import_attempts SET state='ABORTED' "
                "WHERE attempt_id=?",
                (attempt.attempt_id.to_json_value(),),
            )
        with self.assertRaises(DOIPersistenceError):
            self.service.import_source_attempt(
                attempt,
                control.attempt_events(attempt.attempt_id)[-1],
            )
        self.assertIn(
            "DOI_SOURCE_ATTEMPT_PROJECTION_MISMATCH",
            self.service.verify_projections().errors,
        )

    def test_case_exact_replay_rejects_projection_version_drift(self) -> None:
        request = evaluation_input(
            split_lines(),
            evaluation_suffix="M4-CASE-REPLAY-DRIFT",
            snapshot_suffix="M4-CASE-REPLAY-DRIFT",
            run_suffix="M4-CASE-REPLAY-DRIFT",
        )
        case_id = EvidenceId("SYN-EVIDENCE-DOI-M4-CASE-REPLAY-DRIFT")
        evaluation = self._persist_request(request, case_id, "CASE-REPLAY-DRIFT")
        with self.database.write() as connection:
            connection.execute(
                "UPDATE doi_case_projections SET "
                "projection_version=projection_version+1"
            )
        with self.assertRaises(DOIPersistenceError):
            self.service.append_snapshot_evaluation(
                case_id=case_id,
                snapshot=request.snapshot,
                evaluation=evaluation,
                created_at=request.evaluated_at,
            )
        self.assertIn(
            "DOI_CASE_PROJECTION_MISMATCH",
            self.service.verify_projections().errors,
        )

    def test_owner_exact_replay_rejects_normalized_state_drift(self) -> None:
        request = evaluation_input(
            split_lines(),
            evaluation_suffix="M4-OWNER-REPLAY-DRIFT",
            snapshot_suffix="M4-OWNER-REPLAY-DRIFT",
            run_suffix="M4-OWNER-REPLAY-DRIFT",
        )
        case_id = EvidenceId("SYN-EVIDENCE-DOI-M4-OWNER-REPLAY-DRIFT")
        evaluation = self._persist_request(request, case_id, "OWNER-REPLAY-DRIFT")
        values = {
            "stream_id": "SYN-EVIDENCE-DOI-M4-OWNER-REPLAY-STREAM",
            "current_state": "SET",
            "event": evaluation,
            "occurred_at": NOW,
            "case_id": case_id,
        }
        self.service.set_attention_cause(**values)
        with self.database.write() as connection:
            connection.execute(
                "UPDATE doi_owner_streams SET current_state='DRIFT' "
                "WHERE stream_family='ATTENTION'"
            )
        with self.assertRaises(DOIPersistenceError):
            self.service.set_attention_cause(**values)
        self.assertIn(
            "DOI_ATTENTION_PROJECTION_HISTORY_MISMATCH",
            self.service.verify_projections().errors,
        )

    def test_kpi_exact_replay_rejects_normalized_amount_drift(self) -> None:
        case_id, _, _, _, decision = self._substitution_graph()
        values = {
            "case_id": case_id,
            "event": decision.event,
            "contribution": decision.contribution,
        }
        self.service.append_kpi_contribution(**values)
        with self.database.write() as connection:
            connection.execute(
                "UPDATE doi_retained_kpi_contributions SET "
                "amount_minor_units=amount_minor_units+1"
            )
        with self.assertRaises(DOIPersistenceError):
            self.service.append_kpi_contribution(**values)
        self.assertIn(
            "DOI_KPI_PROJECTION_MISMATCH",
            self.service.verify_projections().errors,
        )

    def test_two_source_retries_compete_for_exact_next_ordinal(self) -> None:
        _, started, failed = self._persist_failed_attempt()
        first_control, _, _ = _failed_control()
        second_control, _, _ = _failed_control()
        first_command = _command_id("M4-RETRY-FIRST")
        second_command = _command_id("M4-RETRY-SECOND")
        accepted_at = CanonicalTimestamp("2026-08-10T12:01:01Z")
        first = first_control.retry_source_import(
            run_id=started.run.run_id,
            command_id=first_command,
            source_identity_id=_source_id(),
            accepted_at=accepted_at,
        )
        second = second_control.retry_source_import(
            run_id=started.run.run_id,
            command_id=second_command,
            source_identity_id=_source_id(),
            accepted_at=accepted_at,
        )
        with self.assertRaises(InjectedPersistenceFault):
            self.service.accept_retry(
                command_id=first_command,
                predecessor_attempt_id=failed.attempt_id,
                attempt=first,
                event=first_control.attempt_events(first.attempt_id)[0],
                run=first_control.run(first.run_id),
                accepted_at=accepted_at,
                fault_injector=FaultInjector(
                    frozenset({FaultPoint.BEFORE_COMMIT})
                ),
            )
        with self.database.read() as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM doi_run_control_receipts"
                ).fetchone()[0],
                0,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM doi_source_import_attempts "
                    "WHERE ordinal=2"
                ).fetchone()[0],
                0,
            )

        def submit(command: object, attempt: object, control: object) -> str:
            try:
                service = DOIPersistenceService(SQLiteDatabase(self.database.path))
                service.accept_retry(
                    command_id=command,  # type: ignore[arg-type]
                    predecessor_attempt_id=failed.attempt_id,
                    attempt=attempt,  # type: ignore[arg-type]
                    event=control.attempt_events(  # type: ignore[attr-defined]
                        attempt.attempt_id
                    )[0],
                    run=control.run(attempt.run_id),  # type: ignore[attr-defined]
                    accepted_at=accepted_at,
                )
            except DOIPersistenceConflict:
                return "REJECTED"
            return "COMMITTED"

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = tuple(
                pool.map(
                    lambda values: submit(*values),
                    (
                        (first_command, first, first_control),
                        (second_command, second, second_control),
                    ),
                )
            )
        self.assertEqual(sorted(outcomes), ["COMMITTED", "REJECTED"])
        with self.database.read() as connection:
            ordinals = tuple(
                row[0]
                for row in connection.execute(
                    "SELECT ordinal FROM doi_source_import_attempts ORDER BY ordinal"
                )
            )
            receipt_count = connection.execute(
                "SELECT COUNT(*) FROM doi_run_control_receipts WHERE operation='RETRY'"
            ).fetchone()[0]
        self.assertEqual(ordinals, (1, 2))
        self.assertEqual(receipt_count, 1)

    def test_retry_vs_explicit_no_retry_finalization_has_one_winner(self) -> None:
        _, started, failed = self._persist_failed_attempt()
        retry_control, _, _ = _failed_control()
        no_retry_control, _, no_retry_failed = _failed_control()
        retry_command = _command_id("M4-RETRY-RACE")
        accepted_at = CanonicalTimestamp("2026-08-10T12:02:00Z")
        retry = retry_control.retry_source_import(
            run_id=started.run.run_id,
            command_id=retry_command,
            source_identity_id=_source_id(),
            accepted_at=accepted_at,
        )
        no_retry_command = accept_no_retry_command(
            command_id=_command_id("M4-NO-RETRY-RACE"),
            run_id=started.run.run_id,
            greatest_failed_attempt_id=no_retry_failed.attempt_id,
            accepted_actor_id=RepId("SYN-REP-AUTHORIZED-0001"),
            accepted_at=accepted_at,
        )
        no_retry_receipt = no_retry_control.finalize_failed_source_import_no_retry(
            no_retry_command
        )
        with self.assertRaises(InjectedPersistenceFault):
            self.service.explicit_no_retry_finalization(
                command=no_retry_command,
                receipt=no_retry_receipt,
                run=no_retry_control.run(started.run.run_id),
                event=no_retry_control.run_events(started.run.run_id)[-1],
                fault_injector=FaultInjector(
                    frozenset({FaultPoint.BEFORE_COMMIT})
                ),
            )
        with self.database.read() as connection:
            receipt_count = connection.execute(
                "SELECT COUNT(*) FROM doi_run_control_receipts"
            ).fetchone()[0]
            status = connection.execute(
                "SELECT status FROM doi_run_projections"
            ).fetchone()[0]
        self.assertEqual(receipt_count, 0)
        self.assertEqual(status, RunStatus.IN_PROGRESS.value)

        def retry_submit() -> str:
            try:
                DOIPersistenceService(SQLiteDatabase(self.database.path)).accept_retry(
                    command_id=retry_command,
                    predecessor_attempt_id=failed.attempt_id,
                    attempt=retry,
                    event=retry_control.attempt_events(retry.attempt_id)[0],
                    run=retry_control.run(retry.run_id),
                    accepted_at=accepted_at,
                )
            except DOIPersistenceConflict:
                return "REJECTED"
            return "COMMITTED"

        def no_retry_submit() -> str:
            try:
                service = DOIPersistenceService(SQLiteDatabase(self.database.path))
                service.explicit_no_retry_finalization(
                    command=no_retry_command,
                    receipt=no_retry_receipt,
                    run=no_retry_control.run(started.run.run_id),
                    event=no_retry_control.run_events(started.run.run_id)[-1],
                )
            except DOIPersistenceConflict:
                return "REJECTED"
            return "COMMITTED"

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = tuple(pool.map(lambda fn: fn(), (retry_submit, no_retry_submit)))
        self.assertEqual(sorted(results), ["COMMITTED", "REJECTED"])
        with self.database.read() as connection:
            operations = tuple(
                row[0]
                for row in connection.execute(
                    "SELECT operation FROM doi_run_control_receipts"
                )
            )
            status = connection.execute(
                "SELECT status FROM doi_run_projections"
            ).fetchone()[0]
        self.assertEqual(len(operations), 1)
        expected = (
            RunStatus.IN_PROGRESS.value
            if operations == ("RETRY",)
            else RunStatus.FAILED.value
        )
        self.assertEqual(status, expected)

    def test_extraction_reservation_vs_rc084_has_one_winner(self) -> None:
        reserve_control, start = self._recheck_start("EXTRACTION-RACE")
        systemic_control, _ = self._recheck_start("EXTRACTION-RACE")
        self.service.invoke_run(start)
        reservation = reserve_control.reserve_extraction(
            run_id=start.run.run_id,
            occurrence_id=ExtractionOccurrenceId(
                InteractionId("SYN-INTERACTION-DOI-M4-EXTRACT-RACE")
            ),
            reserved_at=NOW,
        )
        systemic = systemic_control.fail_pre_extraction_rules_unavailable(
            run_id=start.run.run_id,
            command_id=AcceptedCommandId(
                InteractionId("SYN-INTERACTION-DOI-M4-RC084-RACE")
            ),
            occurred_at=NOW,
        )
        for operation, receipt in (
            (self.service.reserve_extraction, reservation),
            (self.service.pre_extraction_rules_unavailable, systemic),
        ):
            with self.subTest(rollback=operation.__name__):
                with self.assertRaises(InjectedPersistenceFault):
                    operation(
                        receipt,
                        fault_injector=FaultInjector(
                            frozenset({FaultPoint.BEFORE_COMMIT})
                        ),
                    )
        with self.database.read() as connection:
            receipt_count = connection.execute(
                "SELECT COUNT(*) FROM doi_run_control_receipts"
            ).fetchone()[0]
            status = connection.execute(
                "SELECT status FROM doi_run_projections"
            ).fetchone()[0]
        self.assertEqual(receipt_count, 0)
        self.assertEqual(status, RunStatus.IN_PROGRESS.value)

        def submit(kind: str) -> str:
            service = DOIPersistenceService(SQLiteDatabase(self.database.path))
            try:
                if kind == "RESERVE":
                    service.reserve_extraction(reservation)
                else:
                    service.pre_extraction_rules_unavailable(systemic)
            except DOIPersistenceConflict:
                return "REJECTED"
            return "COMMITTED"

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = tuple(pool.map(submit, ("RESERVE", "RC084")))
        self.assertEqual(sorted(results), ["COMMITTED", "REJECTED"])
        with self.database.read() as connection:
            operation = connection.execute(
                "SELECT operation FROM doi_run_control_receipts"
            ).fetchone()[0]
            status = connection.execute(
                "SELECT status FROM doi_run_projections"
            ).fetchone()[0]
        expected = (
            RunStatus.IN_PROGRESS.value
            if operation == "EXTRACTION_RESERVED"
            else RunStatus.FAILED.value
        )
        self.assertEqual(status, expected)

    def test_complete_extraction_populates_normalized_attempt_once(self) -> None:
        _, start = self._recheck_start("EXTRACTION-COMPLETE")
        self.service.invoke_run(start)
        registry = load_doi_registries()
        attempt = DOIExtractionAttempt(
            attempt_id=ExtractionAttemptId(
                InteractionId("SYN-INTERACTION-DOI-M4-EXTRACTION-ATTEMPT")
            ),
            run_id=DoiRunId(start.run.run_id),
            order_id=DoiOrderId(OrderId("SYN-ORDER-DOI-M4-RACE")),
            started_at=NOW,
            completed_at=NOW,
            status=ExtractionStatus.FAILED,
            snapshot_id=None,
            reasons=ReasonSet(
                tuple(
                    registry.reason_ref(code)
                    for code in ("RC-011", "RC-014", "RC-015")
                )
            ),
            portal_read_count=NonNegativeCount(1),
        )
        result = DOIExtractionResult(
            attempt,
            None,
            (AttentionCondition.RECHECK_REQUIRED,),
        )
        case_id = EvidenceId("SYN-EVIDENCE-DOI-M4-EXTRACTION-CASE")
        with self.assertRaises(InjectedPersistenceFault):
            self.service.complete_extraction(
                case_id=case_id,
                result=result,
                created_at=NOW,
                fault_injector=FaultInjector(
                    frozenset({FaultPoint.BEFORE_COMMIT})
                ),
            )
        with self.database.read() as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM doi_extraction_attempts"
                ).fetchone()[0],
                0,
            )
        first = self.service.complete_extraction(
            case_id=case_id,
            result=result,
            created_at=NOW,
        )
        replay = self.service.complete_extraction(
            case_id=case_id,
            result=result,
            created_at=NOW,
        )
        self.assertFalse(first.replayed)
        self.assertTrue(replay.replayed)
        with self.database.read() as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM doi_extraction_attempts"
                ).fetchone()[0],
                1,
            )

    def test_duplicate_evaluation_append_is_exactly_once(self) -> None:
        request = evaluation_input(
            split_lines(),
            evaluation_suffix="M4-DUPLICATE-EVALUATION",
            snapshot_suffix="M4-DUPLICATE-EVALUATION",
            run_suffix="M4-DUPLICATE-EVALUATION",
        )
        case_id = EvidenceId("SYN-EVIDENCE-DOI-M4-DUPLICATE-EVALUATION-CASE")
        evaluation = self._persist_request(request, case_id, "DUPLICATE")
        replay = self.service.append_snapshot_evaluation(
            case_id=case_id,
            snapshot=request.snapshot,
            evaluation=evaluation,
            created_at=request.evaluated_at,
        )
        self.assertTrue(replay.replayed)
        with self.database.read() as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM doi_evaluations"
                ).fetchone()[0],
                1,
            )

    def test_duplicate_intervention_and_action_occurrence_are_suppressed(self) -> None:
        case_id, _, intervention, _, _ = self._substitution_graph(
            persist_intervention=False
        )
        with self.assertRaises(InjectedPersistenceFault):
            self.service.verify_intervention_action(
                case_id=case_id,
                intervention=intervention,
                created_at=NOW,
                fault_injector=FaultInjector(
                    frozenset({FaultPoint.BEFORE_COMMIT})
                ),
            )
        first = self.service.verify_intervention_action(
            case_id=case_id,
            intervention=intervention,
            created_at=NOW,
        )
        replay = self.service.verify_intervention_action(
            case_id=case_id,
            intervention=intervention,
            created_at=NOW,
        )
        self.assertFalse(first.replayed)
        self.assertTrue(replay.replayed)
        with self.database.read() as connection:
            counts = tuple(
                connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in (
                    "doi_interventions",
                    "doi_action_verification_events",
                    "doi_value_events",
                )
            )
        self.assertEqual(counts, (1, 1, 1))

    def test_value_correction_and_reversal_append_without_rewriting_history(
        self,
    ) -> None:
        case_id, _, intervention, _, _ = self._substitution_graph()
        original = intervention.value_events[-1]
        with self.database.read() as connection:
            original_row = tuple(
                connection.execute(
                    "SELECT event_id, record_sha256, record_canonical_bytes "
                    "FROM doi_value_events WHERE intervention_id=?",
                    (intervention.intervention_id.value,),
                ).fetchone()
            )
        correction = _value_event(
            intervention=intervention,
            event_id="SYN-EVIDENCE-DOI-M4-VALUE-CORRECTION",
            event_type=ValueEventType.CORRECTION,
            cents=4_000,
            predecessor=original,
            correction_kind=ValueCorrectionKind.ORIGINAL_VALUE_CORRECTED,
            marker="M4-SQL",
        )
        corrected = append_value_event(intervention, correction).intervention
        with self.assertRaises(InjectedPersistenceFault):
            self.service.append_value_event(
                case_id=case_id,
                intervention=corrected,
                created_at=NOW,
                fault_injector=FaultInjector(
                    frozenset({FaultPoint.BEFORE_COMMIT})
                ),
            )
        with self.database.read() as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM doi_value_events"
                ).fetchone()[0],
                1,
            )
        self.service.append_value_event(
            case_id=case_id,
            intervention=corrected,
            created_at=NOW,
        )
        reversal = _value_event(
            intervention=corrected,
            event_id="SYN-EVIDENCE-DOI-M4-VALUE-REVERSAL",
            event_type=ValueEventType.PARTIAL_REVERSAL,
            cents=500,
            predecessor=correction,
            marker="M4-SQL",
        )
        reversed_intervention = append_value_event(
            corrected,
            reversal,
        ).intervention
        first = self.service.append_value_event(
            case_id=case_id,
            intervention=reversed_intervention,
            created_at=NOW,
        )
        replay = self.service.append_value_event(
            case_id=case_id,
            intervention=reversed_intervention,
            created_at=NOW,
        )
        self.assertFalse(first.replayed)
        self.assertTrue(replay.replayed)
        with self.database.read() as connection:
            rows = tuple(
                tuple(row)
                for row in connection.execute(
                    "SELECT sequence_no, event_id, event_type, predecessor_sha256 "
                    "FROM doi_value_events WHERE intervention_id=? "
                    "ORDER BY sequence_no",
                    (intervention.intervention_id.value,),
                ).fetchall()
            )
            retained_original = tuple(
                connection.execute(
                    "SELECT event_id, record_sha256, record_canonical_bytes "
                    "FROM doi_value_events WHERE intervention_id=? "
                    "AND sequence_no=1",
                    (intervention.intervention_id.value,),
                ).fetchone()
            )
        self.assertEqual(retained_original, original_row)
        self.assertEqual(
            tuple((row[0], row[1], row[2]) for row in rows),
            (
                (
                    1,
                    original.event_id.value,
                    ValueEventType.INITIAL_VERIFIED_VALUE.value,
                ),
                (2, correction.event_id.value, ValueEventType.CORRECTION.value),
                (3, reversal.event_id.value, ValueEventType.PARTIAL_REVERSAL.value),
            ),
        )
        self.assertIsNone(rows[0][3])
        self.assertEqual(rows[1][3], original.hash_binding().sha256)
        self.assertEqual(rows[2][3], correction.hash_binding().sha256)
        self.assertTrue(self.service.verify_projections().ok)

    def test_result_search_and_link_use_normalized_histories(self) -> None:
        case_id, _, intervention, link, _ = self._substitution_graph()
        first_link = self.service.link_resulting_order(
            case_id=case_id,
            link=link,
            created_at=NOW,
        )
        replay_link = self.service.link_resulting_order(
            case_id=case_id,
            link=link,
            created_at=NOW,
        )
        self.assertFalse(first_link.replayed)
        self.assertTrue(replay_link.replayed)
        search_id = EvidenceId("SYN-EVIDENCE-DOI-M4-RESULT-SEARCH")
        evidence = ResultingLinkSearchEvidence.from_complete_search(
            evidence_id=EvidenceId("SYN-EVIDENCE-DOI-M4-RESULT-SEARCH-EVIDENCE"),
            search_id=search_id,
            parent_order_id=link.parent_order_id,
            intervention_type=intervention.intervention_type,
            candidate_order_ids=(),
            disproved_candidate_order_ids=(),
            observed_at=NOW,
            source=intervention_order_source(
                link.parent_order_id,
                "M4-RESULT-SEARCH",
            ),
        )
        history = DOIResultingOrderLinkSearchHistory(
            search_id=search_id,
            parent_order_id=link.parent_order_id,
            intervention_type=intervention.intervention_type,
        )
        reduced = append_resulting_link_search(
            history,
            event_id=EvidenceId("SYN-EVIDENCE-DOI-M4-RESULT-SEARCH-EVENT"),
            evidence=evidence,
        )
        self.service.search_resulting_order(
            case_id=case_id,
            history=reduced.history,
            created_at=NOW,
        )
        replay = self.service.search_resulting_order(
            case_id=case_id,
            history=reduced.history,
            created_at=NOW,
        )
        self.assertTrue(replay.replayed)
        with self.database.read() as connection:
            counts = tuple(
                connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in (
                    "doi_resulting_order_searches",
                    "doi_resulting_order_search_events",
                    "doi_resulting_order_links",
                    "doi_resulting_order_link_revisions",
                    "doi_resulting_order_mapping_components",
                )
            )
        self.assertEqual(counts, (1, 1, 1, 1, 1))

    def test_link_mapping_child_is_immutable_and_deep_verified(self) -> None:
        case_id, _, _, link, _ = self._substitution_graph()
        self.service.link_resulting_order(
            case_id=case_id,
            link=link,
            created_at=NOW,
        )
        with self.assertRaisesRegex(
            sqlite3.IntegrityError,
            "DOI_IMMUTABLE_RECORD",
        ):
            with self.database.write() as connection:
                connection.execute(
                    "UPDATE doi_resulting_order_mapping_components "
                    "SET ordinal=ordinal"
                )
        with self.database.write() as connection:
            connection.execute(
                "DELETE FROM doi_resulting_order_mapping_components"
            )
        self.assertIn(
            "DOI_RESULTING_LINK_CHILD_MISMATCH",
            self.service.verify_projections().errors,
        )

    def test_projection_replays_reject_tampered_intervention_result_and_kpi_heads(
        self,
    ) -> None:
        case_id, _, intervention, link, decision = self._substitution_graph()
        history = self._result_search_history(intervention, link, "CAS")
        self.service.link_resulting_order(
            case_id=case_id,
            link=link,
            created_at=NOW,
        )
        self.service.search_resulting_order(
            case_id=case_id,
            history=history,
            created_at=NOW,
        )
        self.service.append_kpi_contribution(
            case_id=case_id,
            event=decision.event,
            contribution=decision.contribution,
        )
        with self.database.write() as connection:
            connection.execute(
                "UPDATE doi_interventions SET head_sha256=?",
                ("a" * 64,),
            )
            connection.execute(
                "UPDATE doi_resulting_order_searches SET head_sha256=?",
                ("b" * 64,),
            )
            connection.execute(
                "UPDATE doi_resulting_order_links SET head_sha256=?",
                ("c" * 64,),
            )
            connection.execute(
                "UPDATE doi_retained_kpi_contributions SET head_sha256=?",
                ("d" * 64,),
            )
        with self.assertRaises(DOIPersistenceError):
            self.service.record_intervention(
                case_id=case_id,
                intervention=intervention,
                created_at=NOW,
            )
        with self.assertRaises(DOIPersistenceConflict):
            self.service.search_resulting_order(
                case_id=case_id,
                history=history,
                created_at=NOW,
            )
        with self.assertRaises(DOIPersistenceConflict):
            self.service.link_resulting_order(
                case_id=case_id,
                link=link,
                created_at=NOW,
            )
        with self.assertRaises(DOIPersistenceConflict):
            self.service.append_kpi_contribution(
                case_id=case_id,
                event=decision.event,
                contribution=decision.contribution,
            )

    def test_required_doi_service_operations_roll_back_at_before_commit(self) -> None:
        case_id, _, intervention, link, decision = self._substitution_graph(
            persist_intervention=False
        )
        fault = FaultInjector(frozenset({FaultPoint.BEFORE_COMMIT}))
        with self.assertRaises(InjectedPersistenceFault):
            self.service.record_intervention(
                case_id=case_id,
                intervention=intervention,
                created_at=NOW,
                fault_injector=fault,
            )
        with self.database.read() as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM doi_interventions"
                ).fetchone()[0],
                0,
            )
        self.service.record_intervention(
            case_id=case_id,
            intervention=intervention,
            created_at=NOW,
        )
        history = self._result_search_history(intervention, link, "FAULT")
        operations = (
            (
                self.service.link_resulting_order,
                {"case_id": case_id, "link": link, "created_at": NOW},
                "doi_resulting_order_links",
            ),
            (
                self.service.search_resulting_order,
                {"case_id": case_id, "history": history, "created_at": NOW},
                "doi_resulting_order_searches",
            ),
            (
                self.service.append_kpi_contribution,
                {
                    "case_id": case_id,
                    "event": decision.event,
                    "contribution": decision.contribution,
                },
                "doi_retained_kpi_contributions",
            ),
        )
        for operation, values, table in operations:
            with self.subTest(operation=operation.__name__):
                with self.assertRaises(InjectedPersistenceFault):
                    operation(
                        **values,
                        fault_injector=FaultInjector(
                            frozenset({FaultPoint.BEFORE_COMMIT})
                        ),
                    )
                with self.database.read() as connection:
                    self.assertEqual(
                        connection.execute(
                            f"SELECT COUNT(*) FROM {table}"
                        ).fetchone()[0],
                        0,
                    )
        owner_operations = (
            self.service.apply_lifecycle_transition,
            self.service.set_attention_cause,
            self.service.clear_attention_cause,
            self.service.record_human_fact,
            self.service.record_contact_event,
            self.service.record_wwc_event,
            self.service.record_dedupe_event,
        )
        for index, operation in enumerate(owner_operations, start=1):
            with self.subTest(operation=operation.__name__):
                with self.assertRaises(InjectedPersistenceFault):
                    operation(
                        stream_id=f"SYN-EVIDENCE-DOI-M4-FAULT-STREAM-{index}",
                        current_state="TEST",
                        event=intervention,
                        occurred_at=NOW,
                        case_id=case_id,
                        fault_injector=FaultInjector(
                            frozenset({FaultPoint.BEFORE_COMMIT})
                        ),
                    )
        with self.database.read() as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM doi_owner_events"
                ).fetchone()[0],
                0,
            )

    def test_duplicate_kpi_contribution_is_exactly_once(self) -> None:
        case_id, _, _, _, decision = self._substitution_graph()
        first = self.service.append_kpi_contribution(
            case_id=case_id,
            event=decision.event,
            contribution=decision.contribution,
        )
        replay = self.service.append_kpi_contribution(
            case_id=case_id,
            event=decision.event,
            contribution=decision.contribution,
        )
        self.assertFalse(first.replayed)
        self.assertTrue(replay.replayed)
        with self.database.read() as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM doi_kpi_contribution_events"
                ).fetchone()[0],
                1,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM doi_retained_kpi_contributions"
                ).fetchone()[0],
                1,
            )

    def test_kpi_daily_bucket_storage_is_currency_segmented(self) -> None:
        statement = (
            "INSERT INTO doi_kpi_daily_buckets"
            "(action_date, intervention_type, currency_code, "
            "currency_registry_version, currency_scale, amount_minor_units, "
            "intervention_count) VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(action_date, intervention_type, currency_code, "
            "currency_registry_version, currency_scale) DO UPDATE SET "
            "amount_minor_units=amount_minor_units+excluded.amount_minor_units, "
            "intervention_count=intervention_count+excluded.intervention_count"
        )
        substitution = InterventionType.PRODUCT_SUBSTITUTION.value
        with self.database.write() as connection:
            connection.execute(
                statement,
                (
                    "2026-08-20",
                    substitution,
                    "USD",
                    CURRENCY_REGISTRY_VERSION,
                    2,
                    4_321,
                    1,
                ),
            )
            connection.execute(
                statement,
                (
                    "2026-08-20",
                    substitution,
                    "JPY",
                    CURRENCY_REGISTRY_VERSION,
                    0,
                    500,
                    1,
                ),
            )
            connection.execute(
                statement,
                (
                    "2026-08-20",
                    substitution,
                    "USD",
                    CURRENCY_REGISTRY_VERSION,
                    2,
                    679,
                    1,
                ),
            )
        with self.database.read() as connection:
            rows = tuple(
                tuple(row)
                for row in connection.execute(
                    "SELECT currency_code, currency_scale, amount_minor_units, "
                    "intervention_count FROM doi_kpi_daily_buckets "
                    "ORDER BY currency_code"
                ).fetchall()
            )
        self.assertEqual(rows, (("JPY", 0, 500, 1), ("USD", 2, 5_000, 2)))

    def test_projection_verifier_reconciles_run_event_history(self) -> None:
        request = evaluation_input(
            split_lines(),
            evaluation_suffix="M4-RUN-PROJECTION",
            snapshot_suffix="M4-RUN-PROJECTION",
            run_suffix="M4-RUN-PROJECTION",
        )
        self._persist_request(
            request,
            EvidenceId("SYN-EVIDENCE-DOI-M4-RUN-PROJECTION-CASE"),
            "RUN-PROJECTION",
        )
        self.assertTrue(self.service.verify_projections().ok)
        with self.database.write() as connection:
            connection.execute(
                "UPDATE doi_run_projections SET status='FAILED', completed_at=?, "
                "purge_eligible_at=?",
                (NOW.value, NOW.value),
            )
        self.assertIn(
            "DOI_RUN_PROJECTION_RECORD_MISMATCH",
            self.service.verify_projections().errors,
        )

    def test_projection_verifier_reconciles_case_lifecycle_history(self) -> None:
        request = evaluation_input(
            split_lines(),
            evaluation_suffix="M4-CASE-PROJECTION",
            snapshot_suffix="M4-CASE-PROJECTION",
            run_suffix="M4-CASE-PROJECTION",
        )
        self._persist_request(
            request,
            EvidenceId("SYN-EVIDENCE-DOI-M4-CASE-PROJECTION-CASE"),
            "CASE-PROJECTION",
        )
        with self.database.write() as connection:
            connection.execute(
                "UPDATE doi_case_projections SET "
                "lifecycle_state='CLOSED_REVERSIBLE', "
                "terminal_closure_reason='REP_TRANSFERRED'"
            )
        self.assertIn(
            "DOI_CASE_PROJECTION_MISMATCH",
            self.service.verify_projections().errors,
        )

    def test_projection_verifier_reconciles_attention_event_history(self) -> None:
        request = evaluation_input(
            split_lines(),
            evaluation_suffix="M4-ATTENTION-PROJECTION",
            snapshot_suffix="M4-ATTENTION-PROJECTION",
            run_suffix="M4-ATTENTION-PROJECTION",
        )
        case_id = EvidenceId("SYN-EVIDENCE-DOI-M4-ATTENTION-PROJECTION-CASE")
        evaluation = self._persist_request(
            request,
            case_id,
            "ATTENTION-PROJECTION",
        )
        self.service.set_attention_cause(
            stream_id="SYN-EVIDENCE-DOI-M4-ATTENTION-STREAM",
            current_state="SET",
            event=evaluation,
            occurred_at=NOW,
            case_id=case_id,
        )
        self.assertTrue(self.service.verify_projections().ok)
        with self.database.write() as connection:
            connection.execute(
                "UPDATE doi_owner_streams SET projection_payload=? "
                "WHERE stream_family='ATTENTION'",
                (b"drift",),
            )
        self.assertIn(
            "DOI_ATTENTION_PROJECTION_HISTORY_MISMATCH",
            self.service.verify_projections().errors,
        )

    def test_projection_verifier_reconciles_intervention_and_value_history(self) -> None:
        self._substitution_graph()
        self.assertTrue(self.service.verify_projections().ok)
        with self.database.write() as connection:
            connection.execute(
                "UPDATE doi_interventions SET status='REVERSED'"
            )
        self.assertIn(
            "DOI_INTERVENTION_VALUE_PROJECTION_MISMATCH",
            self.service.verify_projections().errors,
        )

    def test_projection_verifier_detects_missing_value_event(self) -> None:
        self._substitution_graph()
        with self.database.write() as connection:
            connection.execute("DELETE FROM doi_value_events")
        self.assertIn(
            "DOI_INTERVENTION_VALUE_PROJECTION_MISMATCH",
            self.service.verify_projections().errors,
        )

    def test_projection_verifier_detects_deleted_run_projection(self) -> None:
        _, start = self._recheck_start("DELETE-RUN-PROJECTION")
        self.service.invoke_run(start)
        with self.database.write() as connection:
            connection.execute("DELETE FROM doi_run_projections")
        self.assertIn(
            "DOI_RUN_PROJECTION_COMPLETENESS_MISMATCH",
            self.service.verify_projections().errors,
        )

    def test_projection_verifier_detects_deleted_case_projection(self) -> None:
        request = evaluation_input(
            split_lines(),
            evaluation_suffix="M4-DELETE-CASE-PROJECTION",
            snapshot_suffix="M4-DELETE-CASE-PROJECTION",
            run_suffix="M4-DELETE-CASE-PROJECTION",
        )
        self._persist_request(
            request,
            EvidenceId("SYN-EVIDENCE-DOI-M4-DELETE-CASE-PROJECTION"),
            "DELETE-CASE-PROJECTION",
        )
        with self.database.write() as connection:
            connection.execute("DELETE FROM doi_case_projections")
        self.assertIn(
            "DOI_CASE_PROJECTION_COMPLETENESS_MISMATCH",
            self.service.verify_projections().errors,
        )

    def test_projection_verifier_detects_deleted_owner_projection(self) -> None:
        request = evaluation_input(
            split_lines(),
            evaluation_suffix="M4-DELETE-OWNER-PROJECTION",
            snapshot_suffix="M4-DELETE-OWNER-PROJECTION",
            run_suffix="M4-DELETE-OWNER-PROJECTION",
        )
        case_id = EvidenceId("SYN-EVIDENCE-DOI-M4-DELETE-OWNER-PROJECTION")
        evaluation = self._persist_request(
            request,
            case_id,
            "DELETE-OWNER-PROJECTION",
        )
        self.service.set_attention_cause(
            stream_id="SYN-EVIDENCE-DOI-M4-DELETE-OWNER-STREAM",
            current_state="SET",
            event=evaluation,
            occurred_at=NOW,
            case_id=case_id,
        )
        with self.database.write() as connection:
            connection.execute(
                "DELETE FROM doi_owner_streams WHERE stream_family='ATTENTION'"
            )
        self.assertIn(
            "DOI_OWNER_PROJECTION_COMPLETENESS_MISMATCH",
            self.service.verify_projections().errors,
        )

    def test_projection_verifier_detects_deleted_intervention_projection(self) -> None:
        self._substitution_graph()
        with self.database.write() as connection:
            connection.execute("DELETE FROM doi_interventions")
        self.assertIn(
            "DOI_ARTIFACT_PROJECTION_COMPLETENESS_MISMATCH",
            self.service.verify_projections().errors,
        )

    def test_projection_verifier_detects_deleted_extraction_projection(self) -> None:
        self._persist_failed_extraction("DELETE-PROJECTION")
        with self.database.write() as connection:
            connection.execute("DELETE FROM doi_extraction_attempts")
        self.assertIn(
            "DOI_ARTIFACT_PROJECTION_COMPLETENESS_MISMATCH",
            self.service.verify_projections().errors,
        )

    def test_projection_verifier_detects_deleted_result_search_projection(self) -> None:
        case_id, _, intervention, link, _ = self._substitution_graph()
        history = self._result_search_history(intervention, link, "DELETE")
        self.service.search_resulting_order(
            case_id=case_id,
            history=history,
            created_at=NOW,
        )
        with self.database.write() as connection:
            connection.execute("DELETE FROM doi_resulting_order_searches")
        self.assertIn(
            "DOI_RESULTING_PROJECTION_COMPLETENESS_MISMATCH",
            self.service.verify_projections().errors,
        )

    def test_projection_verifier_detects_deleted_result_link_projection(self) -> None:
        case_id, _, _, link, _ = self._substitution_graph()
        self.service.link_resulting_order(
            case_id=case_id,
            link=link,
            created_at=NOW,
        )
        with self.database.write() as connection:
            connection.execute("DELETE FROM doi_resulting_order_links")
        self.assertIn(
            "DOI_RESULTING_PROJECTION_COMPLETENESS_MISMATCH",
            self.service.verify_projections().errors,
        )

    def test_source_disappearance_is_monitor_not_closure(self) -> None:
        request = evaluation_input(
            split_lines(),
            evaluation_suffix="M4-SOURCE-DISAPPEARANCE",
            snapshot_suffix="M4-SOURCE-DISAPPEARANCE",
            run_suffix="M4-SOURCE-DISAPPEARANCE",
            order_state=OrderState.SHIPPED,
        )
        absent = dataclasses.replace(
            request.snapshot,
            source_presence=SourcePresence.ABSENT_RECHECK_REQUIRED,
        )
        absent_request = DOIEvaluationInput(
            evaluation_id=request.evaluation_id,
            snapshot=absent,
            evaluated_at=request.evaluated_at,
        )
        case_id = EvidenceId("SYN-EVIDENCE-DOI-M4-SOURCE-ABSENCE-CASE")
        evaluation = self._persist_request(absent_request, case_id, "ABSENCE")
        self.assertIsNone(evaluation.closure_proposal)
        with self.database.read() as connection:
            projection = connection.execute(
                "SELECT lifecycle_state FROM doi_case_projections"
            ).fetchone()[0]
            deadlines = connection.execute(
                "SELECT COUNT(*) FROM doi_retention_deadlines"
            ).fetchone()[0]
        self.assertEqual(projection, CaseLifecycleState.ACTIVE.value)
        self.assertEqual(deadlines, 0)

    def test_hard_closure_cannot_reopen_in_persistence(self) -> None:
        case_id = EvidenceId("SYN-EVIDENCE-DOI-M4-HARD-CASE")
        closed = evaluation_input(
            split_lines(),
            evaluation_suffix="M4-HARD-CLOSED",
            snapshot_suffix="M4-HARD-CLOSED",
            run_suffix="M4-HARD-CLOSED",
            order_state=OrderState.SHIPPED,
        )
        evaluation = self._persist_request(closed, case_id, "HARD-CLOSED")
        assert evaluation.closure_proposal is not None
        retention = schedule_retention(
            case_id=case_id,
            closure_event_id=EvidenceId("SYN-EVIDENCE-DOI-M4-HARD-CLOSURE"),
            lifecycle_state=evaluation.closure_proposal.lifecycle_state,
            closure_reason=evaluation.closure_proposal.reason,
            closed_at=closed.evaluated_at,
            projection_revision=1,
            projection_sha256=evaluation.hash_binding().sha256,
        )
        with self.assertRaises(InjectedPersistenceFault):
            self.service.schedule_retention(
                retention,
                created_at=closed.evaluated_at,
                fault_injector=FaultInjector(
                    frozenset({FaultPoint.BEFORE_COMMIT})
                ),
            )
        with self.database.read() as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM doi_retention_deadlines"
                ).fetchone()[0],
                0,
            )
        self.service.schedule_retention(retention, created_at=closed.evaluated_at)
        active = evaluation_input(
            split_lines(),
            evaluation_suffix="M4-HARD-REOPEN",
            snapshot_suffix="M4-HARD-REOPEN",
            run_suffix="M4-HARD-REOPEN",
        )
        control = InMemoryDOIRunControl()
        start = control.begin_recheck_run(
            run_id=active.snapshot.run_id.value,
            invocation_id=RunInvocationId(
                InteractionId("SYN-INTERACTION-DOI-M4-HARD-REOPEN")
            ),
            run_type=RunType.RECHECK_ORDER,
            order_id=active.snapshot.order_id.value,
            accepted_at=active.evaluated_at,
        )
        self.service.invoke_run(start)
        with self.assertRaisesRegex(
            DOIPersistenceConflict,
            "DOI_HARD_CLOSURE_REOPEN_FORBIDDEN",
        ):
            self.service.append_snapshot_evaluation(
                case_id=case_id,
                snapshot=active.snapshot,
                evaluation=evaluate_doi(active),
                created_at=active.evaluated_at,
            )
        with self.assertRaisesRegex(Exception, "HARD_CLOSURE_CANNOT_REOPEN"):
            cancel_retention_on_reopen(
                retention,
                supplied_binding=retention.binding,
                reopen_event_id=EvidenceId("SYN-EVIDENCE-DOI-M4-HARD-REOPEN"),
            )

    def test_reversible_reopen_cancels_only_exact_active_deadline(self) -> None:
        case_id = EvidenceId("SYN-EVIDENCE-DOI-M4-REVERSIBLE-CASE")
        closed = evaluation_input(
            split_lines(),
            evaluation_suffix="M4-REVERSIBLE-CLOSED",
            snapshot_suffix="M4-REVERSIBLE-CLOSED",
            run_suffix="M4-REVERSIBLE-CLOSED",
            rep_relation=RepRelation.OTHER_REP,
        )
        evaluation = self._persist_request(closed, case_id, "REVERSIBLE-CLOSED")
        assert evaluation.closure_proposal is not None
        retention = schedule_retention(
            case_id=case_id,
            closure_event_id=EvidenceId("SYN-EVIDENCE-DOI-M4-REVERSIBLE-CLOSURE"),
            lifecycle_state=evaluation.closure_proposal.lifecycle_state,
            closure_reason=evaluation.closure_proposal.reason,
            closed_at=closed.evaluated_at,
            projection_revision=1,
            projection_sha256=evaluation.hash_binding().sha256,
        )
        self.service.schedule_retention(retention, created_at=closed.evaluated_at)
        reopen_id = EvidenceId("SYN-EVIDENCE-DOI-M4-REVERSIBLE-REOPEN")
        canceled = cancel_retention_on_reopen(
            retention,
            supplied_binding=retention.binding,
            reopen_event_id=reopen_id,
        )
        active_source = order_source(OrderId("SYN-ORDER-DOI-0001"))
        active = evaluation_input(
            (
                make_line(
                    11,
                    active_source,
                    availability=LineAvailability.IN_STOCK,
                    quantity_availability=QuantityAvailability.FULL,
                    explicitly_available=2,
                ),
                make_line(12, active_source),
            ),
            evaluation_suffix="M4-REVERSIBLE-REOPEN",
            snapshot_suffix="M4-REVERSIBLE-REOPEN",
            run_suffix="M4-REVERSIBLE-REOPEN",
        )
        control = InMemoryDOIRunControl()
        start = control.begin_recheck_run(
            run_id=active.snapshot.run_id.value,
            invocation_id=RunInvocationId(
                InteractionId("SYN-INTERACTION-DOI-M4-REVERSIBLE-REOPEN")
            ),
            run_type=RunType.RECHECK_ORDER,
            order_id=active.snapshot.order_id.value,
            accepted_at=active.evaluated_at,
        )
        self.service.invoke_run(start)
        active_evaluation = evaluate_doi(active)
        with self.assertRaises(InjectedPersistenceFault):
            self.service.reopen_case(
                case_id=case_id,
                canceled_retention=canceled,
                snapshot=active.snapshot,
                evaluation=active_evaluation,
                created_at=active.evaluated_at,
                fault_injector=FaultInjector(
                    frozenset({FaultPoint.BEFORE_COMMIT})
                ),
            )
        with self.database.read() as connection:
            rolled_back = connection.execute(
                "SELECT p.lifecycle_state, d.canceled_by_reopen_event_id "
                "FROM doi_case_projections p JOIN doi_retention_deadlines d "
                "ON d.case_id=p.case_id"
            ).fetchone()
        self.assertEqual(
            tuple(rolled_back),
            (CaseLifecycleState.CLOSED_REVERSIBLE.value, None),
        )
        first = self.service.reopen_case(
            case_id=case_id,
            canceled_retention=canceled,
            snapshot=active.snapshot,
            evaluation=active_evaluation,
            created_at=active.evaluated_at,
        )
        replay = self.service.reopen_case(
            case_id=case_id,
            canceled_retention=canceled,
            snapshot=active.snapshot,
            evaluation=active_evaluation,
            created_at=active.evaluated_at,
        )
        self.assertFalse(first.replayed)
        self.assertTrue(replay.replayed)
        with self.database.read() as connection:
            row = connection.execute(
                "SELECT p.lifecycle_state, d.canceled_by_reopen_event_id "
                "FROM doi_case_projections p JOIN doi_retention_deadlines d "
                "ON d.case_id=p.case_id"
            ).fetchone()
        self.assertEqual(tuple(row), (CaseLifecycleState.ACTIVE.value, reopen_id.value))

    def _hard_case_for_purge(self, suffix: str):  # type: ignore[no-untyped-def]
        case_id = EvidenceId(f"SYN-EVIDENCE-DOI-M4-{suffix}-CASE")
        request = evaluation_input(
            split_lines(),
            evaluation_suffix=f"M4-{suffix}",
            snapshot_suffix=f"M4-{suffix}",
            run_suffix=f"M4-{suffix}",
            order_state=OrderState.SHIPPED,
        )
        evaluation = self._persist_request(request, case_id, suffix)
        assert evaluation.closure_proposal is not None
        retention = schedule_retention(
            case_id=case_id,
            closure_event_id=EvidenceId(f"SYN-EVIDENCE-DOI-M4-{suffix}-CLOSURE"),
            lifecycle_state=evaluation.closure_proposal.lifecycle_state,
            closure_reason=evaluation.closure_proposal.reason,
            closed_at=request.evaluated_at,
            projection_revision=1,
            projection_sha256=evaluation.hash_binding().sha256,
        )
        self.service.schedule_retention(retention, created_at=request.evaluated_at)
        return case_id, request, retention

    def test_concurrent_purge_is_one_delete_and_one_absence_noop(self) -> None:
        case_id, _, retention = self._hard_case_for_purge("CONCURRENT-PURGE")

        def purge() -> bool:
            service = DOIPersistenceService(SQLiteDatabase(self.database.path))
            return service.finalize_kpi_and_purge_case(
                case_id,
                now=retention.purge_eligible_at,
            ).deleted

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = sorted(pool.map(lambda _: purge(), range(2)))
        self.assertEqual(results, [False, True])
        with self.database.read() as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM doi_cases").fetchone()[0],
                0,
            )

    def test_kpi_finalization_fault_rolls_back_then_purge_is_identity_free(self) -> None:
        case_id, request, _, _, decision = self._substitution_graph()
        self.service.append_kpi_contribution(
            case_id=case_id,
            event=decision.event,
            contribution=decision.contribution,
        )
        closed = evaluation_input(
            request.snapshot.lines,
            evaluation_suffix="M4-KPI-CLOSED",
            snapshot_suffix="M4-KPI-CLOSED",
            run_suffix="M4-KPI-CLOSED",
            order_state=OrderState.SHIPPED,
        )
        closed_evaluation = self._persist_request(closed, case_id, "KPI-CLOSED")
        assert closed_evaluation.closure_proposal is not None
        retention = schedule_retention(
            case_id=case_id,
            closure_event_id=EvidenceId("SYN-EVIDENCE-DOI-M4-KPI-CLOSURE"),
            lifecycle_state=closed_evaluation.closure_proposal.lifecycle_state,
            closure_reason=closed_evaluation.closure_proposal.reason,
            closed_at=closed.evaluated_at,
            projection_revision=2,
            projection_sha256=closed_evaluation.hash_binding().sha256,
        )
        self.service.schedule_retention(retention, created_at=closed.evaluated_at)
        order_id = request.snapshot.order_id.to_json_value()
        with self.assertRaises(InjectedPersistenceFault):
            self.service.finalize_kpi_and_purge_case(
                case_id,
                now=retention.purge_eligible_at,
                fault_injector=FaultInjector(
                    frozenset({FaultPoint.DURING_KPI_FINALIZATION})
                ),
            )
        self.assertGreater(self.service.identity_occurrences(order_id), 0)
        with self.database.read() as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM doi_kpi_daily_buckets"
                ).fetchone()[0],
                0,
            )
        result = self.service.finalize_kpi_and_purge_case(
            case_id,
            now=retention.purge_eligible_at,
        )
        replay = self.service.finalize_kpi_and_purge_case(
            case_id,
            now=retention.purge_eligible_at,
        )
        self.assertTrue(result.deleted)
        self.assertEqual(result.finalized_contribution_count, 1)
        self.assertFalse(replay.deleted)
        self.assertEqual(self.service.identity_occurrences(order_id), 0)
        with self.database.read() as connection:
            bucket = tuple(
                connection.execute(
                    "SELECT amount_minor_units, intervention_count "
                    "FROM doi_kpi_daily_buckets"
                ).fetchone()
            )
        self.assertEqual(bucket, (4_321, 1))


if __name__ == "__main__":
    unittest.main()
