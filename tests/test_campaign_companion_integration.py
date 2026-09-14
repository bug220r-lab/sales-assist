"""Combined companion and synthetic workspace boundaries on disposable loopback servers."""

from __future__ import annotations

import http.client
import json
import os
import tempfile
import threading
import unittest
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch

from synthetic_sales_assist.application import ScenarioApplication
from synthetic_sales_assist.portal.server import (
    PortalHTTPServer,
    PortalRequestHandler,
    PortalServerConfig,
)


PARENT_ORIGIN = "http://127.0.0.1:8765"
COMPANION_ORIGIN = "http://127.0.0.1:8770"
COMPANION_URL = COMPANION_ORIGIN + "/?embedded=1"
WORKSPACE_PAGES = ("/campaigns", "/replies", "/writing-history")
WORKSPACE_QUEUE = "/api/v1/campaign-workspace?view=queue"
PRIMARY_DESTINATIONS = (
    "/overview", "/sales-credit", "/doi", "/review", "/campaigns",
    "/replies", "/writing-history", "/campaign-replies", "/system",
)


class _Page(HTMLParser):
    def __init__(self, body: bytes) -> None:
        super().__init__(convert_charrefs=True)
        self.primary_count = 0
        self.primary_links: list[str | None] = []
        self.frames: list[dict[str, str | None]] = []
        self._in_primary = False
        self.feed(body.decode("utf-8"))

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]],
    ) -> None:
        values = dict(attrs)
        if tag == "nav" and values.get("aria-label") == "Primary":
            self.primary_count += 1
            self._in_primary = True
        elif tag == "a" and self._in_primary:
            self.primary_links.append(values.get("href"))
        if tag == "iframe":
            self.frames.append(values)

    def handle_endtag(self, tag: str) -> None:
        if tag == "nav":
            self._in_primary = False


class CampaignCompanionIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        environment = patch.dict(os.environ)
        environment.start()
        self.addCleanup(environment.stop)
        os.environ.pop("SSA_CAMPAIGN_REPLIES", None)
        temporary = tempfile.TemporaryDirectory(prefix="ssa-companion-integration-")
        self.addCleanup(temporary.cleanup)
        self.application = ScenarioApplication.open(Path(temporary.name))
        self.workspace_path = self.application.database.path.with_name(
            "campaign_replies.sqlite3"
        )
        self.server = PortalHTTPServer(
            self.application, PortalServerConfig("127.0.0.1", 0),
            csrf_token="a" * 64, shutdown_token="b" * 64,
        )
        self.actual_origin = self.server.origin
        self.port = int(self.server.server_address[1])
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self._stop_server)
        self.assertNotIn(self.port, (8765, 8770))

    def _stop_server(self) -> None:
        if self.thread.is_alive():
            self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()
        self.assertFalse(self.thread.is_alive())

    def get(self, path: str) -> tuple[int, dict[str, str], bytes]:
        # These tests fetch only their own ephemeral server. HTML is parsed as
        # text, so the fixed companion iframe never causes a child request.
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            connection.request("GET", path)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def assert_no_frame_permission(self, headers: dict[str, str]) -> None:
        policy = headers["Content-Security-Policy"]
        self.assertNotIn("frame-src", policy)
        self.assertNotIn(COMPANION_ORIGIN, policy)
        self.assertIn("default-src 'none'", policy)
        self.assertIn("frame-ancestors 'none'", policy)
        self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_companion_get_does_not_initialize_synthetic_workspace(self) -> None:
        self.server.origin = PARENT_ORIGIN
        self.assertIsNone(self.server.campaign_workspace)
        self.assertFalse(self.workspace_path.exists())
        with patch.object(
            PortalRequestHandler, "_workspace",
            side_effect=AssertionError("Companion requested synthetic storage"),
        ) as workspace:
            for enabled in (False, True):
                with self.subTest(enabled=enabled):
                    if enabled:
                        os.environ["SSA_CAMPAIGN_REPLIES"] = "1"
                    status, headers, body = self.get("/campaign-replies")
                    self.assertEqual(status, 200)
                    self.assertEqual(len(_Page(body).frames), int(enabled))
                    if not enabled:
                        self.assert_no_frame_permission(headers)
                    workspace.assert_not_called()
                    self.assertIsNone(self.server.campaign_workspace)
                    self.assertFalse(self.workspace_path.exists())
                    self.assertFalse(self.workspace_path.with_name(
                        self.workspace_path.name + "-wal"
                    ).exists())
        # Positive control: the same server can lazily initialize its own
        # synthetic feature store when a workspace route actually needs it.
        self.server.origin = self.actual_origin
        status, headers, body = self.get(WORKSPACE_QUEUE)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["data"]["total"], 0)
        self.assertIsNotNone(self.server.campaign_workspace)
        self.assertTrue(self.workspace_path.is_file())
        self.assert_no_frame_permission(headers)

    def test_both_page_renderers_keep_complete_distinct_navigation(self) -> None:
        for path in ("/overview", "/campaign-replies", *WORKSPACE_PAGES):
            with self.subTest(path=path):
                status, headers, body = self.get(path)
                self.assertEqual(status, 200)
                page = _Page(body)
                self.assertEqual(page.primary_count, 1)
                self.assertEqual(Counter(page.primary_links), Counter(PRIMARY_DESTINATIONS))
                self.assertEqual(page.frames, [])
                self.assert_no_frame_permission(headers)
                if path == "/campaign-replies":
                    self.assertIn(b"Local companion", body)
                    self.assertIn(b"Read-only review", body)
                    self.assertNotIn(b"Synthetic demo", body)
                else:
                    self.assertIn(b"Synthetic demo", body)
                if path in WORKSPACE_PAGES:
                    self.assertIn(b"No live connection", body)

    def test_alternate_port_keeps_workspace_usable_and_companion_disconnected(self) -> None:
        os.environ["SSA_CAMPAIGN_REPLIES"] = "1"
        self.assertEqual(self.server.origin, self.actual_origin)
        self.assertNotEqual(self.actual_origin, PARENT_ORIGIN)
        status, headers, body = self.get("/campaign-replies")
        self.assertEqual(status, 200)
        self.assertEqual(_Page(body).frames, [])
        self.assert_no_frame_permission(headers)
        # Only change the declared origin for the enabled half of this test;
        # the listener and every test request remain on the ephemeral port.
        for origin in (self.actual_origin, PARENT_ORIGIN):
            self.server.origin = origin
            for path in (*WORKSPACE_PAGES, WORKSPACE_QUEUE):
                with self.subTest(origin=origin, path=path):
                    status, headers, body = self.get(path)
                    self.assertEqual(status, 200)
                    self.assert_no_frame_permission(headers)
                    if path == WORKSPACE_QUEUE:
                        data = json.loads(body)
                        self.assertEqual(data["schema_version"], "synthetic-campaign-workspace/v1")
                        self.assertEqual(data["data"]["total"], 0)
                    else:
                        self.assertEqual(_Page(body).frames, [])
                        self.assertIn(b"No live connection", body)
        status, headers, body = self.get("/campaign-replies")
        self.assertEqual(status, 200)
        self.assertEqual([frame.get("src") for frame in _Page(body).frames], [COMPANION_URL])
        self.assertIn("frame-src " + COMPANION_ORIGIN, headers["Content-Security-Policy"])
        self.assertNotIn("Access-Control-Allow-Origin", headers)


if __name__ == "__main__":
    unittest.main()
