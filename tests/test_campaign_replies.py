from __future__ import annotations

import http.client
import os
import threading
import unittest
from html.parser import HTMLParser
from typing import Any, cast
from unittest.mock import patch

from synthetic_sales_assist.portal.dashboard_rendering import render_campaign_replies
from synthetic_sales_assist.portal.server import PortalHTTPServer, PortalServerConfig


CSRF = "a" * 64
SHUTDOWN = "b" * 64
PARENT_ORIGIN = "http://127.0.0.1:8765"
COMPANION_ORIGIN = "http://127.0.0.1:8770"
COMPANION_URL = COMPANION_ORIGIN + "/?embedded=1"


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.frames: list[dict[str, str | None]] = []
        self.active_links: list[dict[str, str | None]] = []
        self.resource_urls: list[str] = []
        self.inline_code: list[str] = []
        self.h1_count = 0

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        values = dict(attrs)
        if tag == "iframe":
            self.frames.append(values)
        if tag == "a" and values.get("aria-current") == "page":
            self.active_links.append(values)
        if tag == "h1":
            self.h1_count += 1
        if tag in {"iframe", "script", "img", "embed", "source"}:
            source = values.get("src")
            if source:
                self.resource_urls.append(source)
        if tag == "link" and values.get("href"):
            self.resource_urls.append(cast(str, values["href"]))
        if tag == "style" or (tag == "script" and not values.get("src")):
            self.inline_code.append(tag)
        for name, _ in attrs:
            if name.casefold().startswith("on") or name.casefold() == "style":
                self.inline_code.append(name)


def _parse(raw: bytes) -> _PageParser:
    parser = _PageParser()
    parser.feed(raw.decode("utf-8"))
    return parser


def _csp(headers: dict[str, str]) -> dict[str, list[str]]:
    return {
        tokens[0]: tokens[1:]
        for part in headers["Content-Security-Policy"].split(";")
        if (tokens := part.strip().split())
    }


class CampaignRepliesRenderingTests(unittest.TestCase):
    def test_default_view_is_disconnected_without_companion_requests(self) -> None:
        page = render_campaign_replies(CSRF)
        parser = _parse(page)
        self.assertEqual(parser.frames, [])
        self.assertTrue(all(url.startswith("/") and not url.startswith("//")
                            for url in parser.resource_urls))
        self.assertEqual(parser.inline_code, [])
        self.assertEqual(parser.h1_count, 1)
        self.assertIn("/campaign-replies", [a.get("href") for a in parser.active_links])

    def test_enabled_view_embeds_only_the_fixed_isolated_companion(self) -> None:
        page = render_campaign_replies(CSRF, enabled=True)
        parser = _parse(page)
        self.assertEqual(len(parser.frames), 1)
        frame = parser.frames[0]
        self.assertEqual(frame.get("src"), COMPANION_URL)
        self.assertTrue(frame.get("title"))
        self.assertEqual(frame.get("referrerpolicy"), "no-referrer")
        self.assertEqual(set(cast(str, frame.get("sandbox", "")).split()), {
            "allow-scripts", "allow-same-origin", "allow-popups",
            "allow-popups-to-escape-sandbox",
        })
        self.assertNotIn("srcdoc", frame)
        self.assertNotIn(CSRF, cast(str, frame.get("src")))
        self.assertEqual([url for url in parser.resource_urls if "://" in url], [COMPANION_URL])
        self.assertEqual(parser.inline_code, [])
        self.assertEqual(parser.h1_count, 1)
        self.assertIn("/campaign-replies", [a.get("href") for a in parser.active_links])
        self.assertNotIn(
            "Synthetic demo · Localhost only · Not connected to live systems",
            page.decode("utf-8"),
        )


class _UnusedBackend:
    """Any attempted application/database operation makes the request fail."""

    database = None

    def __init__(self) -> None:
        self.accesses: list[str] = []

    def __getattr__(self, name: str) -> Any:
        self.accesses.append(name)
        raise AssertionError("Companion rendering must not use a backend service")


class CampaignRepliesServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.environment = patch.dict(os.environ)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        os.environ.pop("SSA_CAMPAIGN_REPLIES", None)
        self.application = _UnusedBackend()
        self.control_center = _UnusedBackend()
        self.server = PortalHTTPServer(
            cast(Any, self.application), PortalServerConfig(port=0),
            csrf_token=CSRF, shutdown_token=SHUTDOWN,
        )
        self.server.control_center = cast(Any, self.control_center)
        self.port = int(self.server.server_address[1])
        self.actual_origin = self.server.origin
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        if self.thread.is_alive():
            self.server.shutdown()
        self.thread.join(timeout=3)
        self.server.server_close()
        self.assertEqual(self.application.accesses, [])
        self.assertEqual(self.control_center.accesses, [])

    def request(
        self, method: str, path: str, *, host: str | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            connection.request(method, path, headers={
                "Host": host if host is not None else f"127.0.0.1:{self.port}",
            })
            response = connection.getresponse()
            raw = response.read()
            return response.status, dict(response.getheaders()), raw
        finally:
            connection.close()

    def enable_canonical_view(self) -> None:
        os.environ["SSA_CAMPAIGN_REPLIES"] = "1"
        # Simulate the public origin after ephemeral binding; never bind or
        # connect to the canonical port or to a running companion service.
        self.server.origin = PARENT_ORIGIN

    def test_disabled_default_does_not_embed_even_on_canonical_origin(self) -> None:
        self.server.origin = PARENT_ORIGIN
        status, headers, raw = self.request("GET", "/campaign-replies")
        self.assertEqual(status, 200)
        self.assertEqual(_parse(raw).frames, [])
        self.assertNotIn(COMPANION_ORIGIN, headers["Content-Security-Policy"])

    def test_opt_in_requires_exact_environment_value_and_canonical_origin(self) -> None:
        for value in ("", "0", "true", "yes", "01", " 1", "1 "):
            with self.subTest(value=value):
                os.environ["SSA_CAMPAIGN_REPLIES"] = value
                self.server.origin = PARENT_ORIGIN
                status, headers, raw = self.request("GET", "/campaign-replies")
                self.assertEqual(status, 200)
                self.assertEqual(_parse(raw).frames, [])
                self.assertNotIn(COMPANION_ORIGIN, headers["Content-Security-Policy"])
        os.environ["SSA_CAMPAIGN_REPLIES"] = "1"
        for origin in (self.actual_origin, "http://localhost:8765", COMPANION_ORIGIN):
            with self.subTest(origin=origin):
                self.server.origin = origin
                status, headers, raw = self.request("GET", "/campaign-replies")
                self.assertEqual(status, 200)
                self.assertEqual(_parse(raw).frames, [])
                self.assertNotIn(COMPANION_ORIGIN, headers["Content-Security-Policy"])
        self.server.origin = PARENT_ORIGIN
        status, _, raw = self.request("GET", "/campaign-replies")
        self.assertEqual(status, 200)
        self.assertEqual(_parse(raw).frames[0].get("src"), COMPANION_URL)

    def test_enabled_response_allows_only_exact_frame_and_retains_other_security(self) -> None:
        self.enable_canonical_view()
        status, headers, raw = self.request("GET", "/campaign-replies")
        self.assertEqual(status, 200)
        self.assertEqual(len(_parse(raw).frames), 1)
        policy = _csp(headers)
        self.assertEqual(policy["frame-src"], [COMPANION_ORIGIN])
        self.assertEqual(policy["default-src"], ["'none'"])
        self.assertEqual(policy["connect-src"], ["'self'"])
        self.assertEqual(policy["frame-ancestors"], ["'none'"])
        self.assertEqual(policy["script-src"], ["'self'"])
        self.assertEqual(policy["object-src"], ["'none'"])
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        self.assertEqual(headers["Referrer-Policy"], "no-referrer")
        self.assertEqual(headers["Cache-Control"], "no-store, max-age=0")
        self.assertEqual(headers["Cross-Origin-Resource-Policy"], "same-origin")
        self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_frame_exception_never_leaks_to_other_routes_or_errors(self) -> None:
        self.enable_canonical_view()
        for path, expected in (("/", 303), ("/static/ssa-dashboard.css", 200),
                               ("/campaign-replies/", 404), ("/campaign-replies?x=1", 400)):
            with self.subTest(path=path):
                status, headers, _ = self.request("GET", path)
                self.assertEqual(status, expected)
                self.assertNotIn(COMPANION_ORIGIN, headers["Content-Security-Policy"])
                self.assertEqual(_csp(headers)["frame-ancestors"], ["'none'"])

    def test_fixed_html_route_is_get_only_without_json_or_proxy_surface(self) -> None:
        self.enable_canonical_view()
        for method in ("POST", "HEAD", "OPTIONS", "PUT", "PATCH", "DELETE"):
            with self.subTest(method=method):
                status, headers, _ = self.request(method, "/campaign-replies")
                self.assertEqual(status, 405)
                self.assertEqual(headers["Allow"], "GET")
                self.assertNotIn(COMPANION_ORIGIN, headers["Content-Security-Policy"])
        for path in ("/api/v1/dashboard/campaign-replies", "/campaign-replies/data"):
            with self.subTest(path=path):
                status, _, _ = self.request("GET", path)
                self.assertEqual(status, 404)

    def test_query_encoded_target_and_nonexact_host_are_rejected_before_dispatch(self) -> None:
        self.enable_canonical_view()
        for path in ("/campaign-replies?presentation=1", "/campaign-replies?enabled=1",
                     "/campaign-replies?url=http://127.0.0.1:9999/", "/campaign%2dreplies"):
            with self.subTest(path=path):
                status, headers, raw = self.request("GET", path)
                self.assertEqual(status, 400)
                self.assertEqual(_parse(raw).frames, [])
                self.assertNotIn(COMPANION_ORIGIN, headers["Content-Security-Policy"])
        status, _, _ = self.request("GET", "/campaign-replies", host=f"localhost:{self.port}")
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
