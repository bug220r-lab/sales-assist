"""Integrated loopback, campaign-to-reply and restart acceptance checks."""

from __future__ import annotations

import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from synthetic_sales_assist.application import ScenarioApplication
from synthetic_sales_assist.campaign_replies.application import WorkspaceApplication
from synthetic_sales_assist.campaign_replies.web import WorkspaceError, WorkspaceWeb
from synthetic_sales_assist.portal.server import PortalHTTPServer, PortalServerConfig
from synthetic_sales_assist.safety.repository import scan_secret_material


class WorkspaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="ssa-workspace-tests-")
        self.path = Path(self.temporary.name) / "campaign_replies.sqlite3"
        self.app = WorkspaceApplication(self.path)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_campaign_to_reply_review_survives_new_application(self) -> None:
        seeded = self.app.post({"action": "demo"})
        campaign_id = seeded["campaign_id"]
        self.app.post({"action": "launch", "campaign_id": campaign_id})
        sent = self.app.post({"action": "step", "campaign_id": campaign_id})
        self.assertEqual(sent["counts"]["accepted"], 1)
        self.app.post({"action": "demo-reply", "campaign_id": campaign_id})
        record = next(r for r in sent["records"] if r["receipt"])
        detail = self.app.get({"view": "conversation", "id": record["conversation_id"]})
        self.assertEqual(detail["anchor_thread_id"], record["anchor_thread_id"])
        self.assertTrue(detail["needs_reply"])
        request = {
            "action": "save-draft", "conversation_id": record["conversation_id"],
            "text": "Synthetic review: I can help with the checkout question.",
            "expected_revision": 0, "source_fingerprint": detail["source_fingerprint"],
            "style_version": detail["style_profile"]["version"], "reviewed": True,
        }
        saved = self.app.post(request)
        self.assertEqual(saved["revision"], 1)
        restarted = WorkspaceApplication(self.path)
        recovered = restarted.get({"view": "conversation", "id": record["conversation_id"]})
        self.assertEqual(recovered["local_draft"]["text"], request["text"])
        self.assertTrue(recovered["local_draft"]["reviewed"])
        job = restarted.post({"action": "synthetic-job",
                              "conversation_id": record["conversation_id"]})
        self.assertIs(job["draft"], True)
        self.assertIs(job["production_writer_compatible"], False)
        self.assertFalse(job["remote_write_allowed"])
        with self.assertRaises(ValueError):
            restarted.post(request)
        restarted.post({"action": "demo"})
        self.assertEqual(restarted.replies.detail(record["conversation_id"])[
            "local_draft"]["text"], request["text"])

    def test_closed_actions_and_duplicate_json_keys(self) -> None:
        web = WorkspaceWeb(self.path)
        for raw in (b'{"action":"demo","action":"launch"}',
                    b'{"action":"demo","extra":true}', b'{"action":"send-live"}'):
            with self.assertRaises(WorkspaceError):
                web.post(raw)
        with self.assertRaises(WorkspaceError):
            self.app.get({"view": "queue", "needs_reply": "maybe"})
        with self.assertRaises(WorkspaceError):
            self.app.get({"view": "queue", "offset": "-1"})

    def test_secret_scanner_distinguishes_conversion_from_literal(self) -> None:
        code = Path(self.temporary.name) / "conversion.ps1"
        code.write_text("$script:Connection.Token = "
                        "ConvertTo-SecureString -String $value -AsPlainText -Force\n")
        self.assertEqual(scan_secret_material(code.parent), ())
        code.write_text("$script:Connection.Token = '" + "ConvertTo-SecureString'\n")
        self.assertTrue(scan_secret_material(code.parent))
        code.write_text("$script:Connection.Token = " + "ConvertTo-SecureString -String '"
                        + "synthetic-canary-123456789" + "' -AsPlainText -Force\n")
        self.assertTrue(scan_secret_material(code.parent))


class WorkspaceHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="ssa-workspace-http-")
        self.app = ScenarioApplication.open(Path(self.temporary.name))
        self.server = PortalHTTPServer(
            self.app, PortalServerConfig("127.0.0.1", 0),
            csrf_token="a" * 64, shutdown_token="b" * 64,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()
        self.temporary.cleanup()

    def request(self, method: str, path: str, payload: object = None,
                authenticated: bool = True) -> tuple[int, dict, bytes]:
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=10)
        headers = {"Content-Type": "application/json"}
        if authenticated:
            headers.update({"Origin": self.server.origin, "X-SSA-CSRF-Token": "a" * 64})
        connection.request(method, path, json.dumps(payload) if payload else None, headers)
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    def test_local_pages_and_api_keep_existing_request_guards(self) -> None:
        for path in ("/campaigns", "/replies", "/writing-history"):
            status, headers, body = self.request("GET", path)
            self.assertEqual(status, 200)
            self.assertIn(b"No live connection", body)
            self.assertIn("script-src 'self'", headers["Content-Security-Policy"])
        endpoint = "/api/v1/campaign-workspace/actions"
        self.assertEqual(self.request("POST", endpoint, {"action": "demo"}, False)[0], 403)
        self.assertEqual(self.request("POST", endpoint, {"action": "demo"})[0], 200)
        status, _, body = self.request("GET", "/api/v1/campaign-workspace?view=queue")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["data"]["total"], 8)
        self.assertEqual(self.request("POST", endpoint, {"action": "send-live"})[0], 400)
        self.assertEqual(self.request("GET", "/api/v1/campaign-workspace?view=queue&bad=1")[0], 400)
        duplicate = "/api/v1/campaign-workspace?view=queue&view=history"
        self.assertEqual(self.request("GET", duplicate)[0], 400)
        self.assertEqual(self.request("GET", "/api/v1/campaign-workspace/actions")[0], 405)


if __name__ == "__main__":
    unittest.main()
