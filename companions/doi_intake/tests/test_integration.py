"""Repository entry point and review-handoff tests; all order data is fictional."""
from __future__ import annotations

import contextlib
import copy
import dataclasses
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from companions.doi_intake import __main__ as cli
from companions.doi_intake import doi_intake as d
from companions.doi_intake.handoff import load_review_queue

ROOT = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 9, 23, 16, tzinfo=timezone.utc)


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.plan = d.make_plan(d.demo_source(), "integration-run", history=d.demo_history())
        self.folder, _ = d.save_bundle(self.plan, self.root)

    def load(self, **kw):
        args = {"expected_run_id": "integration-run", "expected_source_date": "2026-09-23",
                "now": NOW, "allow_synthetic": True}
        return load_review_queue(self.folder, **(args | kw))

    def repack(self, plan):
        # Recalculate the plan hash and all file checksums, simulating internally
        # inconsistent producer output rather than an easy checksum mismatch.
        material = {k: v for k, v in plan.items() if k not in
                    {"source", "warnings", "plan_fingerprint"}}
        material["source_identity"] = {k: plan["source"][k] for k in
            ("kind", "spreadsheet_id", "tab", "gid", "source_date", "source_date_basis")}
        plan["plan_fingerprint"] = d.digest(material)
        manifest = d.decode_json((self.folder / "manifest.json").read_text())
        manifest["plan_fingerprint"] = plan["plan_fingerprint"]
        for name, data in d.bundle_files(plan).items():
            (self.folder / name).write_bytes(data)
            manifest["files"][name] = hashlib.sha256(data).hexdigest()
        (self.folder / "manifest.json").write_bytes(d.json_bytes(manifest))

    def test_valid_queue_preserves_holds_and_never_authorizes(self):
        result = self.load()
        self.assertEqual(len(result["lookup_queue"]), 6)
        self.assertEqual(result["held_order_numbers"], ["91000004"])
        self.assertFalse(result["execution_authorized"])
        self.assertEqual(result["order_admin_reads"], 0)
        self.assertEqual(result["synthetic_database_writes"], 0)
        self.assertEqual(result["status"], "SYNTHETIC_REVIEW_ONLY")

    def test_synthetic_blocked_without_explicit_flag(self):
        with self.assertRaises(d.IntakeError) as error:
            self.load(allow_synthetic=False)
        self.assertEqual(error.exception.code, "SYNTHETIC_QUEUE_BLOCKED")

    def test_mismatched_run(self):
        with self.assertRaises(d.IntakeError): self.load(expected_run_id="wrong-run")

    def test_mismatched_source_date(self):
        with self.assertRaises(d.IntakeError): self.load(expected_source_date="2026-09-16")

    def test_stale_capture(self):
        with self.assertRaises(d.IntakeError) as error:
            self.load(now=NOW + timedelta(hours=4))
        self.assertEqual(error.exception.code, "QUEUE_NOT_FRESH")

    def test_future_capture(self):
        with self.assertRaises(d.IntakeError): self.load(now=NOW - timedelta(hours=2))

    def test_capture_age_boundary(self):
        self.assertEqual(self.load(now=NOW + timedelta(hours=3))["counts"]["lookup_orders"], 6)

    def test_invalid_age_limits(self):
        for age in (0, -1, 25, True, 2.5, "4"):
            with self.subTest(age=age), self.assertRaises(d.IntakeError):
                self.load(max_age_hours=age)

    def test_naive_clock(self):
        with self.assertRaises(d.IntakeError): self.load(now=datetime(2026, 9, 23, 16))

    def test_bad_authority_and_version_fields(self):
        mutations = [
            ("execution_authorized", True), ("order_admin_reads", 1),
            ("source_writes", True), ("schema_version", "unknown"),
            ("version", "99.0.0"), ("candidate_queue_prepared", False),
            ("stage", "POST_ORDER_ADMIN"), ("integration_state", "READY_TO_EXECUTE"),
        ]
        for field, value in mutations:
            with self.subTest(field=field):
                plan = copy.deepcopy(self.plan); plan[field] = value; self.repack(plan)
                with self.assertRaises(d.IntakeError): self.load()

    def test_count_types_and_inconsistent_totals(self):
        for value in (True, -1, 0, 99, "6"):
            with self.subTest(value=value):
                plan = copy.deepcopy(self.plan); plan["counts"]["lookup_orders"] = value
                self.repack(plan)
                with self.assertRaises(d.IntakeError): self.load()

    def test_false_reconciliation(self):
        self.plan["reconciliation"]["grid_reconciles"] = False; self.repack(self.plan)
        with self.assertRaises(d.IntakeError): self.load()

    def test_queue_duplicate_rejected_after_rehash(self):
        self.plan["lookup_queue"].append(copy.deepcopy(self.plan["lookup_queue"][0]))
        self.repack(self.plan)
        with self.assertRaises(d.IntakeError): self.load()

    def test_duplicate_source_row_across_jobs(self):
        self.plan["lookup_queue"][1]["source_rows"] = [2]
        self.plan["lookup_queue"][1]["first_source_row"] = 2
        self.repack(self.plan)
        with self.assertRaises(d.IntakeError): self.load()

    def test_hold_cannot_be_moved_to_lookup_without_validation(self):
        self.plan["lookup_queue"].append(self.plan["held_orders"].pop())
        self.repack(self.plan)
        with self.assertRaises(d.IntakeError): self.load()

    def test_bad_job_fields(self):
        changes = [("assigned_rep", "OTHER"), ("state", "COMPLETE"),
                   ("requires_fresh_order_admin_read", False), ("queue_position", True),
                   ("run_order_key", "another-run|91000001"), ("priority_group", 3),
                   ("source_rows", [0]), ("first_source_row", 3)]
        for field, value in changes:
            with self.subTest(field=field):
                plan = copy.deepcopy(self.plan); plan["lookup_queue"][0][field] = value
                self.repack(plan)
                with self.assertRaises(d.IntakeError): self.load()

    def test_unknown_fields_rejected(self):
        self.plan["lookup_queue"][0]["customer_email"] = "fictional@example.test"
        self.repack(self.plan)
        with self.assertRaises(d.IntakeError): self.load()

    def test_wrong_workbook_or_tab_or_source_proof(self):
        for field, value in [("spreadsheet_id", "wrong"), ("tab", "Wrong"),
                             ("gid", True), ("requested_record_columns", ["A", "B", "E"]),
                             ("kind", "UNKNOWN"), ("consistency", "REVISION_LOCKED")]:
            with self.subTest(field=field):
                plan = copy.deepcopy(self.plan); plan["source"][field] = value
                self.repack(plan)
                with self.assertRaises(d.IntakeError): self.load()

    def test_bad_source_fingerprint(self):
        self.plan["source_fingerprint"] = "0" * 64; self.repack(self.plan)
        with self.assertRaises(d.IntakeError): self.load()

    def test_corrupted_file(self):
        (self.folder / "lookup_queue.csv").write_text("corrupt")
        with self.assertRaises(d.IntakeError): self.load()

    def test_rehashed_report_disagreement(self):
        manifest = d.decode_json((self.folder / "manifest.json").read_text())
        content = b'{"wrong_report":true}\n'
        (self.folder / "report.json").write_bytes(content)
        manifest["files"]["report.json"] = hashlib.sha256(content).hexdigest()
        (self.folder / "manifest.json").write_bytes(d.json_bytes(manifest))
        with self.assertRaises(d.IntakeError): self.load()

    def test_occurrence_mismatch(self):
        self.plan["source_occurrences"].pop(); self.repack(self.plan)
        with self.assertRaises(d.IntakeError): self.load()

    def test_wrong_historical_order_cannot_leak_into_review(self):
        job = next(j for j in self.plan["lookup_queue"] if j["historical_context"])
        job["historical_context"]["observations"][0]["order_number"] = "91009999"
        self.repack(self.plan)
        with self.assertRaises(d.IntakeError): self.load()

    def test_followup_sort_and_old_terminal_statuses(self):
        plan = d.make_plan(d.demo_source(), "followups", sort="followups", history=d.demo_history())
        self.folder, _ = d.save_bundle(plan, self.root)
        result = self.load(expected_run_id="followups")
        self.assertEqual(result["lookup_queue"][0]["order_number"], "91000003")
        self.assertTrue({"91000006", "91000008", "91000009"}.issubset(
            {j["order_number"] for j in result["lookup_queue"]}))

    def test_empty_jude_source_is_valid_empty_review(self):
        source = dataclasses.replace(d.demo_source(), rows=((d.Cell("TEXT", "91000001"),
                                                            d.Cell("TEXT", "Other Rep")),), row_count=2)
        self.folder, _ = d.save_bundle(d.make_plan(source, "empty"), self.root)
        self.assertEqual(self.load(expected_run_id="empty")["lookup_queue"], [])

    def test_conflicting_history_stays_visible(self):
        history = d.demo_history()
        record = copy.deepcopy(history["records"][0]); record["lookup_state"] = "completed"
        history["records"].append(record)
        self.folder, _ = d.save_bundle(d.make_plan(d.demo_source(), "history-conflict",
                                                 sort="followups", history=history), self.root)
        queue = self.load(expected_run_id="history-conflict")["lookup_queue"]
        self.assertTrue(next(j for j in queue if j["order_number"] == "91000003")
                        ["historical_context"]["conflicting_latest"])


class EntryPointTests(unittest.TestCase):
    def invoke(self, args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = cli.main(args)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_default_startup_is_offline(self):
        with mock.patch.object(d, "google_session") as session:
            code, out, _ = self.invoke([])
        self.assertEqual(code, 0); self.assertIn("separate companion", out)
        session.assert_not_called()

    def test_live_read_requires_explicit_enable(self):
        with mock.patch.object(d, "main") as run:
            for command in ("auth", "sheets"):
                code, _, error = self.invoke([command])
                self.assertEqual(code, 2); self.assertIn("GOOGLE_NOT_ENABLED", error)
            run.assert_not_called()

    def test_explicit_enable_forwards_only_after_validation(self):
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(d, "main", return_value=0) as run:
            args = ["sheets", "--day", "wednesday", "--source-date", "2026-09-23",
                    "--run-id", "test", "--out", temp, "--token", str(Path(temp) / "token.json")]
            self.assertEqual(self.invoke(["--enable-google"] + args)[0], 0)
            run.assert_called_once_with(args)

    def test_generated_data_inside_checkout_blocked(self):
        with mock.patch.object(d, "main") as run:
            code, _, error = self.invoke(["demo", "--out", str(ROOT / "runs")])
            self.assertEqual(code, 2); self.assertIn("REPOSITORY_DATA_PATH_FORBIDDEN", error)
            run.assert_not_called()

    def test_oauth_client_inside_checkout_blocked(self):
        with mock.patch.object(d, "main") as run:
            code, _, _ = self.invoke(["--enable-google", "auth", "--client-secret",
                                     str(ROOT / "credentials.json")])
            self.assertEqual(code, 2); run.assert_not_called()

    def test_token_inside_checkout_blocked(self):
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(d, "main") as run:
            code, _, _ = self.invoke(["--enable-google", "auth", "--client-secret",
                                     str(Path(temp) / "client.json"), "--token",
                                     str(ROOT / "token.json")])
            self.assertEqual(code, 2); run.assert_not_called()

    def test_history_inside_checkout_blocked(self):
        with mock.patch.object(d, "main") as run:
            self.assertEqual(self.invoke(["demo", "--history", str(ROOT / "history.json")])[0], 2)
            run.assert_not_called()

    def test_review_in_checkout_blocked(self):
        code, _, _ = self.invoke(["review", str(ROOT / "runs"), "--run-id", "test",
                                 "--source-date", "2026-09-23"])
        self.assertEqual(code, 2)

    def test_non_sensitive_error_output(self):
        with mock.patch.object(d, "main", side_effect=ValueError("SECRET-DO-NOT-PRINT")):
            code, _, error = self.invoke(["demo"])
        self.assertEqual(code, 2); self.assertNotIn("SECRET", error)

    def test_module_demo_then_verify_subprocess(self):
        with tempfile.TemporaryDirectory() as temp:
            command = [sys.executable, "-m", "companions.doi_intake"]
            result = subprocess.run(command + ["demo", "--out", temp], cwd=ROOT,
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual(data["counts"]["lookup_orders"], 6)
            result = subprocess.run(command + ["verify", str(Path(temp) / "demo-wednesday")],
                                    cwd=ROOT, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_preserved_v1_script_bytes(self):
        expected = "e0172417ae2820414eb8bdb01f27416f1a8edb6e9255a6dbaad965a194892f2b"
        self.assertEqual(hashlib.sha256(Path(d.__file__).read_bytes()).hexdigest(), expected)

    def test_windows_launcher_is_separate_from_core_start(self):
        text = (ROOT / "DOI_INTAKE.cmd").read_text()
        self.assertIn("-m companions.doi_intake", text)
        self.assertIn("SSA_DOI_PYTHON", text)
        self.assertNotIn("synthetic_sales_assist", text)


if __name__ == "__main__":
    unittest.main()
