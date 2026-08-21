from __future__ import annotations

import unittest
from concurrent.futures import ThreadPoolExecutor

from synthetic_sales_assist.doi.identities import (
    AcceptedCommandId,
    ExtractionOccurrenceId,
    RunInvocationId,
)
from synthetic_sales_assist.doi.lifecycle import (
    LifecycleConflictError,
    LifecycleSchemaError,
    TransitionFixture,
    make_transition_command,
)
from synthetic_sales_assist.doi.source import (
    InMemoryDOIRunControl,
    RunControlConflict,
    RunStatus,
    RunType,
)
from synthetic_sales_assist.doi.state import (
    InMemoryDoiState,
    absent_stream_creation_transition_ids,
)
from synthetic_sales_assist.domain.identities import (
    EvidenceId,
    InteractionId,
    OrderId,
    RunId,
)
from synthetic_sales_assist.domain.registries import load_doi_registries
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp


NOW = CanonicalTimestamp("2026-08-20T12:00:00Z")


def _started_recheck() -> tuple[InMemoryDOIRunControl, RunId]:
    controller = InMemoryDOIRunControl()
    run_id = RunId("SYN-RUN-CONTROL-001")
    controller.begin_recheck_run(
        run_id=run_id,
        invocation_id=RunInvocationId(InteractionId("SYN-INTERACTION-RUN-CONTROL-001")),
        run_type=RunType.RECHECK_ORDER,
        order_id=OrderId("SYN-ORDER-CONTROL-001"),
        accepted_at=NOW,
    )
    return controller, run_id


class TestInMemoryDoiState(unittest.TestCase):
    def test_composes_the_authoritative_source_controller(self) -> None:
        source, _ = _started_recheck()
        state = InMemoryDoiState(source_run_control=source)
        self.assertIs(state.source_run_control, source)

    def test_absent_stream_admission_is_closed_to_exact_creation_rows(self) -> None:
        expected = {
            "TR-001",
            "TR-007",
            "TR-042",
            "TR-044",
            "TR-045",
            "TR-045A",
            "TR-054",
            "TR-055",
            "TR-082",
            "TR-084",
        }
        self.assertEqual(set(absent_stream_creation_transition_ids()), expected)
        registries = load_doi_registries()
        for transition_id in absent_stream_creation_transition_ids():
            with self.subTest(transition=transition_id):
                fixture = TransitionFixture.legal(
                    registries.transition_ref(transition_id)
                )
                state = InMemoryDoiState()
                result = state.execute_fixture(
                    fixture.command,
                    occurred_at=fixture.occurred_at,
                )
                self.assertFalse(result.replayed)
                self.assertIsNotNone(state.stream(fixture.command.stream_id))

    def test_absent_stream_rejects_every_non_creation_transition(self) -> None:
        allowed = set(absent_stream_creation_transition_ids())
        for transition in load_doi_registries().transition_refs:
            if transition.transition_id in allowed:
                continue
            with self.subTest(transition=transition.transition_id):
                fixture = TransitionFixture.legal(transition)
                state = InMemoryDoiState()
                with self.assertRaisesRegex(
                    LifecycleConflictError,
                    "STATE_STREAM_CREATION_TRANSITION_INVALID",
                ):
                    state.execute_fixture(
                        fixture.command,
                        occurred_at=fixture.occurred_at,
                    )
                self.assertIsNone(state.stream(fixture.command.stream_id))
                self.assertEqual(state.retained_event_count, 0)

    def test_tr112_cannot_bootstrap_delete_or_finalization_effects(self) -> None:
        transition = load_doi_registries().transition_ref("TR-112")
        fixture = TransitionFixture.legal(transition)
        state = InMemoryDoiState()
        with self.assertRaisesRegex(
            LifecycleConflictError,
            "STATE_STREAM_CREATION_TRANSITION_INVALID",
        ):
            state.execute_fixture(
                fixture.command,
                occurred_at=fixture.occurred_at,
            )
        self.assertIsNone(state.stream(fixture.command.stream_id))
        self.assertEqual(state.stream_count, 0)
        self.assertEqual(state.retained_event_count, 0)

    def test_lifecycle_commit_replay_and_owner_scoped_delete(self) -> None:
        state = InMemoryDoiState()
        fixture = TransitionFixture.legal(load_doi_registries().transition_ref("TR-044"))
        accepted = state.execute_fixture(fixture.command, occurred_at=fixture.occurred_at)
        replay = state.execute_fixture(fixture.command, occurred_at=fixture.occurred_at)
        self.assertFalse(accepted.replayed)
        self.assertTrue(replay.replayed)
        self.assertEqual(state.stream_count, 1)
        self.assertEqual(state.retained_event_count, 1)
        head = accepted.stream.projection.head_sha256
        self.assertIsNotNone(head)
        state.delete_owner_stream(
            fixture.command.stream_id,
            expected_head_sha256=head or "",
        )
        self.assertIsNone(state.stream(fixture.command.stream_id))
        self.assertEqual(state.stream_count, 0)
        self.assertEqual(state.retained_event_count, 0)

    def test_production_state_rejects_structural_fixture_authority(self) -> None:
        state = InMemoryDoiState()
        fixture = TransitionFixture.legal(
            load_doi_registries().transition_ref("TR-045")
        )
        with self.assertRaisesRegex(
            LifecycleSchemaError,
            "TRANSITION_SYNTHETIC_FIXTURE_AUTHORITY_FORBIDDEN",
        ):
            state.execute(fixture.command, occurred_at=fixture.occurred_at)
        self.assertIsNone(state.stream(fixture.command.stream_id))
        self.assertEqual(state.retained_event_count, 0)

    def test_lifecycle_fault_rolls_back_copy_on_write_candidate(self) -> None:
        state = InMemoryDoiState()
        fixture = TransitionFixture.legal(load_doi_registries().transition_ref("TR-044"))

        def fail(_: object) -> None:
            raise RuntimeError("injected")

        with self.assertRaisesRegex(RuntimeError, "injected"):
            state.execute_fixture(
                fixture.command,
                occurred_at=fixture.occurred_at,
                fault_injector=fail,
            )
        self.assertIsNone(state.stream(fixture.command.stream_id))
        self.assertEqual(state.retained_event_count, 0)

    def test_two_distinct_same_scope_commands_serialize(self) -> None:
        state = InMemoryDoiState()
        transition = load_doi_registries().transition_ref("TR-044")
        fixture = TransitionFixture.legal(transition)
        changed = make_transition_command(
            transition=transition,
            stream_id=fixture.command.stream_id,
            occurrence_id=fixture.command.occurrence_id,
            current_state=fixture.definition.from_state,
            expected_sequence=1,
            expected_predecessor_sha256=None,
            guard_proof=fixture.command.guard_proof,
            reasons=(load_doi_registries().reason_ref("RC-061"),),
        )
        commands = (
            fixture.command,
            changed,
        )

        def submit(command: object) -> str:
            try:
                state.execute_fixture(command, occurred_at=NOW)  # type: ignore[arg-type]
            except LifecycleConflictError as error:
                return error.code
            return "ACCEPTED"

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = tuple(pool.map(submit, commands))
        self.assertEqual(outcomes.count("ACCEPTED"), 1)
        self.assertEqual(
            outcomes.count("TRANSITION_OCCURRENCE_MATERIAL_CONFLICT"),
            1,
        )
        self.assertEqual(state.retained_event_count, 1)

    def test_extraction_reservation_wins_and_rc084_branch_cannot_commit(self) -> None:
        controller, run_id = _started_recheck()
        controller.reserve_extraction(
            run_id=run_id,
            occurrence_id=ExtractionOccurrenceId(
                InteractionId("SYN-INTERACTION-EXTRACTION-001")
            ),
            reserved_at=NOW,
        )
        with self.assertRaisesRegex(RunControlConflict, "extraction_reservation_won"):
            controller.fail_pre_extraction_rules_unavailable(
                run_id=run_id,
                command_id=AcceptedCommandId(
                    InteractionId("SYN-INTERACTION-SYSTEMIC-001")
                ),
                occurred_at=NOW,
            )
        self.assertEqual(controller.run(run_id).status, RunStatus.IN_PROGRESS)

    def test_rc084_branch_wins_with_zero_reads_dispositions_and_evaluations(self) -> None:
        controller, run_id = _started_recheck()
        receipt = controller.fail_pre_extraction_rules_unavailable(
            run_id=run_id,
            command_id=AcceptedCommandId(InteractionId("SYN-INTERACTION-SYSTEMIC-002")),
            occurred_at=NOW,
        )
        with self.assertRaisesRegex(RunControlConflict, "extraction_reservation_run_state"):
            controller.reserve_extraction(
                run_id=run_id,
                occurrence_id=ExtractionOccurrenceId(
                    InteractionId("SYN-INTERACTION-EXTRACTION-002")
                ),
                reserved_at=NOW,
            )
        run = receipt.run
        self.assertEqual(run.status, RunStatus.FAILED)
        self.assertEqual(tuple(reason.code for reason in run.terminal_reasons.reasons), ("RC-084",))
        self.assertEqual(run.counts.portal_read_count.value, 0)
        self.assertEqual(run.counts.disposition_subject_count.value, 0)
        self.assertEqual(run.counts.successful_evaluation_count.value, 0)

    def test_authoritative_crossed_race_has_exactly_one_winner(self) -> None:
        controller, run_id = _started_recheck()

        def reserve() -> str:
            try:
                controller.reserve_extraction(
                    run_id=run_id,
                    occurrence_id=ExtractionOccurrenceId(
                        InteractionId("SYN-INTERACTION-EXTRACTION-003")
                    ),
                    reserved_at=NOW,
                )
            except RunControlConflict:
                return "REJECTED"
            return "RESERVED"

        def systemic() -> str:
            try:
                controller.fail_pre_extraction_rules_unavailable(
                    run_id=run_id,
                    command_id=AcceptedCommandId(
                        InteractionId("SYN-INTERACTION-SYSTEMIC-003")
                    ),
                    occurred_at=NOW,
                )
            except RunControlConflict:
                return "REJECTED"
            return "FAILED"

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = (pool.submit(reserve), pool.submit(systemic))
            outcomes = tuple(future.result() for future in futures)
        self.assertEqual(outcomes.count("REJECTED"), 1)
        self.assertEqual(sum(outcome in {"RESERVED", "FAILED"} for outcome in outcomes), 1)


if __name__ == "__main__":
    unittest.main()
