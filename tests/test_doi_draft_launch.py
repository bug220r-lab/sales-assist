"""Isolated launch, real loopback requests and mocked draft creation only."""

from __future__ import annotations

import contextlib
import http.client
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from doi_draft_transfer.launch import (
    CONFIG_NAME, RECEIPT_NAME, SCHEMA, DraftLaunchError, DraftOnlyRuntime,
    main, private_path, read_config,
)
from doi_draft_transfer.contract import MAILBOX_ID, USER_ID
from doi_draft_transfer.store import FILENAME
from tests.test_doi_draft_transfer import MockClient, csv_text, synthetic_row, verified_review


class LaunchFixture(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="ssa-synthetic-draft-launch-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.config_file = self.root / CONFIG_NAME
        self.config = {
            "schema": SCHEMA, "enabled": True, "data_dir": str(self.root), "port": 0,
            "mailbox_id": MAILBOX_ID, "user_id": USER_ID, "allow_draft_create": False,
        }
        self.write_config()
        self.runtime = None
        self.thread = None
        self.addCleanup(self.stop)

    def write_config(self):
        self.config_file.write_text(json.dumps(self.config), encoding="utf-8")

    def start(self, client=None):
        self.runtime = DraftOnlyRuntime(self.config_file)
        with patch("doi_draft_transfer.launch.HelpScoutDraftClient.from_environment") as factory:
            factory.return_value = client
            receipt = self.runtime.start()
            if self.config["allow_draft_create"]:
                factory.assert_called_once_with()
            else:
                factory.assert_not_called()
        self.thread = threading.Thread(
            target=self.runtime.server.serve_forever, daemon=True
        )
        self.thread.start()
        return receipt

    def stop(self):
        if self.runtime is not None:
            if self.thread is not None and self.thread.is_alive():
                self.runtime.server.shutdown()
                self.thread.join(5)
            self.runtime.close()
            self.runtime = None
        self.thread = None

    def request(self, method, route, payload=None, **overrides):
        server = self.runtime.server
        headers = {
            "Origin": server.origin, "X-SSA-CSRF-Token": server.csrf_token,
            "Content-Type": "application/json",
        }
        headers.update(overrides)
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
        try:
            connection.request(
                method, route, body=json.dumps(payload) if payload is not None else None,
                headers=headers,
            )
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def action(self, action, **kwargs):
        status, raw = self.request(
            "POST", "/api/v1/doi-draft-transfer/action", {"action": action, **kwargs}
        )
        return status, json.loads(raw)


class DraftLaunchTests(LaunchFixture):
    def test_missing_disabled_and_closed_configuration_fail_before_runtime_creation(self):
        original = dict(self.config)
        for field, value in (
            ("enabled", False), ("enabled", 1), ("schema", "SYN-unknown"),
            ("allow_draft_create", "true"), ("mailbox_id", 1), ("user_id", 1),
            ("port", True), ("port", -1), ("port", 65536), ("host", "0.0.0.0"),
            ("doi_owner_confirmations", "SYN-unrelated"), ("access_token", "SYN-prohibited"),
        ):
            with self.subTest(field=field, value=value):
                self.config = {**original, field: value}
                self.write_config()
                with self.assertRaises(DraftLaunchError):
                    DraftOnlyRuntime(self.config_file).start()
                self.assertEqual(list(self.root.iterdir()), [self.config_file])
        self.config_file.unlink()
        with self.assertRaises(DraftLaunchError):
            read_config(self.config_file)

    def test_duplicate_keys_oversize_and_root_mismatch_are_rejected(self):
        good = self.config_file.read_text()
        for raw in (
            good[:-1] + ',"enabled":true}', " " * 8193,
            json.dumps({**self.config, "data_dir": str(self.root.parent)}),
        ):
            self.config_file.write_text(raw, encoding="utf-8")
            with self.assertRaises(DraftLaunchError):
                read_config(self.config_file)

    def test_private_paths_reject_sync_repository_links_and_shared_app_roots(self):
        with self.assertRaises(ValueError):
            private_path(Path(__file__).resolve().parents[1] / "SYN-private")
        with self.assertRaises(DraftLaunchError):
            private_path(self.root / "OneDrive" / "SYN")
        with patch.dict(os.environ, {"OneDrive": str(self.root)}):
            with self.assertRaises(DraftLaunchError):
                read_config(self.config_file)
        marker = self.root / "doi-private-launch.json"
        marker.write_text("SYN normal app marker", encoding="utf-8")
        with self.assertRaisesRegex(DraftLaunchError, "DEDICATED_ROOT"):
            read_config(self.config_file)
        self.assertEqual(marker.read_text(), "SYN normal app marker")
        marker.unlink()
        duplicate = self.root / "SYN-hardlink"
        os.link(self.config_file, duplicate)
        with self.assertRaisesRegex(DraftLaunchError, "LINKED_PATH"):
            read_config(self.config_file)

    def test_review_only_ignores_ambient_transfer_flag_and_never_opens_credentials(self):
        with patch.dict(os.environ, {"SSA_HELPSCOUT_DRAFT_TRANSFER": "1"}):
            with patch("doi_draft_transfer.local_auth._read_encrypted") as read:
                receipt = self.start()
                self.assertIsNone(self.runtime.server.draft_transfer.client)
                self.assertFalse((self.root / "data" / FILENAME).exists())
                self.assertEqual(self.action("check_destination")[0], 503)
                read.assert_not_called()
        self.assertEqual(receipt.database_path, str(self.root / "data" / FILENAME))
        self.assertTrue(receipt.build_version.startswith("draft-only/v1:"))
        self.assertFalse((self.root / "runtime" / "service.json").exists())

    def test_transfer_scope_requires_separate_process_activation(self):
        self.config["allow_draft_create"] = True
        self.write_config()
        with patch.dict(os.environ, {"SSA_HELPSCOUT_DRAFT_TRANSFER": "0"}):
            with self.assertRaisesRegex(DraftLaunchError, "SEPARATE_ACTIVATION"):
                DraftOnlyRuntime(self.config_file).start()
        self.assertFalse((self.root / "data" / FILENAME).exists())
        self.assertFalse((self.root / "runtime" / RECEIPT_NAME).exists())

    def test_second_instance_and_busy_port_do_not_touch_running_service(self):
        receipt = self.start()
        before = (self.root / "runtime" / RECEIPT_NAME).read_bytes()
        with self.assertRaisesRegex(Exception, "INSTANCE_ALREADY_ACTIVE|LEASE_UNAVAILABLE"):
            DraftOnlyRuntime(self.config_file).start()
        self.assertEqual((self.root / "runtime" / RECEIPT_NAME).read_bytes(), before)
        self.assertEqual(self.request("GET", "/doi-draft-transfer")[0], 200)
        self.stop()
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            self.config["port"] = listener.getsockname()[1]
            self.write_config()
            with self.assertRaises(OSError):
                DraftOnlyRuntime(self.config_file).start()
            self.assertEqual(listener.getsockname()[1], self.config["port"])
        self.assertFalse((self.root / "runtime" / RECEIPT_NAME).exists())

    def test_check_command_does_not_start_runtime_or_construct_auth(self):
        with patch("doi_draft_transfer.launch.HelpScoutDraftClient.from_environment") as auth:
            with patch.object(DraftOnlyRuntime, "start") as start:
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["--config", str(self.config_file), "--check"]), 0)
                auth.assert_not_called()
                start.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [self.config_file])


class DraftOnlyHTTPTests(LaunchFixture):
    def test_only_draft_routes_are_available_with_original_host_origin_and_csrf_guards(self):
        self.start()
        status, body = self.request("GET", "/doi-draft-transfer")
        self.assertEqual(status, 200)
        self.assertNotIn(b'href="/doi-csv-review"', body)
        for route in (
            "/doi-csv-review", "/api/v1/doi-csv-review/state", "/campaign-replies",
            "/overview", "/api/v1/orders", "/health", "/static/doi-csv-review.js",
        ):
            self.assertEqual(self.request("GET", route)[0], 404)
        for route in (
            "/api/v1/doi-csv-review/load", "/api/v1/doi-csv-review/reviewed",
            "/api/v1/doi-csv-review/alternate-draft", "/api/v1/dashboard/system/backups",
        ):
            self.assertEqual(self.request("POST", route, {})[0], 404)
        action = {"action": "preview_import", "csv_text": csv_text([synthetic_row()])}
        route = "/api/v1/doi-draft-transfer/action"
        for headers in (
            {"Host": "evil.example.test"}, {"Origin": "https://evil.example.test"},
            {"X-SSA-CSRF-Token": "SYN-wrong"},
        ):
            self.assertIn(self.request("POST", route, action, **headers)[0], {400, 403})
        self.assertEqual(self.action("send")[0], 400)
        self.assertFalse((self.root / "data" / FILENAME).exists())

    def test_csv_review_exact_approval_and_no_repeat_create_survive_mode_restart(self):
        client = MockClient()
        self.config["allow_draft_create"] = True
        self.write_config()
        self.start(client)
        row = synthetic_row()
        status, preview = self.action("preview_import", csv_text=csv_text([row]))
        self.assertEqual(status, 200)
        self.assertEqual(self.action(
            "commit_import", preview_token=preview["preview_token"], revision=preview["revision"]
        )[0], 200)
        _, detail = self.action("detail", order_id=row["order_id"])
        self.assertEqual(self.action(
            "transfer", order_id=row["order_id"], version=1,
            binding=detail["approval_binding"], retry=False,
        )[0], 409)
        review = verified_review()
        review["checks"]["customer_approval"].update(
            decision="pending_conditional_outreach", conditional_copy_reviewed=True,
            evidence="SYN customer decision pending; conditional question only",
        )
        fields = {k: row[k] for k in ("selected_body_text", "recipient_email", "reviewer_notes")}
        self.assertEqual(self.action(
            "edit", order_id=row["order_id"], version=1, fields=fields, review=review
        )[0], 200)
        _, detail = self.action("detail", order_id=row["order_id"])
        approval = {
            "order_id": row["order_id"], "version": detail["version"],
            "binding": detail["approval_binding"],
        }
        self.assertEqual(self.action(
            "approve", **approval, confirmation="I_APPROVE_THIS_EXACT_HELP_SCOUT_DRAFT"
        )[0], 200)
        status, result = self.action("transfer", **approval, retry=False)
        self.assertEqual((status, result["state"]), (200, "CREATED"))
        self.stop()
        self.start(client)
        self.assertEqual(self.action("transfer", **approval, retry=False)[0], 200)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(client.calls[0]["mailboxId"], MAILBOX_ID)
        self.assertEqual(client.calls[0]["user"], USER_ID)
        self.assertIs(client.calls[0]["threads"][0]["draft"], True)
        self.assertIs(client.calls[0]["autoReply"], False)
        self.assertFalse((self.root / "data" / "synthetic_sales_assist.sqlite3").exists())
        self.assertFalse((self.root / "data" / "doi-reviewed-split.json").exists())


@unittest.skipUnless(os.name == "nt", "Windows packaged launch entrypoint")
class DraftPackagedLaunchTests(LaunchFixture):
    def test_packaged_python_check_and_wrapper_syntax_without_daily_policy(self):
        from tests.test_m8_release import COMMIT, STAMP, TREE, candidate_files
        from tools.build_demo_release import build_payloads
        from tools.release_support import extract_archive

        # Keep the dedicated private root separate from the disposable installation.
        temporary = tempfile.TemporaryDirectory(prefix="ssa-synthetic-draft-package-")
        self.addCleanup(temporary.cleanup)
        bundle = Path(temporary.name)
        files = candidate_files()
        artifacts, _ = build_payloads(files, COMMIT, TREE, STAMP)
        archive = bundle / "package.zip"
        archive.write_bytes(next(v for k, v in artifacts.items() if "windows-demo" in k))
        install = bundle / "application"
        extract_archive(archive, install)
        verified = subprocess.run(
            [sys.executable, "-B", "-I", str(install / "tools" / "release_support.py"),
             "verify", "--install-root", str(install)],
            capture_output=True, text=True, timeout=60, check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)
        result = subprocess.run(
            [sys.executable, "-B", "-s", "-E", "-m", "doi_draft_transfer",
             "--config", str(self.config_file), "--check"],
            cwd=install / "src", capture_output=True, text=True, timeout=60, check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('"allow_draft_create": false', result.stdout)
        self.assertEqual(list(self.root.iterdir()), [self.config_file])
        # Parse only: do not override a host execution policy to run the PS1 wrapper.
        shell = shutil.which("powershell") or shutil.which("pwsh")
        environment = {**os.environ, "SSA_SYN_WRAPPER": str(install / "scripts/start-drafts.ps1")}
        syntax = subprocess.run(
            [shell, "-NoProfile", "-Command",
             "$errors = $null; [void][System.Management.Automation.Language.Parser]::ParseFile("
             "$env:SSA_SYN_WRAPPER,[ref]$null,[ref]$errors); if ($errors.Count) { exit 1 }"],
            env=environment, capture_output=True, text=True, timeout=30, check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self.assertEqual(syntax.returncode, 0, syntax.stdout + syntax.stderr)
        self.assertEqual(
            (install / "scripts" / "start.ps1").read_bytes().replace(b"\r\n", b"\n"),
            files["scripts/start.ps1"].replace(b"\r\n", b"\n"),
        )
