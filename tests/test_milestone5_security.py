from __future__ import annotations

import http.client
import json
import os
import socket
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from synthetic_sales_assist.application import ScenarioApplication
from synthetic_sales_assist.persistence.paths import (
    DataPaths,
    PathPolicyError,
    resolve_data_paths,
)
from synthetic_sales_assist.portal.contracts import (
    API_REQUEST_SCHEMA_VERSION,
    MAX_REQUEST_BODY_BYTES,
    MAX_RESPONSE_BODY_BYTES,
    PortalContractError,
)
from synthetic_sales_assist.portal.lifecycle import (
    RUNTIME_RECEIPT_MEMBERS,
    PortalLifecycleError,
    RuntimeReceipt,
)
from synthetic_sales_assist.portal.rendering import order_source_payload
from synthetic_sales_assist.portal.server import (
    PortalHTTPServer,
    PortalRuntime,
    PortalServerConfig,
    PortalServerError,
    open_runtime,
)
from synthetic_sales_assist.safety.identity import is_reserved_identity
from tests.test_milestone5_portal import (
    CSRF,
    INTERACTION_ID,
    ORDER_ID,
    RUN_ID,
    SHUTDOWN,
    FakeApplication,
    _order,
    _status,
)


class PortalSecurityHTTPTests(unittest.TestCase):
    def setUp(self) -> None:
        self.application = FakeApplication()
        self.server = PortalHTTPServer(
            self.application,
            PortalServerConfig(port=0),
            csrf_token=CSRF,
            shutdown_token=SHUTDOWN,
        )
        self.port = int(self.server.server_address[1])
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        if self.thread.is_alive():
            self.server.shutdown()
        self.thread.join(timeout=3)
        self.server.server_close()

    def request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        supplied = {} if headers is None else dict(headers)
        supplied.setdefault("Host", f"127.0.0.1:{self.port}")
        connection.request(method, path, body=body, headers=supplied)
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    def raw_exchange(self, request: bytes) -> bytes:
        with socket.create_connection(("127.0.0.1", self.port), timeout=5) as client:
            client.settimeout(5)
            client.sendall(request)
            with self.subTest(request=request[:32]):
                try:
                    client.shutdown(socket.SHUT_WR)
                except OSError:
                    pass
            parts: list[bytes] = []
            while True:
                try:
                    part = client.recv(65_536)
                except ConnectionResetError:
                    break
                if not part:
                    break
                parts.append(part)
            return b"".join(parts)

    def post_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Origin": "http" + f"://127.0.0.1:{self.port}",
            "X-SSA-CSRF-Token": CSRF,
        }

    @staticmethod
    def evaluate_body() -> bytes:
        return json.dumps(
            {"request_key": None, "schema_version": API_REQUEST_SCHEMA_VERSION},
            separators=(",", ":"),
        ).encode("utf-8")

    def test_loopback_host_allowlist_is_exact(self) -> None:
        for host in ("127.0.0.1", "localhost", "::1"):
            with self.subTest(host=host):
                self.assertEqual(PortalServerConfig(host=host).host, host)
        for host in ("0.0.0.0", "192.0.2.10", "example.invalid", ""):
            with self.subTest(host=host):
                with self.assertRaises(PortalServerError):
                    PortalServerConfig(host=host)

    def test_host_origin_and_csrf_are_exact(self) -> None:
        status, headers, raw = self.request(
            "GET", "/api/v1/orders", headers={"Host": "localhost:8765"}
        )
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(raw)["error"]["code"], "HOST_HEADER_INVALID")
        self.assertEqual(headers["Connection"], "close")
        self.assertNotIn(SHUTDOWN.encode("ascii"), raw)
        self.assertNotIn(CSRF.encode("ascii"), raw)

        headers = self.post_headers()
        headers["Origin"] = "null"
        status, _, raw = self.request(
            "POST",
            f"/api/v1/orders/{ORDER_ID}/evaluate",
            body=self.evaluate_body(),
            headers=headers,
        )
        self.assertEqual(status, 403)
        self.assertEqual(json.loads(raw)["error"]["code"], "ORIGIN_INVALID")

        headers = self.post_headers()
        headers["X-SSA-CSRF-Token"] = SHUTDOWN
        status, _, raw = self.request(
            "POST",
            f"/api/v1/orders/{ORDER_ID}/evaluate",
            body=self.evaluate_body(),
            headers=headers,
        )
        self.assertEqual(status, 403)
        self.assertEqual(json.loads(raw)["error"]["code"], "CSRF_TOKEN_INVALID")
        self.assertEqual(self.application.evaluate_calls, [])

    def test_duplicate_security_and_entity_headers_are_rejected(self) -> None:
        body = self.evaluate_body()
        authority = f"127.0.0.1:{self.port}"
        origin = "http" + f"://{authority}"
        requests = (
            (
                b"Host: " + authority.encode() + b"\r\nHost: " + authority.encode(),
                b"HOST_HEADER_INVALID",
            ),
            (
                b"Origin: " + origin.encode() + b"\r\nOrigin: " + origin.encode(),
                b"ORIGIN_INVALID",
            ),
            (
                b"X-SSA-CSRF-Token: "
                + CSRF.encode()
                + b"\r\nX-SSA-CSRF-Token: "
                + CSRF.encode(),
                b"CSRF_TOKEN_INVALID",
            ),
            (
                b"Content-Length: "
                + str(len(body)).encode()
                + b"\r\nContent-Length: "
                + str(len(body)).encode(),
                b"CONTENT_LENGTH_INVALID",
            ),
            (
                b"Content-Type: application/json\r\nContent-Type: application/json",
                b"CONTENT_TYPE_INVALID",
            ),
        )
        for duplicated, error_code in requests:
            with self.subTest(header=duplicated.split(b":", 1)[0]):
                baseline = (
                    f"POST /api/v1/orders/{ORDER_ID}/evaluate HTTP/1.1\r\n"
                    f"Host: {authority}\r\nOrigin: {origin}\r\n"
                    f"X-SSA-CSRF-Token: {CSRF}\r\n"
                    f"Content-Type: application/json\r\nContent-Length: {len(body)}\r\n"
                ).encode()
                name = duplicated.split(b":", 1)[0].lower()
                filtered = b"\r\n".join(
                    line
                    for line in baseline.split(b"\r\n")
                    if not line.lower().startswith(name + b":")
                )
                response = self.raw_exchange(filtered + duplicated + b"\r\n\r\n" + body)
                self.assertIn(error_code, response)
                self.assertEqual(response.count(b"HTTP/1.1 "), 1)
        self.assertEqual(self.application.evaluate_calls, [])

    def test_duplicate_shutdown_token_is_rejected_without_shutdown(self) -> None:
        body = json.dumps(
            {"schema_version": API_REQUEST_SCHEMA_VERSION}, separators=(",", ":")
        ).encode()
        authority = f"127.0.0.1:{self.port}"
        origin = "http" + f"://{authority}"
        request = (
            f"POST /api/v1/system/shutdown HTTP/1.1\r\n"
            f"Host: {authority}\r\nOrigin: {origin}\r\n"
            f"X-SSA-CSRF-Token: {CSRF}\r\n"
            f"X-SSA-Shutdown-Token: {SHUTDOWN}\r\n"
            f"X-SSA-Shutdown-Token: {SHUTDOWN}\r\n"
            f"Content-Type: application/json\r\nContent-Length: {len(body)}\r\n\r\n"
        ).encode() + body
        response = self.raw_exchange(request)
        self.assertIn(b"SHUTDOWN_TOKEN_INVALID", response)
        self.assertFalse(self.server.shutdown_requested.is_set())

    def test_unread_rejected_body_cannot_dispatch_a_pipelined_request(self) -> None:
        authority = f"127.0.0.1:{self.port}"
        first = (
            f"POST /api/v1/orders/{ORDER_ID}/evaluate HTTP/1.1\r\n"
            f"Host: {authority}\r\nOrigin: null\r\n"
            f"X-SSA-CSRF-Token: {CSRF}\r\nContent-Type: application/json\r\n"
            "Content-Length: 2\r\n\r\n{}"
        ).encode()
        second = (
            f"GET /api/v1/orders HTTP/1.1\r\nHost: {authority}\r\n\r\n"
        ).encode()
        response = self.raw_exchange(first + second)
        self.assertIn(b"ORIGIN_INVALID", response)
        self.assertEqual(response.count(b"HTTP/1.1 "), 1)
        self.assertEqual(self.application.evaluate_calls, [])

    def test_closed_json_and_request_body_bound(self) -> None:
        invalid_bodies = (
            b'{"request_key":null,"request_key":null,'
            b'"schema_version":"synthetic-sales-assist-api-request/v1"}',
            b'{"extra":0,"request_key":null,'
            b'"schema_version":"synthetic-sales-assist-api-request/v1"}',
            b'{"request_key":1.5,"schema_version":"synthetic-sales-assist-api-request/v1"}',
        )
        for body in invalid_bodies:
            with self.subTest(body=body):
                status, _, raw = self.request(
                    "POST",
                    f"/api/v1/orders/{ORDER_ID}/evaluate",
                    body=body,
                    headers=self.post_headers(),
                )
                self.assertEqual(status, 400)
                self.assertIn("error", json.loads(raw))
        oversized = b"{" + b" " * MAX_REQUEST_BODY_BYTES
        status, _, raw = self.request(
            "POST",
            f"/api/v1/orders/{ORDER_ID}/evaluate",
            body=oversized,
            headers=self.post_headers(),
        )
        self.assertEqual(status, 413)
        self.assertEqual(json.loads(raw)["error"]["code"], "REQUEST_BODY_TOO_LARGE")

    def test_evaluation_rechecks_fast_health_immediately_before_dispatch(self) -> None:
        self.application.healthy = False
        status, _, raw = self.request(
            "POST",
            f"/api/v1/orders/{ORDER_ID}/evaluate",
            body=self.evaluate_body(),
            headers=self.post_headers(),
        )
        self.assertEqual(status, 503)
        self.assertEqual(
            json.loads(raw)["error"]["code"], "PORTAL_EVALUATION_HEALTH_FAILED"
        )
        self.assertEqual(self.application.evaluate_calls, [])

    def test_unsupported_methods_and_parse_errors_use_safe_responses(self) -> None:
        for method in ("TRACE", "CONNECT", "BREW"):
            with self.subTest(method=method):
                status, headers, raw = self.request(method, "/api/v1/orders")
                self.assertEqual(status, 405)
                self.assertEqual(json.loads(raw)["error"]["code"], "METHOD_NOT_ALLOWED")
                self.assertIn("default-src 'none'", headers["Content-Security-Policy"])
                self.assertEqual(headers["Connection"], "close")
                self.assertNotIn(b"Unsupported method", raw)
        long_target = b"/" + b"a" * 65_536
        response = self.raw_exchange(
            b"GET " + long_target + b" HTTP/1.1\r\nHost: ignored\r\n\r\n"
        )
        self.assertIn(b" 414 ", response)
        self.assertIn(b"Content-Security-Policy", response)
        self.assertNotIn(b"Error response", response)

    def test_known_routes_return_endpoint_specific_method_not_allowed(self) -> None:
        get_on_post = (
            "/api/v1/scenarios/doi-overlap/instantiate",
            f"/api/v1/orders/{ORDER_ID}/evaluate",
            "/api/v1/system/shutdown",
        )
        for path in get_on_post:
            with self.subTest(path=path, method="GET"):
                status, headers, raw = self.request("GET", path)
                self.assertEqual(status, 405)
                self.assertEqual(headers["Allow"], "POST")
                self.assertEqual(
                    json.loads(raw)["error"]["code"],
                    "METHOD_NOT_ALLOWED",
                )
        post_on_get = (
            "/health",
            "/api/v1/scenarios",
            "/api/v1/orders",
            f"/api/v1/orders/{ORDER_ID}",
            f"/api/v1/orders/{ORDER_ID}/history",
            f"/api/v1/interactions/{INTERACTION_ID}",
            f"/api/v1/runs/{RUN_ID}",
            "/api/v1/metrics/summary",
            "/api/v1/system/status",
        )
        for path in post_on_get:
            with self.subTest(path=path, method="POST"):
                status, headers, raw = self.request(
                    "POST",
                    path,
                    body=b"",
                )
                self.assertEqual(status, 405)
                self.assertEqual(headers["Allow"], "GET")
                self.assertEqual(
                    json.loads(raw)["error"]["code"],
                    "METHOD_NOT_ALLOWED",
                )
        for method in ("GET", "POST"):
            with self.subTest(method=method, path="unknown"):
                status, _, raw = self.request(
                    method,
                    "/api/v1/not-a-route",
                    body=b"" if method == "POST" else None,
                )
                self.assertEqual(status, 404)
                self.assertEqual(json.loads(raw)["error"]["code"], "ROUTE_NOT_FOUND")
        self.assertEqual(self.application.instantiate_calls, [])
        self.assertEqual(self.application.evaluate_calls, [])

    def test_absolute_form_and_traversal_targets_fail_closed(self) -> None:
        authority = f"127.0.0.1:{self.port}"
        targets = (
            "http" + f"://{authority}/health",
            "/../health",
            "/api/v1/orders%2fignored",
            "//localhost/health",
        )
        for target in targets:
            with self.subTest(target=target):
                response = self.raw_exchange(
                    f"GET {target} HTTP/1.1\r\nHost: {authority}\r\n\r\n".encode()
                )
                self.assertIn(b" 400 ", response)
                self.assertIn(b"Connection: close", response)

    def test_response_and_embedded_payload_bounds_fail_safely(self) -> None:
        self.application.description = "S" * 4_097
        status, headers, raw = self.request("GET", "/api/v1/scenarios")
        self.assertEqual(status, 500)
        self.assertLessEqual(len(raw), MAX_RESPONSE_BODY_BYTES)
        self.assertEqual(headers["Connection"], "close")
        with patch(
            "synthetic_sales_assist.portal.rendering.MAX_RESPONSE_BODY_BYTES", 100
        ):
            with self.assertRaisesRegex(PortalContractError, "ORDER_PAYLOAD_TOO_LARGE"):
                order_source_payload(_order())

    def test_valid_owned_shutdown_requires_both_independent_tokens(self) -> None:
        body = json.dumps(
            {"schema_version": API_REQUEST_SCHEMA_VERSION}, separators=(",", ":")
        ).encode()
        headers = self.post_headers()
        headers["X-SSA-Shutdown-Token"] = SHUTDOWN
        with patch(
            "synthetic_sales_assist.portal.server.validate_shutdown_response",
            side_effect=PortalContractError("RESPONSE_SHUTDOWN_TEST_INVALID", status=500),
        ):
            status, _, raw = self.request(
                "POST",
                "/api/v1/system/shutdown",
                body=body,
                headers=headers,
            )
        self.assertEqual(status, 500)
        self.assertEqual(
            json.loads(raw)["error"]["code"],
            "RESPONSE_SHUTDOWN_TEST_INVALID",
        )
        self.assertFalse(self.server.shutdown_requested.is_set())
        status, _, raw = self.request(
            "POST", "/api/v1/system/shutdown", body=body, headers=headers
        )
        self.assertEqual(status, 202)
        self.assertEqual(json.loads(raw)["data"]["status"], "SHUTDOWN_ACCEPTED")
        self.assertTrue(self.server.shutdown_requested.wait(timeout=2))


class _UnhealthyApplication(FakeApplication):
    def system_status(self, deep: bool = False) -> dict[str, object]:
        del deep
        return _status(healthy=False)


class PortalRuntimeSecurityTests(unittest.TestCase):
    def _paths(self) -> tuple[tempfile.TemporaryDirectory[str], object, Path]:
        temporary = tempfile.TemporaryDirectory(prefix="synthetic-sales-assist-m5-")
        self.addCleanup(temporary.cleanup)
        paths = resolve_data_paths(Path(temporary.name).resolve())
        paths.ensure_directories()
        receipt = paths.runtime / "service.json"
        return temporary, paths, receipt

    @staticmethod
    def _receipt(host: str = "127.0.0.1") -> RuntimeReceipt:
        authority = f"[{host}]" if host == "::1" else host
        return RuntimeReceipt(
            schema_version="synthetic-sales-assist-runtime-receipt/v1",
            pid=1234,
            process_start_time="2026-08-21T12:00:00.000000Z",
            process_identity_token="c" * 64,
            csrf_token="a" * 64,
            host=host,
            port=8765,
            shutdown_token="b" * 64,
            database_path=str(Path(tempfile.gettempdir()).resolve() / "synthetic.sqlite3"),
            app_version="0.1.0",
            build_version="synthetic-sales-assist-m5/v1",
            database_schema_version=4,
            origin="http" + f"://{authority}:8765",
        )

    def test_runtime_receipt_schema_hosts_and_token_independence_are_exact(self) -> None:
        for host in ("127.0.0.1", "localhost", "::1"):
            with self.subTest(host=host):
                receipt = self._receipt(host)
                self.assertEqual(frozenset(receipt.to_dict()), RUNTIME_RECEIPT_MEMBERS)
        value = self._receipt().to_dict()
        value["csrf_token"] = value["shutdown_token"]
        with self.assertRaisesRegex(
            PortalLifecycleError, "RUNTIME_RECEIPT_TOKENS_NOT_INDEPENDENT"
        ):
            RuntimeReceipt(**value)  # type: ignore[arg-type]

    def test_runtime_publishes_canonical_owned_receipt_then_cleans_up(self) -> None:
        _temporary, paths, receipt_path = self._paths()
        runtime = PortalRuntime(
            FakeApplication(),
            paths=paths,  # type: ignore[arg-type]
            receipt_path=receipt_path,
            config=PortalServerConfig(port=0),
        )
        receipt = runtime.start()
        try:
            self.assertTrue(receipt_path.is_file())
            raw = receipt_path.read_bytes()
            value = json.loads(raw)
            self.assertEqual(frozenset(value), RUNTIME_RECEIPT_MEMBERS)
            self.assertEqual(raw, receipt.canonical_bytes())
            self.assertEqual(value["csrf_token"], runtime.csrf_token)
            self.assertNotEqual(value["csrf_token"], value["shutdown_token"])
            self.assertEqual(value["build_version"], "synthetic-sales-assist-m5/v1")
            self.assertEqual(
                value["database_path"], str(paths.database)  # type: ignore[attr-defined]
            )
            descriptor = os.open(Path(f"{receipt_path}.lock"), os.O_RDONLY)
            try:
                self.assertEqual(
                    os.read(descriptor, 64).decode("ascii"),
                    runtime.process_identity_token,
                )
                self.assertEqual(os.fstat(descriptor).st_size, 64)
            finally:
                os.close(descriptor)
        finally:
            runtime.close()
        self.assertFalse(receipt_path.exists())
        self.assertFalse(Path(f"{receipt_path}.lock").exists())

    def test_server_bind_never_calls_name_resolution(self) -> None:
        with (
            patch("socket.getfqdn", side_effect=AssertionError("resolver prohibited")),
            patch("socket.gethostbyaddr", side_effect=AssertionError("resolver prohibited")),
            patch("socket.getaddrinfo", side_effect=AssertionError("resolver prohibited")),
        ):
            server = PortalHTTPServer(
                FakeApplication(),
                PortalServerConfig(port=0),
                csrf_token=CSRF,
                shutdown_token=SHUTDOWN,
            )
        server.server_close()

    def test_default_application_open_occurs_only_after_process_lease(self) -> None:
        _temporary, paths, receipt_path = self._paths()
        runtime_holder: dict[str, PortalRuntime] = {}

        def open_application(data_dir: Path | None) -> FakeApplication:
            self.assertEqual(data_dir, paths.root)  # type: ignore[attr-defined]
            runtime = runtime_holder["runtime"]
            self.assertIsNotNone(runtime.lease._handle)
            self.assertTrue(runtime.lease.lock_path.is_file())
            return FakeApplication()

        with patch(
            "synthetic_sales_assist.application.ScenarioApplication.open",
            side_effect=open_application,
        ) as application_open:
            runtime = open_runtime(
                data_dir=paths.root,  # type: ignore[attr-defined]
                receipt_path=receipt_path,
                port=0,
            )
            runtime_holder["runtime"] = runtime
            application_open.assert_not_called()
            runtime.start()
            application_open.assert_called_once_with(paths.root)  # type: ignore[attr-defined]
            runtime.close()

    def test_real_scenario_application_passes_deep_startup_health(self) -> None:
        _temporary, paths, receipt_path = self._paths()
        application = ScenarioApplication.open(paths.root)  # type: ignore[attr-defined]
        runtime = PortalRuntime(
            application,
            paths=paths,  # type: ignore[arg-type]
            receipt_path=receipt_path,
            config=PortalServerConfig(port=0),
        )
        receipt = runtime.start()
        try:
            self.assertEqual(receipt.database_schema_version, 4)
            self.assertEqual(receipt.build_version, "synthetic-sales-assist-m5/v1")
            self.assertTrue(receipt_path.is_file())
        finally:
            runtime.close()

    def test_real_http_instantiates_all_required_aliases_and_persists_evaluation(
        self,
    ) -> None:
        _temporary, paths, receipt_path = self._paths()
        application = ScenarioApplication.open(paths.root)  # type: ignore[attr-defined]
        runtime = PortalRuntime(
            application,
            paths=paths,  # type: ignore[arg-type]
            receipt_path=receipt_path,
            config=PortalServerConfig(port=0),
        )
        receipt = runtime.start()
        server = runtime.server
        self.assertIsNotNone(server)
        assert server is not None
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def request(
            method: str,
            target: str,
            body: bytes | None = None,
        ) -> tuple[int, bytes]:
            connection = http.client.HTTPConnection(
                "127.0.0.1", receipt.port, timeout=10
            )
            headers = {"Host": f"127.0.0.1:{receipt.port}"}
            if method == "POST":
                headers.update(
                    {
                        "Content-Type": "application/json",
                        "Origin": receipt.origin,
                        "X-SSA-CSRF-Token": receipt.csrf_token,
                    }
                )
            connection.request(method, target, body=body, headers=headers)
            response = connection.getresponse()
            result = response.status, response.read()
            connection.close()
            return result

        try:
            aliases = (
                "sales-credit-target-rep",
                "sales-credit-human-review",
                "doi-fulfillment-split",
                "doi-full-ds",
                "doi-manual-review",
                "doi-overlap",
                "malformed-input",
            )
            order_ids: dict[str, str] = {}
            for index, alias in enumerate(aliases, start=1):
                body = json.dumps(
                    {
                        "mode": "complete",
                        "request_key": f"REAL-PORTAL-INSTANTIATE-{index}",
                        "schema_version": API_REQUEST_SCHEMA_VERSION,
                    },
                    separators=(",", ":"),
                ).encode()
                status, raw = request(
                    "POST", f"/api/v1/scenarios/{alias}/instantiate", body
                )
                self.assertEqual(status, 201, alias)
                order_id = json.loads(raw)["data"]["order_id"]
                self.assertTrue(
                    is_reserved_identity(order_id, expected_namespace="ORDER"), alias
                )
                order_ids[alias] = order_id

            representation_modes = (
                "missing-required-section",
                "identity-mismatch",
                "duplicate-line",
                "declared-rendered-mismatch",
                "stale-source-changed",
                "dom-payload-mismatch",
                "malformed-value",
            )
            for index, mode in enumerate(representation_modes, start=1):
                body = json.dumps(
                    {
                        "mode": mode,
                        "request_key": f"REAL-PORTAL-REPRESENTATION-{index}",
                        "schema_version": API_REQUEST_SCHEMA_VERSION,
                    },
                    separators=(",", ":"),
                ).encode()
                status, raw = request(
                    "POST",
                    "/api/v1/scenarios/doi-fulfillment-split/instantiate",
                    body,
                )
                self.assertEqual(status, 201, mode)
                representation = json.loads(raw)["data"]
                expected_state = "MALFORMED" if mode == "malformed-value" else "INCOMPLETE"
                self.assertEqual(representation["source_status"], expected_state, mode)
                representation_id = representation["order_id"]
                status, _ = request(
                    "GET",
                    f"/api/v1/orders/{representation_id}",
                )
                self.assertEqual(status, 200, mode)
                status, _ = request("GET", f"/orders/{representation_id}")
                self.assertEqual(status, 200, mode)
            order_id = order_ids["doi-overlap"]

            status, page = request("GET", f"/orders/{order_id}")
            self.assertEqual(status, 200)
            self.assertIn(b"synthetic-sales-assist-m5/v1", page)
            self.assertIn(b"ssa-synthetic-order-payload", page)

            evaluate = json.dumps(
                {
                    "request_key": "REAL-PORTAL-EVALUATE-1",
                    "schema_version": API_REQUEST_SCHEMA_VERSION,
                },
                separators=(",", ":"),
            ).encode()
            status, raw = request(
                "POST", f"/api/v1/orders/{order_id}/evaluate", evaluate
            )
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(raw)["data"]["top_level_result"], "DOI_OPPORTUNITY")

            status, raw = request("GET", f"/api/v1/orders/{order_id}/history")
            self.assertEqual(status, 200)
            history = json.loads(raw)["data"]
            self.assertTrue(history["artifacts"])
            self.assertTrue(history["receipts"])
            self.assertTrue(history["attempt_receipts"])
            self.assertEqual(history["telemetry_event_count"], 1)

            sales_credit_id = order_ids["sales-credit-target-rep"]
            sales_credit_evaluate = json.dumps(
                {
                    "request_key": "REAL-PORTAL-SALES-CREDIT-EVALUATE-1",
                    "schema_version": API_REQUEST_SCHEMA_VERSION,
                },
                separators=(",", ":"),
            ).encode()
            status, sales_credit_raw = request(
                "POST",
                f"/api/v1/orders/{sales_credit_id}/evaluate",
                sales_credit_evaluate,
            )
            self.assertEqual(status, 200, sales_credit_raw)
            for target in (
                f"/api/v1/orders/{sales_credit_id}",
                f"/api/v1/orders/{sales_credit_id}/history",
                f"/orders/{sales_credit_id}",
            ):
                status, _ = request("GET", target)
                self.assertEqual(status, 200, target)
        finally:
            server.shutdown()
            thread.join(timeout=3)
            runtime.close()

    def test_runtime_rejects_arbitrary_receipt_path_without_overwrite(self) -> None:
        _temporary, paths, _receipt_path = self._paths()
        unrelated = paths.root / "unrelated.json"  # type: ignore[attr-defined]
        unrelated.write_bytes(b"preserve")
        with self.assertRaisesRegex(PortalServerError, "RUNTIME_RECEIPT_PATH_INVALID"):
            PortalRuntime(
                FakeApplication(),
                paths=paths,  # type: ignore[arg-type]
                receipt_path=unrelated,
                config=PortalServerConfig(port=0),
            )
        self.assertEqual(unrelated.read_bytes(), b"preserve")

    def test_runtime_rejects_reparse_runtime_parent_before_application_open(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        target = root / "runtime-target"
        target.mkdir()
        runtime_parent = root / "runtime"
        try:
            runtime_parent.symlink_to(target, target_is_directory=True)
        except OSError:
            _temporary, paths, receipt_path = self._paths()
            runtime = PortalRuntime(
                FakeApplication(),
                paths=paths,  # type: ignore[arg-type]
                receipt_path=receipt_path,
                config=PortalServerConfig(port=0),
            )
            with patch(
                "synthetic_sales_assist.portal.lifecycle.assert_real_local_directory",
                side_effect=PathPolicyError("CONTROLLED_DIRECTORY_REPARSE_POINT"),
            ):
                with self.assertRaisesRegex(
                    PortalLifecycleError,
                    "RUNTIME_RECEIPT_PARENT_INVALID",
                ):
                    runtime.start()
            return
        paths = DataPaths(
            root=root,
            data=root / "data",
            logs=root / "logs",
            backups=root / "backups",
            runtime=runtime_parent,
            exports=root / "exports",
            database=root / "data" / "synthetic_sales_assist.sqlite3",
        )
        runtime = PortalRuntime(
            FakeApplication(),
            paths=paths,
            receipt_path=runtime_parent / "service.json",
            config=PortalServerConfig(port=0),
        )
        with self.assertRaisesRegex(
            PortalLifecycleError,
            "RUNTIME_RECEIPT_PARENT_INVALID",
        ):
            runtime.start()

    def test_startup_deep_health_failure_leaves_no_receipt_or_lock(self) -> None:
        _temporary, paths, receipt_path = self._paths()
        runtime = PortalRuntime(
            _UnhealthyApplication(),
            paths=paths,  # type: ignore[arg-type]
            receipt_path=receipt_path,
            config=PortalServerConfig(port=0),
        )
        with self.assertRaisesRegex(PortalServerError, "PORTAL_STARTUP_HEALTH_FAILED"):
            runtime.start()
        self.assertFalse(receipt_path.exists())
        self.assertFalse(Path(f"{receipt_path}.lock").exists())


if __name__ == "__main__":
    unittest.main()
