from __future__ import annotations

import importlib
import json
import tempfile
import unittest
from io import StringIO
from pathlib import Path

from synthetic_sales_assist.cli.commands import (
    EXIT_DATABASE,
    EXIT_SAFETY,
    EXIT_SUCCESS,
    main,
)
from synthetic_sales_assist.demos import AuditView, DemoRunView
from synthetic_sales_assist.persistence.database import SQLiteDatabase
from synthetic_sales_assist.persistence.paths import resolve_data_paths
from synthetic_sales_assist.persistence.telemetry import SAFETY_COUNTER_NAMES


class _Backend:
    def run_demo(self, alias: str, request_key: str | None) -> DemoRunView:
        return DemoRunView(
            scenario=alias,
            rule_pack="SALES_CREDIT",
            synthetic_ids=("SYN-ORDER-M4-CLI-0001",),
            top_level_result="CREDIT_CONFIRMED_TARGET_REP",
            workflow_state="CREDIT_CONFIRMED_TARGET_REP",
            reasons=("RC-PLACED-VALUE-PROVED", "RC-TARGET-REP"),
            opportunities=(),
            human_review_required=False,
            run_id="SYN-RUN-M4-CLI-0001",
            evaluation_id="SYN-EVALUATION-M4-CLI-0001",
            case_id="SYN-EVIDENCE-CASE-M4-CLI-0001",
            exact_replay=request_key == "replay-key",
            conflict=False,
            processing_duration_ns=100,
        )

    def order_show(self, synthetic_order_id: str) -> AuditView:
        return AuditView("ORDER", synthetic_order_id, (("state", "KNOWN"),))

    def case_history(self, synthetic_order_id: str) -> AuditView:
        return AuditView("CASE_HISTORY", synthetic_order_id, (("state", "OPEN"),))

    def run_show(self, synthetic_run_id: str) -> AuditView:
        return AuditView("RUN", synthetic_run_id, (("state", "COMPLETED"),))


def _run(argv: list[str], backend: _Backend | None = None) -> tuple[int, dict[str, object]]:
    output = StringIO()
    errors = StringIO()
    exit_code = main(argv, backend=backend, stdout=output, stderr=errors)
    rendered = output.getvalue() or errors.getvalue()
    parsed: dict[str, object] = json.loads(rendered)
    return exit_code, parsed


class Milestone4CLITests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="synthetic-sales-assist-m4-cli-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_cli_required_aliases_and_stable_json_envelope(self) -> None:
        exit_code, envelope = _run(
            ["demo", "list", "--json", "--data-dir", str(self.root / "app")]
        )
        self.assertEqual(exit_code, EXIT_SUCCESS)
        self.assertEqual(
            tuple(envelope),
            ("command", "errors", "ok", "result", "schema_version"),
        )
        result = envelope["result"]
        self.assertIsInstance(result, list)
        assert isinstance(result, list)
        self.assertEqual(
            [row["alias"] for row in result],
            [
                "doi-fulfillment-split",
                "doi-full-ds",
                "doi-manual-review",
                "doi-overlap",
                "malformed-input",
                "sales-credit-human-review",
                "sales-credit-target-rep",
            ],
        )

    def test_cli_init_doctor_verify_metrics_and_demo_adapter(self) -> None:
        data_dir = str(self.root / "app")
        for arguments in (
            ["--json", "--data-dir", data_dir, "db", "init"],
            ["doctor", "--data-dir", data_dir, "--json"],
            ["db", "verify", "--deep", "--json", "--data-dir", data_dir],
            ["metrics", "summary", "--data-dir", data_dir, "--json"],
        ):
            with self.subTest(arguments=arguments):
                exit_code, envelope = _run(arguments)
                self.assertEqual(exit_code, EXIT_SUCCESS, envelope)
                self.assertIs(envelope["ok"], True)

        exit_code, envelope = _run(
            [
                "demo",
                "run",
                "sales-credit-target-rep",
                "--request-key",
                "replay-key",
                "--json",
                "--data-dir",
                data_dir,
            ],
            _Backend(),
        )
        self.assertEqual(exit_code, EXIT_SUCCESS)
        result = envelope["result"]
        self.assertIsInstance(result, dict)
        assert isinstance(result, dict)
        self.assertIs(result["exact_replay"], True)
        self.assertTrue(str(result["database_path"]).endswith("synthetic_sales_assist.sqlite3"))

    def test_preinit_doctor_reports_closed_nine_counter_baseline_and_cleanup_command(self) -> None:
        data_dir = str(self.root / "preinit")
        exit_code, envelope = _run(
            ["--json", "--data-dir", data_dir, "doctor"]
        )
        self.assertEqual(exit_code, EXIT_SUCCESS, envelope)
        result = envelope["result"]
        self.assertIsInstance(result, dict)
        assert isinstance(result, dict)
        counters = result["safety_counters"]
        self.assertIsInstance(counters, dict)
        assert isinstance(counters, dict)
        self.assertEqual(tuple(sorted(counters)), SAFETY_COUNTER_NAMES)
        self.assertEqual(set(counters.values()), {0})
        self.assertEqual(
            result["safety_counter_source"],
            "CLOSED_BASELINE_DATABASE_NOT_INITIALIZED",
        )
        self.assertIs(result["schema_version"], None)

        cleanup_code, cleanup_envelope = _run(
            ["--json", "--data-dir", data_dir, "db", "purge-expired-backups"]
        )
        self.assertEqual(cleanup_code, EXIT_SUCCESS, cleanup_envelope)
        self.assertEqual(
            cleanup_envelope["result"],
            {"evaluated_count": 0, "purged_count": 0},
        )

    def test_cli_fails_closed_for_unknown_alias_without_echoing_input(self) -> None:
        exit_code, envelope = _run(
            [
                "--json",
                "--data-dir",
                str(self.root / "app"),
                "demo",
                "run",
                "not-a-demo",
            ]
        )
        self.assertEqual(exit_code, EXIT_SAFETY)
        self.assertEqual(envelope["errors"], ["DEMO_ALIAS_UNKNOWN"])
        self.assertNotIn("not-a-demo", json.dumps(envelope))

    def test_cli_default_backend_executes_every_alias_and_safe_inspection(self) -> None:
        data_dir = str(self.root / "concrete")
        expected = {
            "sales-credit-target-rep": "CREDIT_CONFIRMED_TARGET_REP",
            "sales-credit-human-review": "MANUAL_REVIEW_REQUIRED",
            "doi-fulfillment-split": "DOI_OPPORTUNITY",
            "doi-full-ds": "DOI_EXCLUDED",
            "doi-manual-review": "DOI_MANUAL_REVIEW",
            "doi-overlap": "DOI_OPPORTUNITY",
            "malformed-input": "INVALID_INPUT",
        }
        retained: dict[str, dict[str, object]] = {}
        for alias, top_level in expected.items():
            with self.subTest(alias=alias):
                exit_code, envelope = _run(
                    ["--json", "--data-dir", data_dir, "demo", "run", alias]
                )
                self.assertEqual(exit_code, EXIT_SUCCESS, envelope)
                result = envelope["result"]
                self.assertIsInstance(result, dict)
                assert isinstance(result, dict)
                self.assertEqual(result["top_level_result"], top_level)
                retained[alias] = result

        replay_code, replay_envelope = _run(
            [
                "--json",
                "--data-dir",
                data_dir,
                "demo",
                "run",
                "sales-credit-target-rep",
            ]
        )
        self.assertEqual(replay_code, EXIT_SUCCESS)
        replay = replay_envelope["result"]
        assert isinstance(replay, dict)
        self.assertIs(replay["exact_replay"], True)

        sales = retained["sales-credit-target-rep"]
        doi = retained["doi-fulfillment-split"]
        commands = (
            ("order", "show", str(sales["case_id"])),
            ("case", "history", str(sales["case_id"])),
            ("run", "show", str(sales["run_id"])),
            ("order", "show", str(doi["synthetic_ids"][0])),
            ("case", "history", str(doi["synthetic_ids"][0])),
            ("run", "show", str(doi["run_id"])),
        )
        for group, leaf, identity in commands:
            with self.subTest(group=group, identity=identity):
                exit_code, envelope = _run(
                    ["--json", "--data-dir", data_dir, group, leaf, identity]
                )
                self.assertEqual(exit_code, EXIT_SUCCESS, envelope)
                self.assertIs(envelope["ok"], True)

        exit_code, envelope = _run(
            ["--json", "--data-dir", data_dir, "metrics", "summary"]
        )
        self.assertEqual(exit_code, EXIT_SUCCESS)
        metrics = envelope["result"]
        assert isinstance(metrics, dict)
        self.assertEqual(metrics["total_processed"], 8)
        self.assertEqual(set(metrics["safety_counters"].values()), {0})

    def test_db_verify_is_deep_and_missing_database_fails_closed(self) -> None:
        missing = str(self.root / "missing")
        exit_code, envelope = _run(
            ["--json", "--data-dir", missing, "db", "verify"]
        )
        self.assertEqual(exit_code, EXIT_DATABASE)
        self.assertEqual(envelope["errors"], ["DATABASE_NOT_INITIALIZED"])

        data_dir = str(self.root / "verified")
        _run(["--json", "--data-dir", data_dir, "demo", "run", "doi-full-ds"])
        _run(
            [
                "--json",
                "--data-dir",
                data_dir,
                "demo",
                "run",
                "sales-credit-target-rep",
            ]
        )
        exit_code, envelope = _run(
            ["--json", "--data-dir", data_dir, "db", "verify", "--deep"]
        )
        self.assertEqual(exit_code, EXIT_SUCCESS, envelope)
        result = envelope["result"]
        assert isinstance(result, dict)
        self.assertEqual(result["projection_verification"], "ok")
        self.assertEqual(result["receipt_hash_verification"], "ok")
        self.assertEqual(result["safety_counter_verification"], "ok")

    def test_db_verify_detects_projection_receipt_and_counter_drift(self) -> None:
        cases = (
            ("projection", "SALES_CREDIT_PROJECTION_INVALID"),
            ("receipt", "DURABLE_RECEIPT_HASH_MISMATCH"),
            ("counter", "SYSTEM_SAFETY_COUNTER_INVALID"),
        )
        for kind, expected_code in cases:
            with self.subTest(kind=kind):
                data_dir = self.root / kind
                arguments = [
                    "--json",
                    "--data-dir",
                    str(data_dir),
                    "demo",
                    "run",
                    "sales-credit-target-rep",
                ]
                self.assertEqual(_run(arguments)[0], EXIT_SUCCESS)
                paths = resolve_data_paths(data_dir)
                database = SQLiteDatabase(paths.database)
                with database.write() as connection:
                    if kind == "projection":
                        connection.execute("DROP TRIGGER sc_cases_version_guard")
                        connection.execute(
                            "UPDATE sc_cases SET workflow_state = 'EVIDENCE_NEEDED', "
                            "projection_version = projection_version + 1"
                        )
                    elif kind == "receipt":
                        connection.execute(
                            """
                            INSERT INTO durable_commands (
                                command_id, natural_namespace, natural_key,
                                command_domain, command_sha256, command_bytes, accepted_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                "SYN-EVIDENCE-M4-INVALID-COMMAND",
                                "m4.verify",
                                "synthetic-invalid",
                                "m4-invalid-command/v1",
                                "0" * 64,
                                b"{}",
                                "2026-08-21T00:00:00Z",
                            ),
                        )
                        connection.execute(
                            """
                            INSERT INTO durable_command_receipts (
                                command_id, result_domain, result_sha256,
                                result_bytes, recorded_at
                            ) VALUES (?, ?, ?, ?, ?)
                            """,
                            (
                                "SYN-EVIDENCE-M4-INVALID-COMMAND",
                                "m4-invalid-result/v1",
                                "0" * 64,
                                b"{}",
                                "2026-08-21T00:00:00Z",
                            ),
                        )
                    else:
                        connection.execute(
                            "UPDATE system_safety_counters SET counter_value = 1 "
                            "WHERE counter_name = 'REAL_CUSTOMER_DATA_COUNT'"
                        )
                if kind == "counter":
                    doctor_code, doctor_envelope = _run(
                        ["--json", "--data-dir", str(data_dir), "doctor"]
                    )
                    self.assertEqual(doctor_code, EXIT_SUCCESS, doctor_envelope)
                    doctor = doctor_envelope["result"]
                    self.assertIsInstance(doctor, dict)
                    assert isinstance(doctor, dict)
                    safety_counters = doctor["safety_counters"]
                    self.assertIsInstance(safety_counters, dict)
                    assert isinstance(safety_counters, dict)
                    self.assertEqual(safety_counters["REAL_CUSTOMER_DATA_COUNT"], 1)
                exit_code, envelope = _run(
                    ["--json", "--data-dir", str(data_dir), "db", "verify"]
                )
                self.assertEqual(exit_code, EXIT_DATABASE)
                self.assertEqual(envelope["errors"], [expected_code])

    def test_cli_main_module_import_has_no_exit_side_effect(self) -> None:
        module = importlib.import_module("synthetic_sales_assist.cli.__main__")
        self.assertTrue(callable(module.main))


if __name__ == "__main__":
    unittest.main()
