from __future__ import annotations

import tempfile
import unittest
from contextlib import nullcontext
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock, patch

from synthetic_sales_assist.application import (
    APPLICATION_BUILD_VERSION,
    APPLICATION_SCHEMA_VERSION,
    ApplicationError,
    ScenarioApplication,
    ordered_line_manifest_digest_from_mappings,
    validate_line_fact,
)
from synthetic_sales_assist.application.durable_registry import (
    DurableRegistryError,
    _attempt_record,
    _binding_record,
    _resolution_record,
)
from synthetic_sales_assist.demos import demo_catalog
from synthetic_sales_assist.doi.demo import DOI_APPLICATION_FIXTURES
from synthetic_sales_assist.domain.idempotency import DigestCollisionError
from synthetic_sales_assist.domain.numeric import Quantity
from synthetic_sales_assist.persistence.idempotency import SQLiteIdempotencyRepository
from synthetic_sales_assist.persistence.telemetry import SAFETY_COUNTER_NAMES


class _SimulatedProcessCrash(BaseException):
    pass


class Milestone5ApplicationTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(
            prefix="synthetic-sales-assist-m5-application-"
        )
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.application = ScenarioApplication.open(self.root / "data")

    def test_catalog_contains_required_aliases_and_selected_edge_scenarios(self) -> None:
        rows = self.application.list_scenarios()
        aliases = tuple(item.alias for item in rows)
        required = {item.alias for item in demo_catalog()}
        self.assertTrue(required.issubset(aliases))
        self.assertTrue(
            {
                "doi-dedupe-review",
                "doi-long-order",
                "doi-partial-quantity",
                "doi-unknown-containment",
                "doi-zero-lines",
                "sales-credit-cancellation-replacement",
            }.issubset(aliases)
        )
        self.assertEqual(aliases, tuple(sorted(aliases)))
        for row in rows:
            self.assertEqual(
                tuple(row.to_dict()),
                (
                    "alias",
                    "allowed_modes",
                    "collected_scenario",
                    "complexity",
                    "description",
                    "expected_result",
                    "rule_pack",
                    "schema_version",
                ),
            )

    def test_required_aliases_instantiate_fresh_reserved_unevaluated_orders(self) -> None:
        details = tuple(
            self.application.instantiate(item.alias, f"instantiate-required-{index}")
            for index, item in enumerate(demo_catalog(), start=1)
        )
        self.assertEqual(len({item.order_id for item in details}), 7)
        self.assertTrue(all(item.order_id.startswith("SYN-ORDER-") for item in details))
        self.assertTrue(all(item.latest_evaluation is None for item in details))
        self.assertEqual(len(self.application.list_orders()), 7)

    def test_instantiation_has_exact_replay_conflict_and_bounded_capacity(self) -> None:
        first = self.application.instantiate(
            "sales-credit-target-rep", "instantiate-replay"
        )
        replay = self.application.instantiate(
            "sales-credit-target-rep", "instantiate-replay"
        )
        self.assertEqual(replay.order_id, first.order_id)
        with self.assertRaises(ApplicationError) as captured:
            self.application.instantiate(
                "sales-credit-human-review", "instantiate-replay"
            )
        self.assertEqual(captured.exception.code, "IDEMPOTENCY_KEY_MATERIAL_CONFLICT")

        bounded = ScenarioApplication.open(
            self.root / "bounded-data",
            registry_limit=1,
        )
        bounded.instantiate("doi-full-ds", "bounded-first")
        with self.assertRaises(ApplicationError) as capacity:
            bounded.instantiate("doi-overlap", "bounded-second")
        self.assertEqual(capacity.exception.code, "APPLICATION_REGISTRY_CAPACITY_REACHED")

    def test_durable_catalog_and_history_survive_close_and_reopen(self) -> None:
        data = self.root / "restart-data"
        first = ScenarioApplication.open(data)
        unevaluated = first.instantiate("doi-full-ds", "restart-unevaluated")
        evaluated = first.instantiate("sales-credit-target-rep", "restart-evaluated")
        conflict_target = first.instantiate("doi-overlap", "restart-conflict-target")

        initial = first.evaluate(evaluated.order_id, "restart-evaluation-key")
        replay = first.evaluate(evaluated.order_id, "restart-evaluation-key")
        self.assertFalse(initial.replayed)
        self.assertTrue(replay.replayed)
        with self.assertRaises(ApplicationError) as conflict:
            first.evaluate(conflict_target.order_id, "restart-evaluation-key")
        self.assertEqual(
            conflict.exception.code,
            "IDEMPOTENCY_KEY_MATERIAL_CONFLICT",
        )

        before_orders = tuple(item.to_dict() for item in first.list_orders())
        before_unevaluated = first.get_order(unevaluated.order_id).to_dict()
        before_evaluated = first.get_order(evaluated.order_id).to_dict()
        before_history = first.get_history(evaluated.order_id).to_dict()
        before_conflict_history = first.get_history(conflict_target.order_id).to_dict()
        self.assertEqual(before_history["exact_replay_count"], 1)
        self.assertEqual(before_conflict_history["conflict_count"], 1)
        self.assertEqual(
            [item["outcome"] for item in before_history["attempt_receipts"]],
            ["SUCCEEDED", "SUCCEEDED"],
        )
        self.assertEqual(
            before_conflict_history["attempt_receipts"][0]["outcome"],
            "CONFLICT",
        )

        del first
        reopened = ScenarioApplication.open(data)
        self.assertEqual(
            tuple(item.to_dict() for item in reopened.list_orders()),
            before_orders,
        )
        self.assertEqual(
            reopened.get_order(unevaluated.order_id).to_dict(),
            before_unevaluated,
        )
        self.assertEqual(
            reopened.get_order(evaluated.order_id).to_dict(),
            before_evaluated,
        )
        self.assertEqual(
            reopened.get_history(evaluated.order_id).to_dict(),
            before_history,
        )
        self.assertEqual(
            reopened.get_history(conflict_target.order_id).to_dict(),
            before_conflict_history,
        )
        replay_after_restart = reopened.evaluate(
            evaluated.order_id,
            "restart-evaluation-key",
        )
        self.assertTrue(replay_after_restart.replayed)
        history_after_restart = reopened.get_history(evaluated.order_id)
        self.assertEqual(history_after_restart.exact_replay_count, 2)
        self.assertEqual(history_after_restart.telemetry_event_count, 3)
        self.assertTrue(history_after_restart.attempt_receipts[-1].replayed)

    def test_crash_boundaries_reconcile_one_linked_evaluation_without_duplication(
        self,
    ) -> None:
        cases = (
            (
                "sales-credit-target-rep",
                "sc_evaluations",
                "sc_case_events",
            ),
            (
                "doi-fulfillment-split",
                "doi_evaluations",
                "doi_run_events",
            ),
        )
        boundaries = ("after-business", "after-telemetry", "after-attempt")

        for alias, evaluation_table, event_table in cases:
            for boundary in boundaries:
                with self.subTest(alias=alias, boundary=boundary):
                    suffix = f"{alias}-{boundary}"
                    data = self.root / f"recovery-{suffix}"
                    application = ScenarioApplication.open(data)
                    detail = application.instantiate(alias, f"instantiate-{suffix}")
                    request_key = f"evaluate-{suffix}"

                    if boundary == "after-business":
                        crash = patch.object(
                            application,
                            "_record_telemetry",
                            side_effect=_SimulatedProcessCrash,
                        )
                    elif boundary == "after-telemetry":
                        crash = patch.object(
                            application,
                            "_append_attempt",
                            side_effect=_SimulatedProcessCrash,
                        )
                    else:
                        append_attempt = application._append_attempt

                        def commit_then_crash(*args: object, **kwargs: object) -> None:
                            append_attempt(*args, **kwargs)  # type: ignore[arg-type]
                            raise _SimulatedProcessCrash

                        crash = patch.object(
                            application,
                            "_append_attempt",
                            side_effect=commit_then_crash,
                        )

                    with crash, self.assertRaises(_SimulatedProcessCrash):
                        application.evaluate(detail.order_id, request_key)

                    with application.database.read() as connection:
                        before_business = (
                            int(
                                connection.execute(
                                    f"SELECT COUNT(*) FROM {evaluation_table}"
                                ).fetchone()[0]
                            ),
                            int(
                                connection.execute(
                                    f"SELECT COUNT(*) FROM {event_table}"
                                ).fetchone()[0]
                            ),
                        )
                    self.assertGreater(before_business[0], 0)
                    self.assertGreater(before_business[1], 0)

                    reopened = ScenarioApplication.open(data)
                    recovered = reopened.get_order(detail.order_id)
                    self.assertIsNotNone(recovered.latest_evaluation)
                    assert recovered.latest_evaluation is not None
                    self.assertFalse(recovered.latest_evaluation.replayed)
                    history = reopened.get_history(detail.order_id)
                    self.assertEqual(len(history.attempt_receipts), 1)
                    self.assertEqual(history.telemetry_event_count, 1)
                    self.assertEqual(history.exact_replay_count, 0)
                    self.assertFalse(history.attempt_receipts[0].replayed)
                    metrics = reopened.metrics_summary()
                    self.assertEqual(metrics.total_processed, 1)
                    self.assertEqual(metrics.exact_replay_count, 0)

                    with reopened.database.read() as connection:
                        after_recovery_business = (
                            int(
                                connection.execute(
                                    f"SELECT COUNT(*) FROM {evaluation_table}"
                                ).fetchone()[0]
                            ),
                            int(
                                connection.execute(
                                    f"SELECT COUNT(*) FROM {event_table}"
                                ).fetchone()[0]
                            ),
                        )
                        recovery_counts = tuple(
                            int(value)
                            for value in connection.execute(
                                "SELECT "
                                "(SELECT COUNT(*) FROM processing_telemetry), "
                                "(SELECT COUNT(*) FROM durable_commands "
                                " WHERE natural_namespace="
                                "'application.scenario_attempt'), "
                                "(SELECT COUNT(*) FROM durable_commands "
                                " WHERE natural_namespace="
                                "'application.scenario_evaluation_resolution')"
                            ).fetchone()
                        )
                    self.assertEqual(after_recovery_business, before_business)
                    self.assertEqual(recovery_counts, (1, 1, 1))

                    replay = reopened.evaluate(detail.order_id, request_key)
                    self.assertTrue(replay.replayed)
                    replay_history = reopened.get_history(detail.order_id)
                    self.assertEqual(len(replay_history.attempt_receipts), 2)
                    self.assertEqual(replay_history.telemetry_event_count, 2)
                    self.assertEqual(replay_history.exact_replay_count, 1)
                    with reopened.database.read() as connection:
                        after_replay_business = (
                            int(
                                connection.execute(
                                    f"SELECT COUNT(*) FROM {evaluation_table}"
                                ).fetchone()[0]
                            ),
                            int(
                                connection.execute(
                                    f"SELECT COUNT(*) FROM {event_table}"
                                ).fetchone()[0]
                            ),
                        )
                        replay_counts = tuple(
                            int(value)
                            for value in connection.execute(
                                "SELECT "
                                "(SELECT COUNT(*) FROM processing_telemetry), "
                                "(SELECT COUNT(*) FROM durable_commands "
                                " WHERE natural_namespace="
                                "'application.scenario_attempt'), "
                                "(SELECT COUNT(*) FROM durable_commands "
                                " WHERE natural_namespace="
                                "'application.scenario_evaluation_resolution')"
                            ).fetchone()
                        )
                    self.assertEqual(after_replay_business, before_business)
                    self.assertEqual(replay_counts, (2, 2, 1))

    def test_malformed_crash_boundaries_reconcile_one_linked_failure(self) -> None:
        boundaries = ("after-business", "after-telemetry", "after-attempt")

        for boundary in boundaries:
            with self.subTest(boundary=boundary):
                data = self.root / f"malformed-recovery-{boundary}"
                application = ScenarioApplication.open(data)
                detail = application.instantiate(
                    "malformed-input",
                    f"instantiate-malformed-{boundary}",
                )
                request_key = f"evaluate-malformed-{boundary}"

                if boundary == "after-business":
                    crash = patch.object(
                        application.malformed_backend,
                        "_record_telemetry",
                        side_effect=_SimulatedProcessCrash,
                    )
                elif boundary == "after-telemetry":
                    crash = patch.object(
                        application,
                        "_append_attempt",
                        side_effect=_SimulatedProcessCrash,
                    )
                else:
                    append_attempt = application._append_attempt

                    def commit_then_crash(*args: object, **kwargs: object) -> None:
                        append_attempt(*args, **kwargs)  # type: ignore[arg-type]
                        raise _SimulatedProcessCrash

                    crash = patch.object(
                        application,
                        "_append_attempt",
                        side_effect=commit_then_crash,
                    )

                with crash, self.assertRaises(_SimulatedProcessCrash):
                    application.evaluate(detail.order_id, request_key)

                with application.database.read() as connection:
                    before_failures = int(
                        connection.execute(
                            "SELECT COUNT(*) FROM structured_domain_failures"
                        ).fetchone()[0]
                    )
                self.assertEqual(before_failures, 1)

                reopened = ScenarioApplication.open(data)
                recovered = reopened.get_order(detail.order_id)
                self.assertIsNotNone(recovered.latest_evaluation)
                assert recovered.latest_evaluation is not None
                self.assertFalse(recovered.latest_evaluation.replayed)
                self.assertEqual(
                    recovered.latest_evaluation.top_level_result,
                    "INVALID_INPUT",
                )
                history = reopened.get_history(detail.order_id)
                self.assertEqual(len(history.attempt_receipts), 1)
                self.assertEqual(history.telemetry_event_count, 1)
                self.assertEqual(history.exact_replay_count, 0)
                self.assertFalse(history.attempt_receipts[0].replayed)
                metrics = reopened.metrics_summary()
                self.assertEqual(metrics.total_processed, 1)
                self.assertEqual(metrics.failed_closed_count, 1)
                self.assertEqual(metrics.exact_replay_count, 0)

                with reopened.database.read() as connection:
                    recovery_counts = tuple(
                        int(value)
                        for value in connection.execute(
                            "SELECT "
                            "(SELECT COUNT(*) FROM structured_domain_failures), "
                            "(SELECT COUNT(*) FROM processing_telemetry), "
                            "(SELECT COUNT(*) FROM durable_commands "
                            " WHERE natural_namespace="
                            "'application.scenario_attempt'), "
                            "(SELECT COUNT(*) FROM durable_commands "
                            " WHERE natural_namespace="
                            "'application.scenario_evaluation_resolution')"
                        ).fetchone()
                    )
                self.assertEqual(recovery_counts, (1, 1, 1, 1))

                replay = reopened.evaluate(detail.order_id, request_key)
                self.assertTrue(replay.replayed)
                replay_history = reopened.get_history(detail.order_id)
                self.assertEqual(len(replay_history.attempt_receipts), 2)
                self.assertEqual(replay_history.telemetry_event_count, 2)
                self.assertEqual(replay_history.exact_replay_count, 1)
                with reopened.database.read() as connection:
                    replay_counts = tuple(
                        int(value)
                        for value in connection.execute(
                            "SELECT "
                            "(SELECT COUNT(*) FROM structured_domain_failures), "
                            "(SELECT COUNT(*) FROM processing_telemetry), "
                            "(SELECT COUNT(*) FROM durable_commands "
                            " WHERE natural_namespace="
                            "'application.scenario_attempt'), "
                            "(SELECT COUNT(*) FROM durable_commands "
                            " WHERE natural_namespace="
                            "'application.scenario_evaluation_resolution')"
                        ).fetchone()
                    )
                self.assertEqual(replay_counts, (1, 2, 2, 1))

    def test_attempt_nonce_collision_rolls_back_before_resolution_and_recovers(
        self,
    ) -> None:
        detail = self.application.instantiate(
            "doi-full-ds",
            "attempt-nonce-collision-instance",
        )
        self.application.evaluate(detail.order_id, "attempt-nonce-collision-first")
        first_attempt = self.application.get_history(
            detail.order_id
        ).attempt_receipts[0]
        retained_nonce = first_attempt.attempt_id.rsplit("-", 1)[-1].lower()
        fixed_uuid_module = Mock()
        fixed_uuid_module.uuid4.return_value = Mock(hex=retained_nonce)

        with patch(
            "synthetic_sales_assist.application.durable_registry.uuid",
            fixed_uuid_module,
        ):
            with self.assertRaises(ApplicationError) as collision:
                self.application.evaluate(
                    detail.order_id,
                    "attempt-nonce-collision-second",
                )
        self.assertEqual(
            collision.exception.code,
            "APPLICATION_DURABLE_HISTORY_INVALID",
        )

        with self.application.database.read() as connection:
            interrupted_counts = tuple(
                int(value)
                for value in connection.execute(
                    "SELECT "
                    "(SELECT COUNT(*) FROM durable_commands WHERE natural_namespace="
                    "'application.scenario_evaluation'), "
                    "(SELECT COUNT(*) FROM durable_commands WHERE natural_namespace="
                    "'application.scenario_attempt'), "
                    "(SELECT COUNT(*) FROM durable_commands WHERE natural_namespace="
                    "'application.scenario_evaluation_resolution')"
                ).fetchone()
            )
        self.assertEqual(interrupted_counts, (2, 1, 1))

        reopened = ScenarioApplication.open(self.root / "data")
        recovered_history = reopened.get_history(detail.order_id)
        self.assertEqual(len(recovered_history.attempt_receipts), 2)
        self.assertEqual(recovered_history.exact_replay_count, 0)
        with reopened.database.read() as connection:
            recovered_counts = tuple(
                int(value)
                for value in connection.execute(
                    "SELECT "
                    "(SELECT COUNT(*) FROM durable_commands WHERE natural_namespace="
                    "'application.scenario_evaluation'), "
                    "(SELECT COUNT(*) FROM durable_commands WHERE natural_namespace="
                    "'application.scenario_attempt'), "
                    "(SELECT COUNT(*) FROM durable_commands WHERE natural_namespace="
                    "'application.scenario_evaluation_resolution')"
                ).fetchone()
            )
        self.assertEqual(recovered_counts, (2, 2, 2))

    def test_cross_order_attempt_nonce_collision_is_closed_and_recoverable(
        self,
    ) -> None:
        first = self.application.instantiate(
            "doi-full-ds",
            "cross-order-nonce-first-instance",
        )
        second = self.application.instantiate(
            "doi-full-ds",
            "cross-order-nonce-second-instance",
        )
        self.application.evaluate(first.order_id, "cross-order-nonce-first-evaluation")
        retained_attempt = self.application.get_history(
            first.order_id
        ).attempt_receipts[0]
        retained_nonce = retained_attempt.attempt_id.rsplit("-", 1)[-1].lower()
        fixed_uuid_module = Mock()
        fixed_uuid_module.uuid4.return_value = Mock(hex=retained_nonce)

        with patch(
            "synthetic_sales_assist.application.durable_registry.uuid",
            fixed_uuid_module,
        ):
            with self.assertRaises(ApplicationError) as collision:
                self.application.evaluate(
                    second.order_id,
                    "cross-order-nonce-second-evaluation",
                )
        self.assertEqual(
            collision.exception.code,
            "APPLICATION_DURABLE_HISTORY_INVALID",
        )

        with self.application.database.read() as connection:
            interrupted_counts = tuple(
                int(value)
                for value in connection.execute(
                    "SELECT "
                    "(SELECT COUNT(*) FROM durable_commands WHERE natural_namespace="
                    "'application.scenario_evaluation'), "
                    "(SELECT COUNT(*) FROM durable_commands WHERE natural_namespace="
                    "'application.scenario_attempt'), "
                    "(SELECT COUNT(*) FROM durable_commands WHERE natural_namespace="
                    "'application.scenario_evaluation_resolution')"
                ).fetchone()
            )
            second_attempt_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM durable_commands c "
                    "JOIN durable_receipt_owners o ON o.command_id=c.command_id "
                    "WHERE c.natural_namespace='application.scenario_attempt' "
                    "AND o.owner_domain='SYSTEM' AND o.owner_id=?",
                    (second.order_id,),
                ).fetchone()[0]
            )
        self.assertEqual(interrupted_counts, (2, 1, 1))
        self.assertEqual(second_attempt_count, 0)

        reopened = ScenarioApplication.open(self.root / "data")
        self.assertEqual(len(reopened.get_history(first.order_id).attempt_receipts), 1)
        recovered_second = reopened.get_history(second.order_id)
        self.assertEqual(len(recovered_second.attempt_receipts), 1)
        self.assertEqual(recovered_second.exact_replay_count, 0)
        with reopened.database.read() as connection:
            recovered_counts = tuple(
                int(value)
                for value in connection.execute(
                    "SELECT "
                    "(SELECT COUNT(*) FROM durable_commands WHERE natural_namespace="
                    "'application.scenario_evaluation'), "
                    "(SELECT COUNT(*) FROM durable_commands WHERE natural_namespace="
                    "'application.scenario_attempt'), "
                    "(SELECT COUNT(*) FROM durable_commands WHERE natural_namespace="
                    "'application.scenario_evaluation_resolution')"
                ).fetchone()
            )
        self.assertEqual(recovered_counts, (2, 2, 2))

    def test_attempt_digest_collision_is_closed_without_attempt_or_resolution(
        self,
    ) -> None:
        detail = self.application.instantiate(
            "doi-full-ds",
            "attempt-digest-collision-instance",
        )
        instance = self.application._instances[detail.order_id]
        digest_collision = DigestCollisionError("IDEMPOTENCY_DIGEST_COLLISION")

        with patch.object(
            SQLiteIdempotencyRepository,
            "resolve_or_record",
            side_effect=digest_collision,
        ) as resolve:
            with self.assertRaises(ApplicationError) as captured:
                self.application._append_attempt(
                    instance,
                    outcome="CONFLICT",
                    telemetry_operation_id=(
                        "SYN-EVIDENCE-M5-OPERATION-ATTEMPT-DIGEST-COLLISION"
                    ),
                    error_code="IDEMPOTENCY_KEY_MATERIAL_CONFLICT",
                    evaluation_binding_command_id=(
                        "SYN-EVIDENCE-M5-EVALUATION-BINDING-DIGEST-COLLISION"
                    ),
                )
        self.assertEqual(captured.exception.code, "APPLICATION_DURABLE_HISTORY_INVALID")
        self.assertEqual(resolve.call_count, 1)

        with self.application.database.read() as connection:
            counts = tuple(
                int(value)
                for value in connection.execute(
                    "SELECT "
                    "(SELECT COUNT(*) FROM durable_commands WHERE natural_namespace="
                    "'application.scenario_attempt'), "
                    "(SELECT COUNT(*) FROM durable_commands WHERE natural_namespace="
                    "'application.scenario_evaluation_resolution')"
                ).fetchone()
            )
        self.assertEqual(counts, (0, 0))

    def test_recovery_readers_reject_key_id_and_counter_type_tampering(self) -> None:
        detail = self.application.instantiate(
            "doi-full-ds",
            "recovery-integrity-instance",
        )
        self.application.evaluate(detail.order_id, "recovery-integrity-evaluate")
        operation_id = self.application.get_history(
            detail.order_id
        ).attempt_receipts[0].telemetry_operation_id

        with self.application.database.read() as connection:
            binding_row = tuple(
                connection.execute(
                    "SELECT c.command_id, c.natural_key, c.command_domain, "
                    "c.command_sha256, c.command_bytes, c.accepted_at, "
                    "r.result_domain, r.result_sha256, r.result_bytes, "
                    "r.recorded_at, o.owner_id FROM durable_commands c "
                    "JOIN durable_command_receipts r ON r.command_id=c.command_id "
                    "JOIN durable_receipt_owners o ON o.command_id=c.command_id "
                    "WHERE c.natural_namespace="
                    "'application.scenario_evaluation'"
                ).fetchone()
            )
            resolution_row = tuple(
                connection.execute(
                    "SELECT c.command_id, c.command_domain, c.command_sha256, "
                    "c.command_bytes, c.accepted_at, r.result_domain, "
                    "r.result_sha256, r.result_bytes, r.recorded_at, o.owner_id "
                    "FROM durable_commands c JOIN durable_command_receipts r "
                    "ON r.command_id=c.command_id JOIN durable_receipt_owners o "
                    "ON o.command_id=c.command_id WHERE c.natural_namespace="
                    "'application.scenario_evaluation_resolution'"
                ).fetchone()
            )
            attempt_row = tuple(
                connection.execute(
                    "SELECT c.command_id, c.natural_key, c.command_domain, "
                    "c.command_sha256, c.command_bytes, c.accepted_at, "
                    "o.owner_id, r.result_domain, r.result_sha256, "
                    "r.result_bytes, r.recorded_at FROM durable_commands c "
                    "JOIN durable_command_receipts r ON r.command_id=c.command_id "
                    "JOIN durable_receipt_owners o ON o.command_id=c.command_id "
                    "WHERE c.natural_namespace='application.scenario_attempt'"
                ).fetchone()
            )
            telemetry_row = tuple(
                connection.execute(
                    "SELECT operation_id, rule_pack, demo_alias, started_at, "
                    "ended_at, extraction_ns, validation_ns, normalization_ns, "
                    "rule_ns, database_ns, total_ns, result_class, human_review, "
                    "fail_closed, replay, conflict, database_error, rule_version, "
                    "schema_version, catalog_version, error_code "
                    "FROM processing_telemetry WHERE operation_id=?",
                    (operation_id,),
                ).fetchone()
            )

        tampered_binding = list(binding_row)
        tampered_binding[1] = '{"components":["tampered-recovery-key"]}'
        with self.assertRaises(DurableRegistryError):
            _binding_record(tuple(tampered_binding))

        tampered_resolution = list(resolution_row)
        tampered_resolution[0] = (
            "SYN-EVIDENCE-M5-EVALUATION-RESOLUTION-TAMPERED"
        )
        with self.assertRaises(DurableRegistryError):
            _resolution_record(tuple(tampered_resolution))

        attempt_nonce = str(attempt_row[0]).rsplit("-", 1)[-1]
        different_nonce = (
            ("A" if attempt_nonce[0] != "A" else "B") + attempt_nonce[1:]
        )
        attempt_tampering = {
            "command-id": (
                0,
                "SYN-EVIDENCE-M5-NOT-AN-ATTEMPT-"
                "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
            ),
            "natural-key": (
                1,
                f'{{"components":["{different_nonce}"]}}',
            ),
            "command-domain": (2, "m5-scenario-attempt-command/v2"),
            "command-sha256": (3, "0" * 64),
            "command-bytes": (4, b"{}"),
            "accepted-at": (5, "2000-01-01T00:00:00.000000Z"),
        }
        self.assertEqual(_attempt_record(attempt_row).attempt_id, attempt_row[0])
        for name, (index, replacement) in attempt_tampering.items():
            with self.subTest(attempt_command_field=name):
                tampered_attempt = list(attempt_row)
                tampered_attempt[index] = replacement
                with self.assertRaises(DurableRegistryError):
                    _attempt_record(tuple(tampered_attempt))

        telemetry_cursor = Mock()
        telemetry_cursor.fetchall.return_value = [telemetry_row]
        counter_cursor = Mock()
        counter_cursor.fetchall.return_value = [
            ("EXTERNAL_MUTATION_REQUEST_COUNT", "not-an-integer")
        ]
        connection = Mock()
        connection.execute.side_effect = (telemetry_cursor, counter_cursor)
        with patch.object(
            self.application.database,
            "read",
            return_value=nullcontext(connection),
        ):
            with self.assertRaises(DurableRegistryError):
                self.application._durable_registry.processing_telemetry(operation_id)

    def test_keyed_replay_and_anonymous_identity_are_restart_safe(self) -> None:
        data = self.root / "restart-identity-data"
        first = ScenarioApplication.open(data)
        keyed = first.instantiate("doi-full-ds", "durable-instance-key")
        anonymous = first.instantiate("doi-full-ds")

        del first
        reopened = ScenarioApplication.open(data)
        replay = reopened.instantiate("doi-full-ds", "durable-instance-key")
        self.assertEqual(replay.order_id, keyed.order_id)
        with self.assertRaises(ApplicationError) as conflict:
            reopened.instantiate("doi-overlap", "durable-instance-key")
        self.assertEqual(
            conflict.exception.code,
            "IDEMPOTENCY_KEY_MATERIAL_CONFLICT",
        )
        fresh = reopened.instantiate("doi-full-ds")
        self.assertNotEqual(fresh.order_id, anonymous.order_id)
        self.assertEqual(len(reopened.list_orders()), 3)

    def test_public_manifest_is_exactly_recomputable_from_closed_line_mappings(self) -> None:
        for index, alias in enumerate(
            ("sales-credit-target-rep", "doi-fulfillment-split", "doi-zero-lines"),
            start=1,
        ):
            with self.subTest(alias=alias):
                detail = self.application.instantiate(alias, f"manifest-{index}")
                mappings = tuple(line.to_dict() for line in detail.lines)
                self.assertEqual(
                    detail.completeness.ordered_line_manifest_digest,
                    ordered_line_manifest_digest_from_mappings(mappings),
                )
        detail = self.application.get_order(self.application.list_orders()[0].order_id)
        line = detail.lines[0].to_dict()
        line["unexpected"] = "closed"
        with self.assertRaises(ValueError):
            ordered_line_manifest_digest_from_mappings((line,))

    def test_public_quantities_are_canonical_strings_in_every_scenario_mode(self) -> None:
        instance = 0
        known_quantity_count = 0
        for scenario in self.application.list_scenarios():
            for mode in scenario.allowed_modes:
                instance += 1
                detail = self.application.instantiate(
                    scenario.alias, f"canonical-quantity-{instance}", mode
                )
                for line in detail.lines:
                    if line.quantity.tag != "KNOWN":
                        continue
                    known_quantity_count += 1
                    self.assertIs(type(line.quantity.value), str)
                    parsed = Quantity.from_json_value(line.quantity.value)
                    self.assertEqual(parsed.to_json_value(), line.quantity.value)
        self.assertGreater(known_quantity_count, 0)

    def test_manifest_rejects_numeric_quantity_and_non_sku_product_identity(self) -> None:
        detail = self.application.instantiate(
            "sales-credit-target-rep", "manifest-invalid-fields"
        )
        canonical = detail.lines[0].to_dict()

        numeric_quantity = deepcopy(canonical)
        numeric_quantity["quantity"]["value"] = 1  # type: ignore[index]
        with self.assertRaisesRegex(ValueError, "LINE_FACT_QUANTITY_INVALID"):
            ordered_line_manifest_digest_from_mappings((numeric_quantity,))

        wrong_product_namespace = deepcopy(canonical)
        wrong_product_namespace["product_id"] = "SYN-ORDER-NOT-A-SKU-0001"
        with self.assertRaisesRegex(ValueError, "LINE_MANIFEST_LINE_INVALID"):
            ordered_line_manifest_digest_from_mappings((wrong_product_namespace,))

        non_money_line_value = deepcopy(canonical)
        non_money_line_value["line_value"]["value"] = "10.00"  # type: ignore[index]
        with self.assertRaisesRegex(ValueError, "LINE_FACT_MONEY_INVALID"):
            ordered_line_manifest_digest_from_mappings((non_money_line_value,))

    def test_line_field_policy_rejects_reason_swaps_and_invalid_known_values(self) -> None:
        unknown_availability = {
            "reason_code": "RC-017",
            "tag": "UNKNOWN",
            "value": None,
        }
        with self.assertRaisesRegex(ValueError, "LINE_FACT_UNKNOWN_REASON_INVALID"):
            validate_line_fact("availability", unknown_availability)

        with self.assertRaisesRegex(ValueError, "LINE_FACT_ENUM_INVALID"):
            validate_line_fact(
                "activity",
                {"reason_code": None, "tag": "KNOWN", "value": "NOT_ACTIVE"},
            )
        with self.assertRaisesRegex(ValueError, "LINE_FACT_TIMESTAMP_INVALID"):
            validate_line_fact(
                "eta",
                {
                    "reason_code": None,
                    "tag": "KNOWN",
                    "value": "2026-08-22 12:00:00",
                },
            )

    def test_published_line_manifest_known_answer_digest_remains_exact(self) -> None:
        line = {
            "activity": {"reason_code": None, "tag": "KNOWN", "value": "ACTIVE"},
            "availability": {
                "reason_code": None,
                "tag": "KNOWN",
                "value": "IN_STOCK",
            },
            "drop_ship_state": {
                "reason_code": None,
                "tag": "KNOWN",
                "value": "NON_DS",
            },
            "eta": {
                "reason_code": None,
                "tag": "KNOWN",
                "value": "2026-08-22T12:00:00Z",
            },
            "line_id": "SYN-EVIDENCE-PORTAL-LINE-0001",
            "line_index": 1,
            "line_value": {
                "reason_code": None,
                "tag": "KNOWN",
                "value": {
                    "amount": "10.00",
                    "currency_code": "USD",
                    "currency_registry_version": (
                        "synthetic-iso-style-currency-registry/v1"
                    ),
                    "currency_scale": 2,
                },
            },
            "product_id": "SYN-SKU-PORTAL-0001",
            "quantity": {"reason_code": None, "tag": "KNOWN", "value": "1"},
        }
        self.assertEqual(
            ordered_line_manifest_digest_from_mappings((line,)),
            "6cd6f84917dcddcd376f9c835a2087f0a94390aca6939174c78c343c229c454f",
        )

    def test_complete_unknown_long_zero_and_fail_closed_representation_modes(self) -> None:
        cases = (
            ("doi-fulfillment-split", "complete", "COMPLETE", 2),
            ("doi-long-order", "large", "COMPLETE", 64),
            ("doi-zero-lines", "zero-relevant-lines", "COMPLETE", 0),
            ("doi-fulfillment-split", "missing-required-section", "INCOMPLETE", 2),
            ("doi-fulfillment-split", "identity-mismatch", "INCOMPLETE", 2),
            ("doi-fulfillment-split", "duplicate-line", "INCOMPLETE", 3),
            ("doi-fulfillment-split", "declared-rendered-mismatch", "INCOMPLETE", 2),
            ("doi-fulfillment-split", "stale-source-changed", "INCOMPLETE", 2),
            ("doi-fulfillment-split", "dom-payload-mismatch", "INCOMPLETE", 2),
            ("doi-fulfillment-split", "malformed-value", "MALFORMED", 2),
            ("doi-unknown-containment", "observed-unknown", "COMPLETE", 3),
            ("doi-fulfillment-split", "backend-evaluation-failure", "COMPLETE", 2),
        )
        evaluable = {"complete", "large", "zero-relevant-lines", "observed-unknown"}
        for index, (alias, mode, state, count) in enumerate(cases, start=1):
            with self.subTest(mode=mode):
                detail = self.application.instantiate(
                    alias, f"representation-{index}", mode
                )
                self.assertEqual(
                    (detail.completeness.state, len(detail.lines)),
                    (state, count),
                )
                if mode == "malformed-value":
                    self.assertEqual(detail.lines[0].quantity.tag, "MALFORMED")
                    self.assertIsNone(detail.completeness.ordered_line_manifest_digest)
                if mode in evaluable:
                    result = self.application.evaluate(
                        detail.order_id, f"representation-evaluate-{index}"
                    )
                    self.assertFalse(result.conflict)
                else:
                    with self.assertRaises(ApplicationError) as captured:
                        self.application.evaluate(
                            detail.order_id, f"representation-evaluate-{index}"
                        )
                    expected_code = (
                        "BACKEND_EVALUATION_FAILURE"
                        if mode == "backend-evaluation-failure"
                        else "SOURCE_REPRESENTATION_NOT_EVALUABLE"
                    )
                    self.assertEqual(captured.exception.code, expected_code)
                self.assertEqual(
                    self.application.get_history(detail.order_id).telemetry_event_count,
                    1,
                )
        metrics = self.application.metrics_summary()
        self.assertEqual(metrics.total_processed, len(cases))
        self.assertEqual(metrics.failed_closed_count, len(cases) - len(evaluable))

    def test_incomplete_and_malformed_sources_remain_distinct(self) -> None:
        incomplete = self.application.instantiate(
            "malformed-input", "malformed-incomplete", "incomplete"
        )
        malformed = self.application.instantiate(
            "malformed-input", "malformed-malformed", "malformed"
        )
        self.assertEqual(incomplete.completeness.state, "INCOMPLETE")
        self.assertEqual(malformed.completeness.state, "MALFORMED")
        with self.assertRaises(ApplicationError) as captured:
            self.application.evaluate(incomplete.order_id, "evaluate-incomplete")
        self.assertEqual(captured.exception.code, "SOURCE_REPRESENTATION_NOT_EVALUABLE")
        self.assertEqual(
            self.application.get_history(incomplete.order_id).telemetry_event_count,
            1,
        )
        result = self.application.evaluate(malformed.order_id, "evaluate-malformed")
        self.assertEqual(result.top_level_result, "INVALID_INPUT")

    def test_real_sales_credit_evaluation_persists_replay_and_safe_history(self) -> None:
        detail = self.application.instantiate(
            "sales-credit-target-rep", "sales-credit-evaluation"
        )
        first = self.application.evaluate(detail.order_id, "sales-credit-request")
        replay = self.application.evaluate(detail.order_id, "sales-credit-request")
        self.assertEqual(first.top_level_result, "CREDIT_CONFIRMED_TARGET_REP")
        self.assertFalse(first.replayed)
        self.assertTrue(replay.replayed)
        self.assertEqual(first.command_id, replay.command_id)
        self.assertIsNotNone(first.evaluation_id)
        self.assertEqual(
            tuple(stage.stage for stage in first.processing_stages),
            ("RULE_EVALUATION", "PERSISTENCE", "TOTAL"),
        )
        history = self.application.get_history(detail.order_id)
        self.assertGreaterEqual(len(history.events), 1)
        self.assertGreaterEqual(len(history.artifacts), 2)
        self.assertEqual(history.exact_replay_count, 1)
        self.assertEqual(history.conflict_count, 0)
        self.assertEqual(history.telemetry_event_count, 2)
        self.assertEqual(len(history.receipts), 2)
        self.assertNotIn("canonical", str(history.to_dict()).lower())

    def test_real_doi_edge_scenarios_preserve_engine_results(self) -> None:
        expected = {
            "doi-overlap": (
                "DOI_OPPORTUNITY",
                ("RC-031", "RC-033", "RC-052", "RC-087"),
                ("EXACT_SKU_RECHECK", "FULFILLMENT_SPLIT"),
            ),
            "doi-long-order": (
                "DOI_OPPORTUNITY",
                ("RC-031", "RC-052"),
                ("FULFILLMENT_SPLIT",),
            ),
            "doi-unknown-containment": (
                "DOI_OPPORTUNITY",
                ("RC-016", "RC-031", "RC-052"),
                ("FULFILLMENT_SPLIT",),
            ),
            "doi-partial-quantity": (
                "DOI_OPPORTUNITY",
                ("RC-032", "RC-052"),
                ("PARTIAL_QUANTITY_REVIEW",),
            ),
            "doi-dedupe-review": (
                "DOI_MONITOR",
                ("RC-038", "RC-039", "RC-058"),
                (),
            ),
            "doi-zero-lines": ("DOI_MONITOR", (), ()),
        }
        fixture_oracles = {
            item.alias: item.application_oracle for item in DOI_APPLICATION_FIXTURES
        }
        self.assertTrue(all(item is not None for item in fixture_oracles.values()))
        for index, (alias, oracle) in enumerate(expected.items(), start=1):
            with self.subTest(alias=alias):
                detail = self.application.instantiate(alias, f"doi-edge-{index}")
                result = self.application.evaluate(detail.order_id, f"doi-run-{index}")
                state, reasons, opportunities = oracle
                self.assertEqual(result.top_level_result, state)
                self.assertEqual(result.reasons, reasons)
                self.assertEqual(
                    tuple(
                        sorted(item.opportunity_type for item in result.opportunities)
                    ),
                    opportunities,
                )
                self.assertIsNotNone(result.run_id)
                self.assertIsNotNone(result.snapshot_id)
                self.assertIsNotNone(result.evaluation_id)
        overlap = self.application.list_orders()
        overlap_order = next(
            item.order_id for item in overlap if item.scenario_alias == "doi-overlap"
        )
        overlap_result = self.application.get_order(overlap_order).latest_evaluation
        self.assertIsNotNone(overlap_result)
        assert overlap_result is not None
        self.assertEqual(len(overlap_result.opportunities), 2)
        self.assertEqual(overlap_result.aggregate_potential_status, "UNAVAILABLE")
        self.assertIsNone(overlap_result.aggregate_potential_value)

    def test_cancellation_replacement_uses_real_sales_credit_evaluator(self) -> None:
        detail = self.application.instantiate(
            "sales-credit-cancellation-replacement",
            "cancellation-replacement",
        )
        result = self.application.evaluate(
            detail.order_id,
            "cancellation-replacement-evaluate",
        )
        self.assertEqual(
            result.top_level_result,
            "CANCELED_REPLACEMENT_WINDOW_ACTIVE",
        )
        self.assertIn("REPLACEMENT_WINDOW_ACTIVE", result.reasons)

    def test_evaluation_never_mutates_source_facts(self) -> None:
        for index, alias in enumerate(
            ("sales-credit-target-rep", "doi-overlap"),
            start=1,
        ):
            with self.subTest(alias=alias):
                before = self.application.instantiate(alias, f"immutable-source-{index}")
                source_projection = {
                    "completeness": before.completeness.to_dict(),
                    "created_at": before.created_at,
                    "interaction_ids": before.interaction_ids,
                    "lines": tuple(line.to_dict() for line in before.lines),
                    "order_id": before.order_id,
                    "order_status": before.order_status,
                    "rule_pack": before.rule_pack,
                    "source_status": before.source_status,
                }
                self.application.evaluate(
                    before.order_id,
                    f"immutable-source-evaluate-{index}",
                )
                after = self.application.get_order(before.order_id)
                self.assertEqual(
                    {
                        "completeness": after.completeness.to_dict(),
                        "created_at": after.created_at,
                        "interaction_ids": after.interaction_ids,
                        "lines": tuple(line.to_dict() for line in after.lines),
                        "order_id": after.order_id,
                        "order_status": after.order_status,
                        "rule_pack": after.rule_pack,
                        "source_status": after.source_status,
                    },
                    source_projection,
                )
                self.assertIsNone(before.latest_evaluation)
                self.assertIsNotNone(after.latest_evaluation)

    def test_doi_history_exposes_attention_values_transitions_and_no_synthetic_actions(
        self,
    ) -> None:
        manual = self.application.instantiate("doi-manual-review", "history-manual")
        self.application.evaluate(manual.order_id, "history-manual-evaluate")
        manual_history = self.application.get_history(manual.order_id)
        self.assertTrue(manual_history.attention_causes)
        self.assertEqual(
            {item.transition_id for item in manual_history.attention_causes},
            {"TR-037"},
        )

        overlap = self.application.instantiate("doi-overlap", "history-overlap")
        self.application.evaluate(overlap.order_id, "history-overlap-evaluate")
        overlap_history = self.application.get_history(overlap.order_id)
        self.assertTrue(overlap_history.attention_causes)
        self.assertGreaterEqual(len(overlap_history.value_events), 3)
        self.assertEqual(
            {item.transition_id for item in overlap_history.value_events},
            {"TR-034"},
        )
        self.assertEqual(overlap_history.intervention_events, ())
        with self.application.database.read() as connection:
            counts = (
                int(
                    connection.execute(
                        "SELECT COUNT(*) FROM doi_interventions"
                    ).fetchone()[0]
                ),
                int(
                    connection.execute(
                        "SELECT COUNT(*) FROM doi_value_events"
                    ).fetchone()[0]
                ),
                int(
                    connection.execute(
                        "SELECT COUNT(*) FROM sc_manager_outcomes"
                    ).fetchone()[0]
                ),
            )
        self.assertEqual(counts, (0, 0, 0))

    def test_typed_sales_credit_history_fails_closed_on_corrupt_material(self) -> None:
        detail = self.application.instantiate(
            "sales-credit-target-rep",
            "corrupt-sales-credit-history",
        )
        self.application.evaluate(detail.order_id, "corrupt-sales-credit-evaluation")
        with self.application.database.write() as connection:
            connection.execute(
                "INSERT INTO sc_manager_outcomes "
                "(occurrence_id, order_id, outcome, decided_at, recorded_at, "
                "actor_id, approved_minor_units, approved_currency, "
                "approved_registry_version, approved_scale, material_sha256, "
                "canonical_bytes) VALUES (?, ?, 'APPROVED', ?, ?, ?, NULL, "
                "NULL, NULL, NULL, ?, ?)",
                (
                    "SYN-EVIDENCE-M5-CORRUPT-MANAGER-0001",
                    detail.order_id,
                    "2026-08-21T12:00:00Z",
                    "2026-08-21T12:00:00Z",
                    "SYN-REP-M5-CORRUPT-0001",
                    "0" * 64,
                    b"{}",
                ),
            )
        with self.assertRaises(ApplicationError) as captured:
            self.application.get_history(detail.order_id)
        self.assertEqual(
            captured.exception.code,
            "APPLICATION_PERSISTED_HISTORY_INVALID",
        )

    def test_typed_doi_history_fails_closed_on_projection_corruption(self) -> None:
        detail = self.application.instantiate("doi-overlap", "corrupt-doi-history")
        result = self.application.evaluate(detail.order_id, "corrupt-doi-evaluation")
        self.assertIsNotNone(result.case_id)
        self.assertIsNotNone(result.evaluation_id)
        with self.application.database.write() as connection:
            row = connection.execute(
                "SELECT a.artifact_pk FROM doi_evaluations e "
                "JOIN doi_case_artifacts a ON a.artifact_pk=e.record_artifact_pk "
                "WHERE e.evaluation_id=?",
                (result.evaluation_id,),
            ).fetchone()
            self.assertIsNotNone(row)
            assert row is not None
            connection.execute("DROP TRIGGER doi_immutable_case_artifact")
            connection.execute(
                "UPDATE doi_case_artifacts SET record_sha256=? WHERE artifact_pk=?",
                ("0" * 64, row[0]),
            )
        with self.assertRaises(ApplicationError) as captured:
            self.application.get_history(detail.order_id)
        self.assertEqual(
            captured.exception.code,
            "APPLICATION_PERSISTED_HISTORY_INVALID",
        )

    def test_evaluation_request_key_conflict_is_closed_and_counted(self) -> None:
        first = self.application.instantiate("doi-full-ds", "conflict-first")
        second = self.application.instantiate("doi-overlap", "conflict-second")
        self.application.evaluate(first.order_id, "shared-evaluation-key")
        with self.assertRaises(ApplicationError) as captured:
            self.application.evaluate(second.order_id, "shared-evaluation-key")
        self.assertEqual(captured.exception.category, "CONFLICT")
        history = self.application.get_history(second.order_id)
        self.assertEqual(history.conflict_count, 1)
        self.assertEqual(history.telemetry_event_count, 1)
        metrics = self.application.metrics_summary()
        self.assertEqual(metrics.conflict_count, 1)
        self.assertEqual(metrics.total_processed, 2)

    def test_interaction_and_run_views_are_allowlisted_and_privacy_safe(self) -> None:
        sales = self.application.instantiate(
            "sales-credit-human-review", "interaction-view"
        )
        interaction = self.application.get_interaction(sales.interaction_ids[0])
        rendered = interaction.to_dict()
        self.assertEqual(rendered["identifier_kind"], "EMAIL")
        self.assertNotIn("@", str(rendered))
        self.assertNotIn("body", rendered)
        evaluation = self.application.evaluate(sales.order_id, "interaction-view-evaluate")
        self.assertIsNotNone(evaluation.run_id)
        assert evaluation.run_id is not None
        run = self.application.get_run(evaluation.run_id)
        self.assertEqual(run.rule_pack, "SALES_CREDIT")
        self.assertNotIn("path", run.to_dict())

    def test_status_metrics_and_exact_closed_versions(self) -> None:
        status = self.application.system_status(deep=True)
        self.assertEqual(status.database_status, "PASS")
        self.assertEqual(status.database_schema_version, 4)
        self.assertEqual(status.expected_schema_version, 4)
        self.assertEqual(status.build_version, APPLICATION_BUILD_VERSION)
        self.assertEqual(status.to_dict()["schema_version"], APPLICATION_SCHEMA_VERSION)
        self.assertEqual(tuple(name for name, _ in status.safety_counters), SAFETY_COUNTER_NAMES)
        self.assertEqual({value for _, value in status.safety_counters}, {0})
        metrics = self.application.metrics_summary()
        self.assertEqual(metrics.total_processed, 0)
        self.assertEqual(metrics.success_rate_denominator, 0)

    def test_status_fails_for_nonzero_system_or_incomplete_telemetry_counter_set(self) -> None:
        with self.application.database.write() as connection:
            connection.execute(
                "UPDATE system_safety_counters SET counter_value = 1 "
                "WHERE counter_name = 'PRODUCTION_SYSTEM_ACCESS_COUNT'"
            )
        status = self.application.system_status()
        self.assertEqual(status.database_status, "FAIL")

        second = ScenarioApplication.open(self.root / "telemetry-data")
        detail = second.instantiate("sales-credit-target-rep", "telemetry-status")
        second.evaluate(detail.order_id, "telemetry-status-evaluate")
        with second.database.write() as connection:
            operation = str(
                connection.execute(
                    "SELECT operation_id FROM processing_telemetry LIMIT 1"
                ).fetchone()[0]
            )
            connection.execute(
                "DELETE FROM telemetry_safety_counters "
                "WHERE operation_id = ? AND counter_name = ?",
                (operation, SAFETY_COUNTER_NAMES[0]),
            )
        self.assertEqual(second.system_status().database_status, "FAIL")


if __name__ == "__main__":
    unittest.main()
