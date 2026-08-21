from __future__ import annotations

import dataclasses
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from synthetic_sales_assist.doi.identities import (
    AcceptedCommandId,
    ExtractionOccurrenceId,
    RunInvocationId,
    SourceBatchId,
    SourceIdentityId,
    SourceRowRefId,
)
from synthetic_sales_assist.doi.source import (
    DOIRejectedSourceRecord,
    DOIRunCounts,
    DOIRunWorkDisposition,
    DOISourceError,
    DOISourceRowCounts,
    FinalizeFailedSourceImportNoRetryCommand,
    InMemoryDOIRunControl,
    InMemorySourceBatchRegistry,
    RunControlConflict,
    RunStatus,
    RunType,
    RunWorkDispositionKind,
    SOURCE_ANCHORS,
    SOURCE_MAPPING_VERSION,
    SourceImportAttemptState,
    SourceImportResultKind,
    SyntheticQueueImage,
    SyntheticQueueRow,
    SyntheticQueueTab,
    TARGET_ASSIGNEE,
    accept_no_retry_command,
    classify_assignee,
    ingest_synthetic_queue,
    normalize_synthetic_order_number,
    source_hash_fixture_records,
)
from synthetic_sales_assist.doi.retention import calendar90
from synthetic_sales_assist.domain.canonical import (
    CanonicalHashCollision,
    canonical_json_bytes,
    domain_hash,
)
from synthetic_sales_assist.domain.identities import (
    EvidenceId,
    InteractionId,
    OrderId,
    RepId,
    RunId,
)
from synthetic_sales_assist.domain.numeric import NonNegativeCount
from synthetic_sales_assist.domain.records import ReasonSet
from synthetic_sales_assist.domain.registries import load_doi_registries
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp


def _source_id(suffix: str = "0001") -> SourceIdentityId:
    return SourceIdentityId(EvidenceId(f"SYN-EVIDENCE-DOI-SOURCE-{suffix}"))


def _batch_id(suffix: str = "0001") -> SourceBatchId:
    return SourceBatchId(EvidenceId(f"SYN-EVIDENCE-DOI-BATCH-{suffix}"))


def _row(
    ordinal: int,
    order_number: object,
    assignee: object = TARGET_ASSIGNEE,
) -> SyntheticQueueRow:
    return SyntheticQueueRow(
        order_number,
        assignee,
        SourceRowRefId(EvidenceId(f"SYN-EVIDENCE-DOI-ROW-{ordinal:04d}")),
    )


def _image(
    rows: tuple[SyntheticQueueRow, ...],
    *,
    revision: str | None = "REV-0001",
    accessible: bool = True,
    mapping_version: str = SOURCE_MAPPING_VERSION,
    anchors: tuple[str, ...] = SOURCE_ANCHORS,
    extent: int | None = None,
) -> SyntheticQueueImage:
    return SyntheticQueueImage(
        _source_id(),
        mapping_version,
        anchors,
        NonNegativeCount(len(rows) if extent is None else extent),
        rows,
        revision,
        accessible,
    )


def _command_id(suffix: str) -> AcceptedCommandId:
    return AcceptedCommandId(InteractionId(f"SYN-INTERACTION-DOI-COMMAND-{suffix}"))


def _review_start(control: InMemoryDOIRunControl, suffix: str = "0001"):
    return control.begin_review_run(
        run_id=RunId(f"SYN-RUN-DOI-{suffix}"),
        invocation_id=RunInvocationId(
            InteractionId(f"SYN-INTERACTION-DOI-RUN-{suffix}")
        ),
        source_identity_id=_source_id(suffix),
        locked_tab=SyntheticQueueTab.MONDAY,
        tab_confirmed=True,
        accepted_at=CanonicalTimestamp("2026-08-10T12:00:00Z"),
    )


def _reasons(*codes: str) -> ReasonSet:
    registry = load_doi_registries()
    return ReasonSet(tuple(registry.reason_ref(code) for code in sorted(codes)))


def _evaluation_record():
    from synthetic_sales_assist.doi.evaluator import evaluate_doi
    from tests.test_doi_evaluator import evaluation_input, split_lines

    return evaluate_doi(evaluation_input(split_lines()))


def _lifecycle_event(transition_id: str):
    from synthetic_sales_assist.doi.lifecycle import (
        TransitionFixture,
        reduce_fixture_transition,
    )

    fixture = TransitionFixture.legal(
        load_doi_registries().transition_ref(transition_id)
    )
    return reduce_fixture_transition(
        fixture.stream,
        fixture.command,
        occurred_at=fixture.occurred_at,
    ).event


class DOISourceClassificationTests(unittest.TestCase):
    def test_synthetic_order_normalization_and_ascii_assignee_rules(self) -> None:
        self.assertEqual(
            normalize_synthetic_order_number("\tSYN-ORDER-00042\r"),
            OrderId("SYN-ORDER-42"),
        )
        self.assertEqual(
            normalize_synthetic_order_number(OrderId("SYN-ORDER-42")),
            OrderId("SYN-ORDER-42"),
        )
        self.assertEqual(classify_assignee("\t target_rep \r"), TARGET_ASSIGNEE)
        self.assertEqual(classify_assignee("other_rep"), "OTHER_REP")
        self.assertIsNone(classify_assignee("TARGET\N{NO-BREAK SPACE}REP"))
        self.assertIsNone(classify_assignee("T\N{CYRILLIC SMALL LETTER A}RGET_REP"))
        for invalid in (
            "42",
            42,
            "SYN-ORDER-0",
            "SYN-ORDER-1 2",
            "SYN-ORDER-\N{ARABIC-INDIC DIGIT ONE}",
        ):
            with self.subTest(invalid=repr(invalid)):
                with self.assertRaises(DOISourceError):
                    normalize_synthetic_order_number(invalid)

    def test_source_cells_are_firewalled_and_raw_assignee_is_not_hash_retained(self) -> None:
        canary = "real.person" + "@" + "example.com"
        with self.assertRaises(DOISourceError) as caught:
            _row(1, "SYN-ORDER-1", canary)
        self.assertNotIn(canary, str(caught.exception))

        image = _image((_row(1, "SYN-ORDER-1", "FICTIONAL_OTHER_REP"),))
        canonical = image.content_binding().canonical_bytes
        self.assertNotIn(b"FICTIONAL_OTHER_REP", canonical)
        self.assertIn(b"OTHER_ASSIGNEE", canonical)

    def test_duplicates_merge_conflicts_reject_and_row_count_equation_is_exact(self) -> None:
        rows = (
            _row(1, "SYN-ORDER-1"),
            _row(2, "SYN-ORDER-01", " target_rep "),
            _row(3, "SYN-ORDER-2", TARGET_ASSIGNEE),
            _row(4, "SYN-ORDER-2", "OTHER_REP"),
            _row(5, "SYN-ORDER-3", "OTHER_REP"),
            _row(6, "SYN-ORDER-4", ""),
        )
        image = _image(rows)
        result = ingest_synthetic_queue(image, image, candidate_batch_id=_batch_id())
        self.assertIs(result.kind, SourceImportResultKind.SUCCEEDED)
        self.assertEqual(result.reasons.reasons, ())
        self.assertIsNotNone(result.batch)
        batch = result.batch
        assert batch is not None
        self.assertEqual(batch.counts.source_row_count.value, 6)
        self.assertEqual(batch.counts.accepted_row_count.value, 2)
        self.assertEqual(batch.counts.invalid_row_count.value, 0)
        self.assertEqual(batch.counts.unrecognized_assignee_row_count.value, 1)
        self.assertEqual(batch.counts.out_of_scope_row_count.value, 1)
        self.assertEqual(batch.counts.conflict_row_count.value, 2)
        self.assertEqual(batch.counts.staged_order_count.value, 1)
        self.assertEqual(batch.counts.duplicate_row_count.value, 1)
        self.assertEqual(batch.counts.rejected_order_count.value, 1)
        staged = batch.staged_orders[0]
        self.assertEqual(staged.order_id, OrderId("SYN-ORDER-1"))
        self.assertEqual(
            [reason.code for reason in staged.reasons.reasons],
            ["RC-006"],
        )
        self.assertEqual(len(staged.source_ref_ids), 2)
        rejected = batch.rejected_records[0]
        self.assertIs(type(rejected), DOIRejectedSourceRecord)
        self.assertEqual(rejected.order_id, OrderId("SYN-ORDER-2"))
        self.assertEqual(
            [reason.code for reason in rejected.reasons.reasons],
            ["RC-008"],
        )
        self.assertEqual(len(rejected.target_source_ref_ids), 1)
        self.assertEqual(
            [reason.code for reason in batch.aggregate_reasons.reasons],
            ["RC-004", "RC-005"],
        )
        self.assertNotIn("OTHER_REP", batch.canonical_bytes().decode("utf-8"))

    def test_locked_schema_invalid_order_is_attempt_failure_and_rc003_is_unreachable(self) -> None:
        rows = (_row(1, "SYN-ORDER-INVALID"),)
        image = _image(rows)
        result = ingest_synthetic_queue(image, image, candidate_batch_id=_batch_id())
        self.assertIs(result.kind, SourceImportResultKind.FAILED)
        self.assertIsNone(result.batch)
        self.assertEqual(
            {reason.code for reason in result.reasons.reasons},
            {"RC-002", "RC-090"},
        )
        self.assertNotIn("RC-003", {reason.code for reason in result.reasons.reasons})
        self.assertNotIn("RC-007", {reason.code for reason in result.reasons.reasons})
        self.assertEqual(result.counts.invalid_row_count.value, 1)

    def test_source_change_revision_partition_and_inaccessible_reads_fail_closed(self) -> None:
        first = _image((_row(1, "SYN-ORDER-1"),), revision="REV-0001")
        changed = _image((_row(2, "SYN-ORDER-2"),), revision="REV-0002")
        cases = (
            (first, changed, {"RC-009", "RC-090"}),
            (first, dataclasses.replace(first, revision=None), {"RC-009", "RC-090"}),
            (first, dataclasses.replace(first, accessible=False), {"RC-089", "RC-090"}),
            (
                dataclasses.replace(first, mapping_version="synthetic-doi-queue-mapping/v2"),
                changed,
                {"RC-002", "RC-090"},
            ),
        )
        for before, after, expected in cases:
            with self.subTest(expected=expected):
                result = ingest_synthetic_queue(
                    before,
                    after,
                    candidate_batch_id=_batch_id(),
                )
                self.assertEqual(
                    {reason.code for reason in result.reasons.reasons},
                    expected,
                )
                self.assertIsNone(result.batch)

    def test_full_content_fingerprint_proves_unchanged_when_revisions_are_unavailable(self) -> None:
        image = _image((_row(1, "SYN-ORDER-1"),), revision=None)
        result = ingest_synthetic_queue(image, image, candidate_batch_id=_batch_id())
        self.assertIs(result.kind, SourceImportResultKind.SUCCEEDED)

    def test_batch_identity_reuses_exact_material_without_reusing_candidate_id(self) -> None:
        image = _image((_row(1, "SYN-ORDER-1"),))
        first_result = ingest_synthetic_queue(
            image,
            image,
            candidate_batch_id=_batch_id("0001"),
        )
        second_result = ingest_synthetic_queue(
            image,
            image,
            candidate_batch_id=_batch_id("0002"),
        )
        assert first_result.batch is not None and second_result.batch is not None
        registry = InMemorySourceBatchRegistry()
        retained = registry.register(first_result.batch)
        replay = registry.register(second_result.batch)
        self.assertIs(replay, retained)
        self.assertEqual(replay.batch_id, _batch_id("0001"))

        with patch(
            "synthetic_sales_assist.doi.source.compare_retained_canonical_bytes",
            side_effect=CanonicalHashCollision("synthetic digest collision"),
        ):
            with self.assertRaises(DOISourceError) as caught:
                registry.register(second_result.batch)
        self.assertEqual(caught.exception.code, "RC-091")

    def test_count_models_reject_false_equations(self) -> None:
        zero = NonNegativeCount(0)
        with self.assertRaises(DOISourceError):
            DOISourceRowCounts(
                NonNegativeCount(1),
                zero,
                zero,
                zero,
                zero,
                zero,
                zero,
                zero,
                zero,
            )
        with self.assertRaises(DOISourceError):
            DOIRunCounts(
                DOISourceRowCounts.zero(),
                zero,
                NonNegativeCount(1),
                NonNegativeCount(1),
                NonNegativeCount(1),
                NonNegativeCount(1),
                zero,
                zero,
            )

    def test_source_hash_known_answers_are_fixed(self) -> None:
        actual: dict[str, tuple[str, str]] = {}
        for name, domain, canonical, digest in source_hash_fixture_records():
            self.assertTrue(canonical.startswith(b"{"))
            actual[name] = (domain, digest)
        self.assertEqual(
            actual,
            {
                "DOIRejectedSourceRecord": (
                    "doi-rejected-source-record/v1",
                    "7617bf31344d188c54eb3eebdc2d76306f8bbb27a4ff72452de812b227d1e310",
                ),
                "DOIRun": (
                    "doi-run/v1",
                    "7dc903e1e4edf488c1216c3c76226608426605824de921d592190875c31f0cf5",
                ),
                "DOIRunEvent": (
                    "doi-run-event/v1",
                    "b7879a0e3602374fb7e70309bad9f85ace295b4a80b60660e956370c5290bab1",
                ),
                "DOIRunWorkDisposition": (
                    "doi-run-work-disposition/v1",
                    "7cb1c9d13c55b640b971f7ea87d172a138deac5215212411251ec3d4ba40338e",
                ),
                "DOIRunWorkItem": (
                    "doi-run-work-item/v1",
                    "41c4961d61c07b07977e00b4ed60b3f6f561aa36e33d2442986a59e69660b891",
                ),
                "DOISourceBatch": (
                    "doi-source-batch/v1",
                    "c3a19c767d20b47fbd069ed4e833c1a061d49f4b86e8cbcab0b0203f768a9c38",
                ),
                "DOISourceBatchIdentity": (
                    "doi-source-batch-identity/v1",
                    "7a5efd40848bfb8ad1aa69a81b265d1d12722c80485340d374e321353c3cd97b",
                ),
                "DOISourceImportAttempt": (
                    "doi-source-import-attempt/v1",
                    "2e1c309feaa93179a57dbc4724282f9927a2944845a26d35ab4c05baee9a342e",
                ),
                "DOISourceImportAttemptEvent": (
                    "doi-source-import-attempt-event/v1",
                    "5c2a3fe3062533d06f4b155364267b81162ae37228ab7c9ee280fc5e6440dca6",
                ),
                "DOIStagedOrder": (
                    "doi-staged-order/v1",
                    "508baca143970fa4c74093eae562c92fcb3e0d010392dbdc256f352eed0c132f",
                ),
                "ExtractionReservationReceipt": (
                    "doi-extraction-reservation-receipt/v1",
                    "794b53de9cf2151c8996ca046636269331dc8aac33a4455991c03d152288758a",
                ),
                "FinalizeFailedSourceImportNoRetryCommand": (
                    "doi-finalize-failed-source-no-retry-command/v1",
                    "75b55630987b19e186c1f89306834844848e73d664378841bbc87f2c862713d5",
                ),
                "NoRetryCommandReceipt": (
                    "doi-no-retry-command-receipt/v1",
                    "9bb37daf5b6fdf3d295fa5efdb41673843ecfa6cae5feda3820016a0453bf1a7",
                ),
                "PreExtractionRulesUnavailableReceipt": (
                    "doi-pre-extraction-rules-unavailable-receipt/v1",
                    "0aea40c2352b3fdbdc3ee7d9557c6de2ff14b1dfbd7fa2f5e8b2dfc1672964da",
                ),
                "SourceImportResult": (
                    "doi-source-import-result/v1",
                    "9e5a11e5a0d30f1ccb0592785f1754dff5625cda0d572fda755b8090cac26222",
                ),
                "SyntheticQueueImageContent": (
                    "doi-source-image-content/v1",
                    "87dafd1cf0e1dcba8a76e345f57742ede3e8ce8e8155e36c86cb8ba986cefdd9",
                ),
            },
        )


class DOIRunControlTests(unittest.TestCase):
    def test_tab_confirmation_is_preallocation_gate_and_start_replays(self) -> None:
        control = InMemoryDOIRunControl()
        values = {
            "run_id": RunId("SYN-RUN-DOI-0001"),
            "invocation_id": RunInvocationId(
                InteractionId("SYN-INTERACTION-DOI-RUN-0001")
            ),
            "source_identity_id": _source_id(),
            "locked_tab": SyntheticQueueTab.MONDAY,
            "accepted_at": CanonicalTimestamp("2026-08-10T12:00:00Z"),
        }
        with self.assertRaises(DOISourceError) as caught:
            control.begin_review_run(**values, tab_confirmed=False)
        self.assertEqual(caught.exception.code, "RC-001")
        first = control.begin_review_run(**values, tab_confirmed=True)
        replay = control.begin_review_run(**values, tab_confirmed=True)
        self.assertIs(replay, first)
        assert first.source_attempt is not None
        self.assertTrue(str(first.source_attempt.attempt_id).endswith("000001"))
        self.assertEqual(first.source_attempt.ordinal.value, 1)
        self.assertIs(first.run.status, RunStatus.IN_PROGRESS)
        self.assertIsNone(first.run.purge_eligible_at)
        with self.assertRaises(RunControlConflict):
            control.begin_review_run(
                **{**values, "accepted_at": CanonicalTimestamp("2026-08-10T12:00:01Z")},
                tab_confirmed=True,
            )

    def test_failed_attempt_waits_indefinitely_then_retry_is_next_ordinal_and_replays(self) -> None:
        control = InMemoryDOIRunControl()
        started = _review_start(control)
        assert started.source_attempt is not None
        image = _image((_row(1, "SYN-ORDER-INVALID"),))
        failure = ingest_synthetic_queue(image, image, candidate_batch_id=_batch_id())
        attempt = control.commit_import_result(
            attempt_id=started.source_attempt.attempt_id,
            result=failure,
            completed_at=CanonicalTimestamp("2026-08-10T12:01:00Z"),
        )
        self.assertIs(attempt.state, SourceImportAttemptState.FAILED)
        self.assertIs(control.run(started.run.run_id).status, RunStatus.IN_PROGRESS)
        command = _command_id("RETRY-0001")
        retry = control.retry_source_import(
            run_id=started.run.run_id,
            command_id=command,
            source_identity_id=_source_id(),
            accepted_at=CanonicalTimestamp("2099-08-10T12:01:01Z"),
        )
        replay = control.retry_source_import(
            run_id=started.run.run_id,
            command_id=command,
            source_identity_id=_source_id(),
            accepted_at=CanonicalTimestamp("2099-08-10T12:01:01Z"),
        )
        self.assertIs(replay, retry)
        self.assertEqual(retry.ordinal.value, 2)
        self.assertNotEqual(retry.attempt_id, attempt.attempt_id)
        self.assertIs(control.run(started.run.run_id).status, RunStatus.IN_PROGRESS)
        with self.assertRaises(RunControlConflict):
            control.retry_source_import(
                run_id=started.run.run_id,
                command_id=command,
                source_identity_id=_source_id(),
                accepted_at=CanonicalTimestamp("2099-08-10T12:01:02Z"),
            )

    def test_successful_import_creates_one_work_item_per_staged_order_only(self) -> None:
        control = InMemoryDOIRunControl()
        started = _review_start(control)
        assert started.source_attempt is not None
        rows = (
            _row(1, "SYN-ORDER-1"),
            _row(2, "SYN-ORDER-01"),
            _row(3, "SYN-ORDER-2"),
            _row(4, "SYN-ORDER-2", "OTHER_REP"),
        )
        image = _image(rows)
        success = ingest_synthetic_queue(image, image, candidate_batch_id=_batch_id())
        control.commit_import_result(
            attempt_id=started.source_attempt.attempt_id,
            result=success,
            completed_at=CanonicalTimestamp("2026-08-10T12:01:00Z"),
        )
        work = control.work_items(started.run.run_id)
        self.assertEqual(len(work), 1)
        self.assertEqual(work[0].order_id, OrderId("SYN-ORDER-1"))
        run = control.run(started.run.run_id)
        self.assertEqual(run.counts.work_item_count.value, 1)
        self.assertEqual(run.counts.disposition_subject_count.value, 0)
        self.assertEqual(run.counts.portal_read_count.value, 0)

    def test_normal_completion_is_derived_from_one_disposition_per_work_item(self) -> None:
        control = InMemoryDOIRunControl()
        started = _review_start(control, "FINAL-SUCCESS")
        assert started.source_attempt is not None
        image = _image((_row(1, "SYN-ORDER-1"),))
        control.commit_import_result(
            attempt_id=started.source_attempt.attempt_id,
            result=ingest_synthetic_queue(image, image, candidate_batch_id=_batch_id()),
            completed_at=CanonicalTimestamp("2026-08-10T12:01:00Z"),
        )
        work_item = control.work_items(started.run.run_id)[0]
        disposition = DOIRunWorkDisposition.successful_evaluation(
            work_item=work_item,
            evaluation=_evaluation_record(),
            occurred_at=CanonicalTimestamp("2026-08-10T12:02:00Z"),
        )
        self.assertIs(
            control.record_work_disposition(disposition),
            control.record_work_disposition(disposition),
        )
        completed_at = CanonicalTimestamp("2026-08-10T12:03:00Z")
        terminal = control.finalize_processing(
            run_id=started.run.run_id,
            completed_at=completed_at,
        )
        replay = control.finalize_processing(
            run_id=started.run.run_id,
            completed_at=completed_at,
        )
        self.assertIs(terminal.run.status, RunStatus.COMPLETED)
        self.assertFalse(terminal.replayed)
        self.assertTrue(replay.replayed)
        self.assertEqual(terminal.run.counts.work_item_count.value, 1)
        self.assertEqual(terminal.run.counts.disposition_subject_count.value, 1)
        self.assertEqual(terminal.run.counts.successful_evaluation_count.value, 1)
        self.assertEqual(terminal.run.counts.order_exception_count.value, 0)
        self.assertEqual(terminal.run.counts.blocked_order_count.value, 0)
        self.assertEqual(terminal.run.counts.portal_read_count.value, 1)
        self.assertEqual(terminal.run.purge_eligible_at, calendar90(completed_at))
        with self.assertRaises(RunControlConflict):
            control.finalize_processing(
                run_id=started.run.run_id,
                completed_at=CanonicalTimestamp("2026-08-10T12:03:01Z"),
            )

    def test_all_blocked_run_completes_with_exceptions_and_zero_success(self) -> None:
        control, run_id = self._recheck_control("ALL-BLOCKED")
        work_item = control.work_items(run_id)[0]
        blocked = DOIRunWorkDisposition.exception_or_block(
            work_item=work_item,
            kind=RunWorkDispositionKind.BLOCKED_ORDER,
            portal_read_performed=False,
            lifecycle_event=_lifecycle_event("TR-044"),
            occurred_at=CanonicalTimestamp("2026-08-10T12:01:00Z"),
            reasons=_reasons("RC-011"),
        )
        control.record_work_disposition(blocked)
        terminal = control.finalize_processing(
            run_id=run_id,
            completed_at=CanonicalTimestamp("2026-08-10T12:02:00Z"),
        )
        self.assertIs(terminal.run.status, RunStatus.COMPLETED_WITH_EXCEPTIONS)
        self.assertEqual(terminal.run.counts.successful_evaluation_count.value, 0)
        self.assertEqual(terminal.run.counts.blocked_order_count.value, 1)
        self.assertEqual(terminal.run.counts.portal_read_count.value, 0)

    def test_finalization_requires_complete_retained_dispositions_and_coherent_batch(self) -> None:
        control, run_id = self._recheck_control("INCOMPLETE")
        with self.assertRaises(RunControlConflict) as incomplete:
            control.finalize_processing(
                run_id=run_id,
                completed_at=CanonicalTimestamp("2026-08-10T12:02:00Z"),
            )
        self.assertEqual(incomplete.exception.code, "run_terminal_count_conservation")

        failed_control = InMemoryDOIRunControl()
        failed_start = _review_start(failed_control, "FAILED-NOT-COMPLETE")
        assert failed_start.source_attempt is not None
        failed_image = _image((_row(1, "SYN-ORDER-INVALID"),))
        failed_control.commit_import_result(
            attempt_id=failed_start.source_attempt.attempt_id,
            result=ingest_synthetic_queue(
                failed_image,
                failed_image,
                candidate_batch_id=_batch_id("FAILED"),
            ),
            completed_at=CanonicalTimestamp("2026-08-10T12:01:00Z"),
        )
        with self.assertRaises(RunControlConflict) as no_batch:
            failed_control.finalize_processing(
                run_id=failed_start.run.run_id,
                completed_at=CanonicalTimestamp("2026-08-10T12:02:00Z"),
            )
        self.assertEqual(no_batch.exception.code, "run_terminal_batch_required")

    def test_empty_coherent_personal_batch_completes_without_dispositions(self) -> None:
        control = InMemoryDOIRunControl()
        started = _review_start(control, "EMPTY")
        assert started.source_attempt is not None
        image = _image(())
        control.commit_import_result(
            attempt_id=started.source_attempt.attempt_id,
            result=ingest_synthetic_queue(
                image,
                image,
                candidate_batch_id=_batch_id("EMPTY"),
            ),
            completed_at=CanonicalTimestamp("2026-08-10T12:01:00Z"),
        )
        terminal = control.finalize_processing(
            run_id=started.run.run_id,
            completed_at=CanonicalTimestamp("2026-08-10T12:02:00Z"),
        )
        self.assertIs(terminal.run.status, RunStatus.COMPLETED)
        self.assertEqual(terminal.run.counts.work_item_count.value, 0)
        self.assertEqual(terminal.run.counts.disposition_subject_count.value, 0)

    def test_disposition_conflict_and_prohibited_evidence_fail_closed(self) -> None:
        control, run_id = self._recheck_control("DISPOSITION-CONFLICT")
        work_item = control.work_items(run_id)[0]
        first = DOIRunWorkDisposition.exception_or_block(
            work_item=work_item,
            kind=RunWorkDispositionKind.ORDER_EXCEPTION,
            portal_read_performed=True,
            lifecycle_event=_lifecycle_event("TR-044"),
            occurred_at=CanonicalTimestamp("2026-08-10T12:01:00Z"),
            reasons=_reasons("RC-011"),
        )
        control.record_work_disposition(first)
        with self.assertRaises(RunControlConflict):
            control.record_work_disposition(
                DOIRunWorkDisposition.exception_or_block(
                    work_item=work_item,
                    kind=RunWorkDispositionKind.ORDER_EXCEPTION,
                    portal_read_performed=True,
                    lifecycle_event=_lifecycle_event("TR-045"),
                    occurred_at=CanonicalTimestamp("2026-08-10T12:01:00Z"),
                    reasons=_reasons("RC-011"),
                )
            )
        prohibited = domain_hash(
            "doi-lifecycle-event/v1",
            canonical_json_bytes(
                {"email": "real.person" + "@" + "example.com"},
                expected_members={"email"},
            ),
        )
        with self.assertRaises(DOISourceError):
            DOIRunWorkDisposition.exception_or_block(
                work_item=work_item,
                kind=RunWorkDispositionKind.BLOCKED_ORDER,
                portal_read_performed=False,
                lifecycle_event=prohibited,
                occurred_at=CanonicalTimestamp("2026-08-10T12:01:00Z"),
                reasons=_reasons("RC-011"),
            )

    def test_explicit_no_retry_terminalizes_and_replays_before_state(self) -> None:
        control = InMemoryDOIRunControl()
        started = _review_start(control)
        assert started.source_attempt is not None
        image = _image((_row(1, "SYN-ORDER-INVALID"),))
        failure = ingest_synthetic_queue(image, image, candidate_batch_id=_batch_id())
        failed = control.commit_import_result(
            attempt_id=started.source_attempt.attempt_id,
            result=failure,
            completed_at=CanonicalTimestamp("2026-08-10T12:01:00Z"),
        )
        with self.assertRaises(TypeError):
            FinalizeFailedSourceImportNoRetryCommand(
                command_id=_command_id("FORGED-NORETRY"),
                run_id=started.run.run_id,
                greatest_failed_attempt_id=failed.attempt_id,
                accepted_actor_id=RepId("SYN-REP-AUTHORIZED-0001"),
                accepted_at=CanonicalTimestamp("2026-08-10T12:02:00Z"),
            )
        with self.assertRaises(DOISourceError):
            accept_no_retry_command(
                command_id=_command_id("UNAUTHORIZED-NORETRY"),
                run_id=started.run.run_id,
                greatest_failed_attempt_id=failed.attempt_id,
                accepted_actor_id=RepId("SYN-REP-UNAUTHORIZED-0001"),
                accepted_at=CanonicalTimestamp("2026-08-10T12:02:00Z"),
            )
        command = accept_no_retry_command(
            command_id=_command_id("NORETRY-0001"),
            run_id=started.run.run_id,
            greatest_failed_attempt_id=failed.attempt_id,
            accepted_actor_id=RepId("SYN-REP-AUTHORIZED-0001"),
            accepted_at=CanonicalTimestamp("2026-08-10T12:02:00Z"),
        )
        receipt = control.finalize_failed_source_import_no_retry(command)
        self.assertIs(control.finalize_failed_source_import_no_retry(command), receipt)
        terminal = control.run(started.run.run_id)
        self.assertIs(terminal.status, RunStatus.FAILED)
        self.assertEqual(terminal.terminal_reasons, failed.reasons)
        with self.assertRaises(RunControlConflict):
            control.finalize_failed_source_import_no_retry(
                accept_no_retry_command(
                    command_id=command.command_id,
                    run_id=command.run_id,
                    greatest_failed_attempt_id=command.greatest_failed_attempt_id,
                    accepted_actor_id=command.accepted_actor_id,
                    accepted_at=CanonicalTimestamp("2026-08-10T12:02:01Z"),
                )
            )
        with self.assertRaises(RunControlConflict):
            control.retry_source_import(
                run_id=started.run.run_id,
                command_id=_command_id("RETRY-AFTER-TERMINAL"),
                source_identity_id=_source_id(),
                accepted_at=CanonicalTimestamp("2026-08-10T12:03:00Z"),
            )

    def test_retry_commit_wins_over_no_retry_for_prior_attempt(self) -> None:
        control = InMemoryDOIRunControl()
        started = _review_start(control)
        assert started.source_attempt is not None
        image = _image((_row(1, "SYN-ORDER-INVALID"),))
        failed = control.commit_import_result(
            attempt_id=started.source_attempt.attempt_id,
            result=ingest_synthetic_queue(image, image, candidate_batch_id=_batch_id()),
            completed_at=CanonicalTimestamp("2026-08-10T12:01:00Z"),
        )
        control.retry_source_import(
            run_id=started.run.run_id,
            command_id=_command_id("RETRY-WINS"),
            source_identity_id=_source_id(),
            accepted_at=CanonicalTimestamp("2026-08-10T12:01:01Z"),
        )
        with self.assertRaises(RunControlConflict):
            control.finalize_failed_source_import_no_retry(
                accept_no_retry_command(
                    command_id=_command_id("NORETRY-LOSES"),
                    run_id=started.run.run_id,
                    greatest_failed_attempt_id=failed.attempt_id,
                    accepted_actor_id=RepId("SYN-REP-AUTHORIZED-0001"),
                    accepted_at=CanonicalTimestamp("2026-08-10T12:01:02Z"),
                )
            )

    def test_rechecks_have_one_work_item_and_no_source_attempt(self) -> None:
        for index, run_type in enumerate(
            (RunType.RECHECK_ORDER, RunType.RECHECK_DEDUPE_ORDER),
            start=1,
        ):
            with self.subTest(run_type=run_type.value):
                control = InMemoryDOIRunControl()
                result = control.begin_recheck_run(
                    run_id=RunId(f"SYN-RUN-DOI-RECHECK-{index}"),
                    invocation_id=RunInvocationId(
                        InteractionId(f"SYN-INTERACTION-DOI-RECHECK-{index}")
                    ),
                    run_type=run_type,
                    order_id=OrderId(f"SYN-ORDER-{index}"),
                    accepted_at=CanonicalTimestamp("2026-08-10T12:00:00Z"),
                )
                self.assertIsNone(result.source_attempt)
                self.assertEqual(len(result.work_items), 1)
                self.assertEqual(result.run.counts.source_attempt_count.value, 0)
                self.assertEqual(result.run.counts.work_item_count.value, 1)

    def _recheck_control(self, suffix: str) -> tuple[InMemoryDOIRunControl, RunId]:
        control = InMemoryDOIRunControl()
        run_id = RunId(f"SYN-RUN-DOI-RACE-{suffix}")
        control.begin_recheck_run(
            run_id=run_id,
            invocation_id=RunInvocationId(
                InteractionId(f"SYN-INTERACTION-DOI-RACE-{suffix}")
            ),
            run_type=RunType.RECHECK_ORDER,
            order_id=OrderId("SYN-ORDER-1"),
            accepted_at=CanonicalTimestamp("2026-08-10T12:00:00Z"),
        )
        return control, run_id

    def test_extraction_reservation_and_rc084_systemic_failure_both_race_orders(self) -> None:
        extraction_first, first_run = self._recheck_control("FIRST")
        extraction_first.reserve_extraction(
            run_id=first_run,
            occurrence_id=ExtractionOccurrenceId(
                InteractionId("SYN-INTERACTION-DOI-OCCURRENCE-FIRST")
            ),
            reserved_at=CanonicalTimestamp("2026-08-10T12:00:01Z"),
        )
        with self.assertRaises(RunControlConflict):
            extraction_first.fail_pre_extraction_rules_unavailable(
                run_id=first_run,
                command_id=_command_id("SYSTEMIC-LOSES"),
                occurred_at=CanonicalTimestamp("2026-08-10T12:00:02Z"),
            )
        self.assertIs(extraction_first.run(first_run).status, RunStatus.IN_PROGRESS)

        systemic_first, second_run = self._recheck_control("SECOND")
        receipt = systemic_first.fail_pre_extraction_rules_unavailable(
            run_id=second_run,
            command_id=_command_id("SYSTEMIC-WINS"),
            occurred_at=CanonicalTimestamp("2026-08-10T12:00:01Z"),
        )
        self.assertEqual(
            [reason.code for reason in receipt.run.terminal_reasons.reasons],
            ["RC-084"],
        )
        self.assertEqual(receipt.run.counts.work_item_count.value, 1)
        self.assertEqual(receipt.run.counts.disposition_subject_count.value, 0)
        self.assertEqual(receipt.run.counts.successful_evaluation_count.value, 0)
        self.assertEqual(receipt.run.counts.portal_read_count.value, 0)
        with self.assertRaises(RunControlConflict):
            systemic_first.reserve_extraction(
                run_id=second_run,
                occurrence_id=ExtractionOccurrenceId(
                    InteractionId("SYN-INTERACTION-DOI-OCCURRENCE-SECOND")
                ),
                reserved_at=CanonicalTimestamp("2026-08-10T12:00:02Z"),
            )

    def test_crossed_race_allows_exactly_one_commit(self) -> None:
        control, run_id = self._recheck_control("CROSSED")

        def reserve() -> str:
            try:
                control.reserve_extraction(
                    run_id=run_id,
                    occurrence_id=ExtractionOccurrenceId(
                        InteractionId("SYN-INTERACTION-DOI-OCCURRENCE-CROSSED")
                    ),
                    reserved_at=CanonicalTimestamp("2026-08-10T12:00:01Z"),
                )
                return "RESERVED"
            except RunControlConflict:
                return "REJECTED"

        def terminalize() -> str:
            try:
                control.fail_pre_extraction_rules_unavailable(
                    run_id=run_id,
                    command_id=_command_id("SYSTEMIC-CROSSED"),
                    occurred_at=CanonicalTimestamp("2026-08-10T12:00:01Z"),
                )
                return "TERMINAL"
            except RunControlConflict:
                return "REJECTED"

        with ThreadPoolExecutor(max_workers=2) as executor:
            reserve_future = executor.submit(reserve)
            terminal_future = executor.submit(terminalize)
            outcomes = {reserve_future.result(), terminal_future.result()}
        expected = (
            {"REJECTED", "RESERVED"}
            if control.run(run_id).status is RunStatus.IN_PROGRESS
            else {"REJECTED", "TERMINAL"}
        )
        self.assertEqual(outcomes, expected)


if __name__ == "__main__":
    unittest.main()
