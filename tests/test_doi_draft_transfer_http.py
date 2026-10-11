"""Actual loopback transport with mocked Help Scout; no live service access."""

import http.client
import json
import os
import tempfile
import threading
import unittest
import uuid
from pathlib import Path

from doi_draft_transfer.store import DraftTransferStore, FILENAME
from synthetic_sales_assist.portal.server import PortalHTTPServer, PortalServerConfig
from tests.test_doi_draft_transfer import MockClient, csv_text, large_synthetic_csv, synthetic_row


class TransferHTTPTests(unittest.TestCase):
    def setUp(self):
        root = Path(os.environ.get("SSA_TRANSFER_TEST_ROOT", tempfile.gettempdir()))
        self.folder = root / ("ssa-synthetic-http-" + uuid.uuid4().hex)
        self.folder.mkdir(parents=True)
        self.client = MockClient()
        self.server = PortalHTTPServer(
            None,
            PortalServerConfig("127.0.0.1", 0),
            csrf_token="a" * 64,
            shutdown_token="b" * 64,
            doi_csv_review_only=True,
            draft_transfer_store=DraftTransferStore(self.folder / FILENAME),
            draft_transfer_client=self.client,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)
        for path in self.folder.iterdir():
            self.assertIn(
                path.name, {FILENAME, FILENAME + "-journal", FILENAME + "-wal", FILENAME + "-shm"}
            )
            path.unlink()
        self.folder.rmdir()

    def request(self, method, path, value=None, headers=None, raw=None):
        con = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=30)
        auth = {
            "Origin": self.server.origin,
            "X-SSA-CSRF-Token": "a" * 64,
            "Content-Type": "application/json",
        }
        auth.update(headers or {})
        try:
            con.request(
                method,
                path,
                body=raw
                if raw is not None
                else (json.dumps(value).encode() if value is not None else None),
                headers=auth,
            )
            response = con.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            con.close()

    def test_page_assets_template_and_no_store_created_on_get(self):
        status, headers, body = self.request("GET", "/doi-draft-transfer")
        self.assertEqual(status, 200)
        self.assertIn(b'id="transfer-exact-approval"', body)
        self.assertIn("connect-src 'self'", headers["Content-Security-Policy"])
        self.assertEqual(body.count(b'src="/static/doi-draft-transfer.js"'), 1)
        for path in (
            "/static/doi-draft-transfer.js",
            "/static/doi-draft-transfer.css",
            "/api/v1/doi-draft-transfer/template",
            "/api/v1/doi-draft-transfer/state",
        ):
            self.assertEqual(self.request("GET", path)[0], 200)
        self.assertFalse((self.folder / FILENAME).exists())
        self.assertEqual(self.client.calls, [])

    def test_origin_host_csrf_and_wrong_method_rejected_without_import(self):
        action = {"action": "preview_import", "csv_text": csv_text([synthetic_row()])}
        for headers in (
            {"Origin": "https://evil.example.test"},
            {"X-SSA-CSRF-Token": "incorrect"},
            {"Host": "evil.example.test"},
        ):
            self.assertIn(
                self.request("POST", "/api/v1/doi-draft-transfer/action", action, headers)[0],
                {400, 403},
            )
        self.assertEqual(self.request("GET", "/api/v1/doi-draft-transfer/action")[0], 405)
        self.assertFalse((self.folder / FILENAME).exists())

    def test_duplicate_json_keys_mailbox_override_and_approval_bypass_rejected(self):
        route = "/api/v1/doi-draft-transfer/action"
        self.assertEqual(
            self.request("POST", route, raw=b'{"action":"detail","action":"transfer"}')[0], 400
        )
        self.assertEqual(
            self.request(
                "POST",
                route,
                {
                    "action": "transfer",
                    "order_id": "90000001",
                    "version": 1,
                    "binding": "0" * 64,
                    "retry": False,
                    "mailbox_id": 1,
                },
            )[0],
            400,
        )
        self.assertEqual(self.request("POST", route, {"action": "send"})[0], 400)
        self.assertEqual(self.client.calls, [])

    def test_preview_commit_and_unapproved_transfer_rejected(self):
        route = "/api/v1/doi-draft-transfer/action"
        row = synthetic_row()
        row["source_provenance_json"] = json.dumps(
            {"synthetic": "SYN\u03a9\n" * 60000}, ensure_ascii=False, indent=2
        )
        response = self.request(
            "POST", route, {"action": "preview_import", "csv_text": csv_text([row])}
        )
        self.assertEqual(response[0], 200)
        preview = json.loads(response[2])
        self.assertFalse((self.folder / FILENAME).exists())
        self.assertEqual(
            self.request(
                "POST",
                route,
                {
                    "action": "commit_import",
                    "preview_token": preview["preview_token"],
                    "revision": preview["revision"],
                },
            )[0],
            200,
        )
        detail = json.loads(
            self.request("POST", route, {"action": "detail", "order_id": "90000001"})[2]
        )
        self.assertFalse(detail["approved"])
        self.assertEqual(detail["row"], row)
        self.assertEqual(
            self.request(
                "POST",
                route,
                {
                    "action": "transfer",
                    "order_id": "90000001",
                    "version": 1,
                    "binding": detail["approval_binding"],
                    "retry": False,
                },
            )[0],
            409,
        )
        self.assertEqual(self.client.calls, [])

    def test_492_row_15mb_upload_preview_persistence_and_bounded_responses(self):
        rows, value = large_synthetic_csv()
        self.assertEqual(len(rows), 492)
        self.assertEqual(len(rows[0]), 34)
        self.assertEqual(sum(bool(row["selected_body_text"]) for row in rows), 150)
        self.assertEqual(sum(not row["selected_body_text"] for row in rows), 342)
        route = "/api/v1/doi-draft-transfer/action"
        status, _, body = self.request(
            "POST", route, {"action": "preview_import", "csv_text": value}
        )
        self.assertEqual(status, 200)
        self.assertLess(len(body), 1024 * 1024)
        self.assertNotIn(b"source_provenance_json", body)
        preview = json.loads(body)
        self.assertEqual(preview["errors"], [])
        self.assertEqual(len(preview["rows"]), 492)
        self.assertFalse((self.folder / FILENAME).exists())
        status, _, body = self.request(
            "POST",
            route,
            {
                "action": "commit_import",
                "preview_token": preview["preview_token"],
                "revision": preview["revision"],
            },
        )
        self.assertEqual(status, 200)
        self.assertLess(len(body), 128 * 1024)
        self.assertEqual(len(json.loads(body)["results"]), 492)
        restarted = DraftTransferStore(self.folder / FILENAME)
        with restarted.transaction() as con:
            self.assertEqual(con.execute("SELECT count(*) FROM drafts").fetchone()[0], 492)
            for row in rows:
                record = restarted.load(con, row["order_id"])
                self.assertEqual(record["row"], row)
                self.assertIsNone(record["approval"])
                self.assertFalse(record["review"]["recipient_verified"])
        self.assertLess((self.folder / FILENAME).stat().st_size, 256 * 1024 * 1024)
        status, _, body = self.request("GET", "/api/v1/doi-draft-transfer/state")
        self.assertEqual(status, 200)
        self.assertLess(len(body), 1024 * 1024)
        self.assertNotIn(b"source_provenance_json", body)
        state = json.loads(body)
        self.assertEqual(len(state["rows"]), 492)
        self.assertEqual(sum(row["has_selected_copy"] for row in state["rows"]), 150)
        for index in (0, 149, 150, 491):
            status, _, body = self.request(
                "POST", route, {"action": "detail", "order_id": rows[index]["order_id"]}
            )
            self.assertEqual(status, 200)
            self.assertLess(len(body), 1024 * 1024)
            self.assertEqual(json.loads(body)["row"], rows[index])
        self.assertEqual(self.client.calls, [])


if __name__ == "__main__":
    unittest.main()
