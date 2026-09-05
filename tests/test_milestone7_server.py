from __future__ import annotations

import http.client
import json
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

from synthetic_sales_assist.application import ScenarioApplication
from synthetic_sales_assist.application.control_center import (
    M4_BENCHMARK_REFERENCE,
    MetricWindow,
    PageRequest,
)
from synthetic_sales_assist.domain.numeric import JSON_SAFE_INTEGER_MAXIMUM
from synthetic_sales_assist.portal.contracts import (
    API_REQUEST_SCHEMA_VERSION,
    API_SCHEMA_VERSION,
    BACKUP_ACTION_RESULT_SCHEMA_VERSION,
    BACKUP_CREATE_REQUEST_SCHEMA_VERSION,
    DATABASE_VERIFY_REQUEST_SCHEMA_VERSION,
    DOI_SCENARIO_SELECTION_REQUEST_SCHEMA_VERSION,
    EXTENSION_HANDSHAKE_SCHEMA_VERSION,
    HUMAN_ACTION_RESULT_SCHEMA_VERSION,
    MANAGER_OUTCOME_REQUEST_SCHEMA_VERSION,
    PortalContractError,
    parse_manager_outcome_request,
    validate_dashboard_response,
)
from synthetic_sales_assist.portal.dashboard_assets import DASHBOARD_JS
from synthetic_sales_assist.portal.server import (
    CSRF_HEADER,
    EXPECTED_EXTENSION_PACKAGE_SHA256,
    EXPECTED_EXTENSION_VERSION,
    PortalHTTPServer,
    PortalServerConfig,
)
from synthetic_sales_assist.safety.content import ProhibitedInputError


CSRF = "a" * 64
SHUTDOWN = "b" * 64
ORDER_ID = "SYN-ORDER-M7-SERVER-0001"
CASE_ID = "SYN-EVIDENCE-M7-CASE-0001"
OPPORTUNITY_A = "SYN-EVIDENCE-M7-OPPORTUNITY-0001"
OPPORTUNITY_B = "SYN-EVIDENCE-M7-OPPORTUNITY-0002"
ACTOR_ID = "SYN-REP-M7-MANAGER-0001"


def _status() -> dict[str, object]:
    return {
        "app_version": "0.1.3",
        "build_version": "synthetic-sales-assist-m8/v1",
        "database_schema_version": 4,
        "database_status": "PASS",
        "evaluated_count": 0,
        "expected_schema_version": 4,
        "integrity_check": "ok",
        "migration_status": "CURRENT",
        "projection_status": "PASS",
        "quick_check": "ok",
        "registry_capacity": 256,
        "registry_count": 0,
        "safety_counters": {
            "EXTERNAL_MUTATION_REQUEST_COUNT": 0,
            "EXTERNAL_PRODUCTION_SYSTEM_ACCESS_COUNT": 0,
            "NON_LOCALHOST_RUNTIME_REQUEST_COUNT": 0,
            "NON_SYNTHETIC_FIXTURE_COUNT": 0,
            "PRODUCTION_MUTATION_REQUEST_COUNT": 0,
            "PRODUCTION_SYSTEM_ACCESS_COUNT": 0,
            "REAL_CUSTOMER_DATA_COUNT": 0,
            "REAL_CUSTOMER_IDENTITY_COUNT": 0,
            "SECRET_MATERIAL_COUNT": 0,
        },
        "schema_version": "synthetic-sales-assist-application/v1",
    }


def _data(payload: dict[str, object] | None) -> dict[str, object]:
    assert payload is not None
    return cast(dict[str, object], payload["data"])


def _error_code(payload: dict[str, object] | None) -> str:
    assert payload is not None
    error = cast(dict[str, object], payload["error"])
    return cast(str, error["code"])


class _Application:
    def system_status(self, deep: bool = False) -> dict[str, object]:
        del deep
        return _status()


class _ControlCenter:
    def __init__(self) -> None:
        self.queue_request: PageRequest | None = None
        self.manager_calls: list[tuple[str, dict[str, object]]] = []
        self.selection_calls: list[tuple[str, dict[str, object]]] = []
        self.backup_calls: list[dict[str, object]] = []
        self.deep_verify_calls = 0

    def overview_view(self, window: MetricWindow) -> dict[str, object]:
        return {
            "schema_version": "synthetic-sales-assist-control-center/v1",
            "window": window.label,
        }

    def sales_credit_queue_view(self, request: PageRequest) -> dict[str, object]:
        self.queue_request = request
        return {
            "items": [],
            "limit": request.limit,
            "offset": request.offset,
            "query": {
                "descending": request.descending,
                "search": request.search,
                "sort_by": request.sort_by,
                "state": request.state,
            },
            "schema_version": "synthetic-sales-assist-control-center/v1",
            "total_count": 0,
        }

    def doi_queue_view(self, request: PageRequest) -> dict[str, object]:
        return self.sales_credit_queue_view(request)

    def review_queue_view(self) -> dict[str, object]:
        return {
            "items": [],
            "schema_version": "synthetic-sales-assist-control-center/v1",
            "total_count": 0,
        }

    def sales_credit_detail(self, order_id: str) -> dict[str, object]:
        return {"order_id": order_id, "schema_version": "synthetic-sales-assist-control-center/v1"}

    def doi_detail(self, case_id: str) -> dict[str, object]:
        return {"case_id": case_id, "schema_version": "synthetic-sales-assist-control-center/v1"}

    def audit_view(self, subject_kind: str, subject_id: str) -> dict[str, object]:
        events: list[dict[str, object]] = []
        if subject_kind == "EVALUATION":
            events.append(
                {
                    "event_id": subject_id,
                    "event_kind": "EVALUATION_RECORDED",
                    "occurred_at": "2026-09-01T12:00:00Z",
                    "sequence": 1,
                    "state": "MANUAL_REVIEW_REQUIRED",
                    "transition_id": None,
                }
            )
        return {
            "events": events,
            "schema_version": "synthetic-sales-assist-control-center/v1",
            "subject_id": subject_id,
            "subject_kind": subject_kind,
        }

    def database_view(self, **_kwargs: object) -> dict[str, object]:
        return {
            "database": {
                "application_schema_version": "synthetic-sales-assist-application/v1",
                "build_version": "synthetic-sales-assist-m8/v1",
                "database_location_class": "LOCAL_TEMPORARY",
                "database_size_bytes": 4096,
                "database_status": "HEALTHY",
                "foreign_key_status": "OK",
                "integrity_check": "ok",
                "latest_backup": None,
                "latest_restore": None,
                "migrations": [
                    {
                        "applied_at_utc": "2026-09-01T12:00:00Z",
                        "name": name,
                        "sha256": sha256,
                        "version": version,
                    }
                    for version, name, sha256 in (
                        (
                            1,
                            "foundation",
                            "5693cfe9868f10868d134bd042ccc26271126be9eae847a214c26f57216d6638",
                        ),
                        (
                            2,
                            "shared_persistence",
                            "5e6f5ea08a4cfd5ec6241da60c49721d99c246fa1e4251d44293a1487e749e31",
                        ),
                        (
                            3,
                            "sales_credit_persistence",
                            "fd22b13f73d389422405bf222313e34a4aa5995f6b28610a222108a3da813395",
                        ),
                        (
                            4,
                            "doi_persistence",
                            "5799e5fe3b0e1c9ffae948f6c6b0a820556a9a0d200b29d7c5751e80c475b09d",
                        ),
                    )
                ],
                "projection_status": "OK",
                "quick_check": "ok",
                "safety_counters": _status()["safety_counters"],
                "safety_observed_at": "2026-09-01T12:03:00Z",
                "schema_version": 4,
                "verification_observed_at": "2026-09-01T12:03:00Z",
            },
            "schema_version": "synthetic-sales-assist-control-center/v1",
        }

    def backups_view(self) -> dict[str, object]:
        return {
            "items": [],
            "schema_version": "synthetic-sales-assist-control-center/v1",
            "total_count": 0,
        }

    def telemetry_view(self, window: MetricWindow) -> dict[str, object]:
        return {
            "schema_version": "synthetic-sales-assist-control-center/v1",
            "window": window.label,
        }

    def system_view(self, **kwargs: object) -> dict[str, object]:
        return {
            "database": {
                "database_status": "HEALTHY",
                "latest_backup": None,
            },
            "extension": self.extension_status_view(
                expected_version=cast(str, kwargs["expected_extension_version"]),
                expected_package_sha256=cast(str, kwargs["expected_extension_package_sha256"]),
                package_available=cast(bool, kwargs["extension_package_available"]),
                observed_version=cast(str | None, kwargs["observed_extension_version"]),
                observed_at=kwargs["extension_observed_at"],
                now=kwargs["now"],
            )["extension"],
            "schema_version": "synthetic-sales-assist-control-center/v1",
        }

    @staticmethod
    def extension_status_view(**kwargs: object) -> dict[str, object]:
        observed = cast(str | None, kwargs["observed_version"])
        return {
            "extension": {
                "expected_package_sha256": kwargs["expected_package_sha256"],
                "expected_version": kwargs["expected_version"],
                "last_seen_at": None,
                "observed_version": observed,
                "schema_version": "synthetic-sales-assist-extension-status/v1",
                "stale_after_seconds": 300,
                "state": "EXPECTED_PACKAGE_ONLY" if observed is None else "LAST_SEEN_HEALTHY",
            },
            "schema_version": "synthetic-sales-assist-control-center/v1",
        }

    def record_sales_credit_manager_outcome(
        self, order_id: str, **kwargs: object
    ) -> dict[str, object]:
        self.manager_calls.append((order_id, kwargs))
        return {
            "command_id": "SYN-EVIDENCE-M7-COMMAND-SC-0001",
            "evaluation_id": None,
            "recorded_at": "2026-09-01T12:00:00Z",
            "replayed": False,
            "schema_version": HUMAN_ACTION_RESULT_SCHEMA_VERSION,
            "status": "RECORDED",
            "subject_id": order_id,
        }

    def record_doi_overlap_selection(self, case_id: str, **kwargs: object) -> dict[str, object]:
        self.selection_calls.append((case_id, kwargs))
        return {
            "command_id": "SYN-EVIDENCE-M7-COMMAND-DOI-0001",
            "evaluation_id": "SYN-EVALUATION-M7-SELECTION-0001",
            "recorded_at": "2026-09-01T12:01:00Z",
            "replayed": False,
            "schema_version": HUMAN_ACTION_RESULT_SCHEMA_VERSION,
            "status": "RECORDED",
            "subject_id": case_id,
        }

    def deep_verify(self) -> dict[str, object]:
        self.deep_verify_calls += 1
        return self.database_view()

    def create_verified_backup(self, **kwargs: object) -> dict[str, object]:
        self.backup_calls.append(kwargs)
        return {
            "backup_id": "SYN-EVIDENCE-BACKUP-M7-0001",
            "backup_sha256": "c" * 64,
            "completed_at": "2026-09-01T12:02:00Z",
            "location_class": "OWNED_LOCAL_BACKUP_DIRECTORY",
            "replayed": False,
            "schema_version": BACKUP_ACTION_RESULT_SCHEMA_VERSION,
            "status": "RECORDED",
            "verified_schema_version": 4,
        }


class Milestone7ServerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.control_center = _ControlCenter()
        self.server = PortalHTTPServer(
            cast(Any, _Application()),
            PortalServerConfig(port=0),
            csrf_token=CSRF,
            shutdown_token=SHUTDOWN,
        )
        self.server.control_center = cast(Any, self.control_center)
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
        payload: object | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], dict[str, object] | None]:
        body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode()
        request_headers = {} if headers is None else dict(headers)
        request_headers.setdefault("Host", f"127.0.0.1:{self.port}")
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        connection.request(method, path, body=body, headers=request_headers)
        response = connection.getresponse()
        raw = response.read()
        result_headers = dict(response.getheaders())
        connection.close()
        decoded = (
            json.loads(raw)
            if raw and result_headers["Content-Type"].startswith("application/json")
            else None
        )
        return response.status, result_headers, decoded

    def post_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Origin": f"http://127.0.0.1:{self.port}",
            CSRF_HEADER: CSRF,
        }

    def test_root_redirects_to_overview_and_keeps_strict_security_headers(self) -> None:
        status, headers, payload = self.request("GET", "/")
        self.assertEqual(status, 303)
        self.assertEqual(headers["Location"], "/overview")
        self.assertIsNone(payload)
        self.assertEqual(headers["Content-Security-Policy"].count("'self'"), 5)
        self.assertEqual(headers["Cache-Control"], "no-store, max-age=0")

    def test_dashboard_assets_are_exact_local_get_resources(self) -> None:
        for path, content_type in (
            ("/static/ssa-dashboard.css", "text/css; charset=utf-8"),
            ("/static/ssa-dashboard.js", "text/javascript; charset=utf-8"),
        ):
            with self.subTest(path=path):
                status, headers, payload = self.request("GET", path)
                self.assertEqual(status, 200)
                self.assertEqual(headers["Content-Type"], content_type)
                self.assertIsNone(payload)
                self.assertEqual(headers["Cross-Origin-Resource-Policy"], "same-origin")

    def test_closed_queue_query_normalizes_pagination_and_rejects_open_search(self) -> None:
        status, _, payload = self.request(
            "GET",
            "/api/v1/dashboard/sales-credit?q=SYN-ORDER-M7&state=MANUAL_REVIEW_REQUIRED"
            "&sort=order_id&direction=asc&page=2&page_size=10",
        )
        self.assertEqual(status, 200)
        self.assertEqual(cast(dict[str, object], payload)["schema_version"], API_SCHEMA_VERSION)
        request = self.control_center.queue_request
        assert request is not None
        self.assertEqual(
            (request.search, request.state, request.offset, request.limit),
            ("SYN-ORDER-M7", "MANUAL_REVIEW_REQUIRED", 10, 10),
        )
        self.assertFalse(request.descending)
        for query in (
            "",
            "q=not-synthetic",
            "q=SYN-ORDER-M7&q=SYN-ORDER-M8",
            "q=SYN-ORDER-%ZZ",
            "operator=OR%201%3D1",
            "page=0",
            "page_size=11",
        ):
            with self.subTest(query=query):
                status, _, payload = self.request("GET", f"/api/v1/dashboard/sales-credit?{query}")
                self.assertEqual(status, 400)
                self.assertIn(
                    _error_code(payload),
                    {
                        "DASHBOARD_QUERY_INVALID",
                        "DASHBOARD_SEARCH_INVALID",
                        "DASHBOARD_PAGE_INVALID",
                        "REQUEST_TARGET_INVALID",
                    },
                )

    def test_native_queue_get_accepts_only_blank_optional_q_and_state(self) -> None:
        query = "q=&state=&sort=updated_at&direction=desc&page=1&page_size=25"
        for path in (
            f"/sales-credit?{query}",
            f"/api/v1/dashboard/sales-credit?{query}",
        ):
            with self.subTest(path=path):
                status, _, _ = self.request("GET", path)
                self.assertEqual(status, 200)
                request = self.control_center.queue_request
                assert request is not None
                self.assertIsNone(request.search)
                self.assertIsNone(request.state)
        for query_member in (
            "q=&state=&sort=&direction=desc&page=1&page_size=25",
            "q=&state=&sort=updated_at&direction=&page=1&page_size=25",
            "q=&state=&sort=updated_at&direction=desc&page=&page_size=25",
            "q=&state=&sort=updated_at&direction=desc&page=1&page_size=",
            "q=&state=&sort=updated_at&direction=desc&page=1&page_size=25&presentation=",
        ):
            with self.subTest(query=query_member):
                status, _, _ = self.request("GET", f"/sales-credit?{query_member}")
                self.assertEqual(status, 400)

    def test_queries_remain_prohibited_on_m5_routes_and_fixed_dashboard_apis(self) -> None:
        for path in (
            "/api/v1/orders?x=1",
            "/api/v1/dashboard/review?presentation=1",
            "/api/v1/dashboard/evidence?x=1",
        ):
            with self.subTest(path=path):
                status, _, payload = self.request("GET", path)
                self.assertEqual(status, 400)
                self.assertEqual(_error_code(payload), "REQUEST_TARGET_INVALID")

    def test_extension_handshake_canonicalizes_fractional_clock_precision(self) -> None:
        body = {
            "extension_version": EXPECTED_EXTENSION_VERSION,
            "schema_version": EXTENSION_HANDSHAKE_SCHEMA_VERSION,
        }
        for micros, expected in ((120000, ".12Z"), (123450, ".12345Z"), (0, "Z")):
            with self.subTest(microsecond=micros):
                instant = datetime(2026, 9, 5, 10, 0, 0, micros, tzinfo=timezone.utc)
                with patch("synthetic_sales_assist.portal.server.datetime") as clock:
                    clock.now.return_value = instant
                    status, _, payload = self.request(
                        "POST", "/api/v1/system/extension/handshake",
                        payload=body, headers=self.post_headers(),
                    )
                self.assertEqual(status, 200, payload)
                self.assertEqual(_data(payload)["last_seen_at"], "2026-09-05T10:00:00" + expected)
                self.assertEqual(self.server.extension_observation()[1], instant)

    def test_extension_handshake_is_closed_same_origin_and_process_local(self) -> None:
        body = {
            "extension_version": EXPECTED_EXTENSION_VERSION,
            "schema_version": EXTENSION_HANDSHAKE_SCHEMA_VERSION,
        }
        status, _, payload = self.request(
            "POST",
            "/api/v1/system/extension/handshake",
            payload=body,
            headers=self.post_headers(),
        )
        self.assertEqual(status, 200)
        data = cast(dict[str, object], cast(dict[str, object], payload)["data"])
        self.assertEqual(
            set(data),
            {
                "expected_extension_version",
                "last_seen_at",
                "observed_extension_version",
                "stale_after_seconds",
                "status",
            },
        )
        self.assertEqual(data["status"], "LAST_SEEN_HEALTHY")
        self.assertEqual(self.server.extension_observation()[0], EXPECTED_EXTENSION_VERSION)
        self.assertEqual(
            EXPECTED_EXTENSION_PACKAGE_SHA256,
            "3c0d145c789fb990c9fe849f16a031f397285de020ec14b6bb97551ddf1aca55",
        )

        status, _, payload = self.request(
            "POST",
            "/api/v1/system/extension/handshake",
            payload={**body, "extra": "PROHIBITED"},
            headers=self.post_headers(),
        )
        self.assertEqual(status, 400)
        self.assertEqual(_error_code(payload), "JSON_MEMBERS_INVALID")

    def test_new_post_routes_require_origin_and_csrf_before_dispatch(self) -> None:
        status, _, payload = self.request(
            "POST",
            "/api/v1/system/extension/handshake",
            payload={
                "extension_version": EXPECTED_EXTENSION_VERSION,
                "schema_version": EXTENSION_HANDSHAKE_SCHEMA_VERSION,
            },
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 403)
        self.assertEqual(_error_code(payload), "ORIGIN_INVALID")
        self.assertEqual(self.server.extension_observation(), (None, None))

    def test_manager_outcome_dispatch_is_closed_and_preserves_canonical_time(self) -> None:
        body = {
            "actor_id": ACTOR_ID,
            "amount_minor_units": 1250,
            "confirmed": True,
            "currency_code": "USD",
            "decided_at": "2026-09-01T12:00:00Z",
            "outcome": "PARTIAL",
            "request_key": "M7-SC-OUTCOME-0001",
            "request_schema_version": API_REQUEST_SCHEMA_VERSION,
            "schema_version": MANAGER_OUTCOME_REQUEST_SCHEMA_VERSION,
        }
        status, _, payload = self.request(
            "POST",
            f"/api/v1/dashboard/sales-credit/{ORDER_ID}/manager-outcome",
            payload=body,
            headers=self.post_headers(),
        )
        self.assertEqual(status, 200)
        self.assertEqual(_data(payload)["status"], "RECORDED")
        order_id, call = self.control_center.manager_calls[0]
        self.assertEqual(order_id, ORDER_ID)
        self.assertEqual(call["decided_at"], body["decided_at"])
        self.assertEqual(call["amount_minor_units"], 1250)

        invalid = {**body, "outcome": "APPROVED"}
        status, _, payload = self.request(
            "POST",
            f"/api/v1/dashboard/sales-credit/{ORDER_ID}/manager-outcome",
            payload=invalid,
            headers=self.post_headers(),
        )
        self.assertEqual(status, 400)
        self.assertEqual(_error_code(payload), "MANAGER_OUTCOME_MONEY_PROHIBITED")
        self.assertEqual(len(self.control_center.manager_calls), 1)

        status, _, payload = self.request(
            "POST",
            f"/api/v1/dashboard/sales-credit/{ORDER_ID}/manager-outcome",
            payload={**body, "request_key": "K" * 97},
            headers=self.post_headers(),
        )
        self.assertEqual(status, 400)
        self.assertEqual(_error_code(payload), "REQUEST_KEY_INVALID")
        self.assertEqual(len(self.control_center.manager_calls), 1)

    def test_manager_outcome_money_transport_preserves_only_safe_integers(self) -> None:
        body = {
            "actor_id": ACTOR_ID,
            "amount_minor_units": JSON_SAFE_INTEGER_MAXIMUM,
            "confirmed": True,
            "currency_code": "USD",
            "decided_at": "2026-09-01T12:00:00Z",
            "outcome": "PARTIAL",
            "request_key": "M7-SC-SAFE-INTEGER-BOUNDARY",
            "request_schema_version": API_REQUEST_SCHEMA_VERSION,
            "schema_version": MANAGER_OUTCOME_REQUEST_SCHEMA_VERSION,
        }
        encoded = json.dumps(body, separators=(",", ":")).encode("utf-8")
        parsed = parse_manager_outcome_request(encoded)
        self.assertEqual(
            parsed["amount_minor_units"],
            JSON_SAFE_INTEGER_MAXIMUM,
        )
        status, _, payload = self.request(
            "POST",
            f"/api/v1/dashboard/sales-credit/{ORDER_ID}/manager-outcome",
            payload=body,
            headers=self.post_headers(),
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            self.control_center.manager_calls[-1][1]["amount_minor_units"],
            JSON_SAFE_INTEGER_MAXIMUM,
        )

        overflow = {**body, "amount_minor_units": 9_007_199_254_740_993}
        with self.assertRaises(PortalContractError) as caught:
            parse_manager_outcome_request(
                json.dumps(overflow, separators=(",", ":")).encode("utf-8")
            )
        self.assertEqual(caught.exception.code, "MANAGER_OUTCOME_AMOUNT_INVALID")
        prior_calls = len(self.control_center.manager_calls)
        status, _, payload = self.request(
            "POST",
            f"/api/v1/dashboard/sales-credit/{ORDER_ID}/manager-outcome",
            payload=overflow,
            headers=self.post_headers(),
        )
        self.assertEqual(status, 400)
        self.assertEqual(_error_code(payload), "MANAGER_OUTCOME_AMOUNT_INVALID")
        self.assertEqual(len(self.control_center.manager_calls), prior_calls)

    def test_dashboard_javascript_rejects_inexact_integer_transport(self) -> None:
        self.assertIn(
            "const jsonSafeIntegerMaximum = 9007199254740991;",
            DASHBOARD_JS,
        )
        self.assertIn("Number.isSafeInteger(integerValue)", DASHBOARD_JS)
        self.assertIn("integerValue > jsonSafeIntegerMaximum", DASHBOARD_JS)
        self.assertIn("integerValue <= 0", DASHBOARD_JS)
        self.assertNotIn("payload[control.name] = Number(value);", DASHBOARD_JS)

    def test_doi_scenario_selection_requires_exact_sorted_option_set(self) -> None:
        body = {
            "actor_id": ACTOR_ID,
            "confirmed": True,
            "evaluation_id": "SYN-EVALUATION-M7-OVERLAP-0001",
            "occurred_at": "2026-09-01T12:01:00Z",
            "option_opportunity_ids": [OPPORTUNITY_A, OPPORTUNITY_B],
            "request_key": "M7-DOI-SELECTION-0001",
            "request_schema_version": API_REQUEST_SCHEMA_VERSION,
            "schema_version": DOI_SCENARIO_SELECTION_REQUEST_SCHEMA_VERSION,
            "selected_opportunity_id": OPPORTUNITY_A,
        }
        status, _, _ = self.request(
            "POST",
            f"/api/v1/dashboard/doi/{CASE_ID}/scenario-selection",
            payload=body,
            headers=self.post_headers(),
        )
        self.assertEqual(status, 200)
        case_id, call = self.control_center.selection_calls[0]
        self.assertEqual(case_id, CASE_ID)
        self.assertEqual(call["evaluation_id"], body["evaluation_id"])
        self.assertEqual(call["option_opportunity_ids"], (OPPORTUNITY_A, OPPORTUNITY_B))
        self.assertEqual(call["occurred_at"], body["occurred_at"])

        status, _, payload = self.request(
            "POST",
            f"/api/v1/dashboard/doi/{CASE_ID}/scenario-selection",
            payload={**body, "option_opportunity_ids": [OPPORTUNITY_B, OPPORTUNITY_A]},
            headers=self.post_headers(),
        )
        self.assertEqual(status, 400)
        self.assertEqual(_error_code(payload), "DOI_SCENARIO_OPTIONS_INVALID")

    def test_deep_verify_is_read_only_and_backup_requires_confirmation_key(self) -> None:
        status, _, _ = self.request(
            "POST",
            "/api/v1/dashboard/system/database/verify",
            payload={"schema_version": DATABASE_VERIFY_REQUEST_SCHEMA_VERSION},
            headers=self.post_headers(),
        )
        self.assertEqual(status, 200)
        self.assertEqual(self.control_center.deep_verify_calls, 1)

        backup = {
            "confirmed": True,
            "request_key": "M7-BACKUP-0001",
            "request_schema_version": API_REQUEST_SCHEMA_VERSION,
            "schema_version": BACKUP_CREATE_REQUEST_SCHEMA_VERSION,
        }
        status, _, _ = self.request(
            "POST",
            "/api/v1/dashboard/system/backups",
            payload=backup,
            headers=self.post_headers(),
        )
        self.assertEqual(status, 201)
        self.assertEqual(
            self.control_center.backup_calls,
            [{"request_key": "M7-BACKUP-0001", "confirmed": True}],
        )

        status, _, payload = self.request(
            "POST",
            "/api/v1/dashboard/system/backups",
            payload={**backup, "confirmed": False},
            headers=self.post_headers(),
        )
        self.assertEqual(status, 400)
        self.assertEqual(_error_code(payload), "ACTION_CONFIRMATION_REQUIRED")
        self.assertEqual(len(self.control_center.backup_calls), 1)

    def test_dashboard_json_get_uses_exact_route_response_contract(self) -> None:
        original = self.control_center.sales_credit_queue_view

        def response_with_unknown(request: PageRequest) -> dict[str, object]:
            return {**original(request), "unexpected_member": "PROHIBITED"}

        target = cast(Any, self.control_center)
        target.sales_credit_queue_view = response_with_unknown
        status, _, payload = self.request(
            "GET",
            "/api/v1/dashboard/sales-credit?page=1&page_size=25",
        )
        self.assertEqual(status, 500)
        self.assertEqual(_error_code(payload), "DASHBOARD_SC_QUEUE_INVALID")

    def test_human_action_response_is_exact_and_bound_to_route_subject(self) -> None:
        original = self.control_center.record_sales_credit_manager_outcome
        body = {
            "actor_id": ACTOR_ID,
            "amount_minor_units": None,
            "confirmed": True,
            "currency_code": None,
            "decided_at": "2026-09-01T12:00:00Z",
            "outcome": "APPROVED",
            "request_key": "M7-SC-CLOSED-RESPONSE",
            "request_schema_version": API_REQUEST_SCHEMA_VERSION,
            "schema_version": MANAGER_OUTCOME_REQUEST_SCHEMA_VERSION,
        }

        def response_with_unknown(
            order_id: str,
            **kwargs: object,
        ) -> dict[str, object]:
            return {**original(order_id, **kwargs), "unexpected_member": True}

        target = cast(Any, self.control_center)
        target.record_sales_credit_manager_outcome = response_with_unknown
        status, _, payload = self.request(
            "POST",
            f"/api/v1/dashboard/sales-credit/{ORDER_ID}/manager-outcome",
            payload=body,
            headers=self.post_headers(),
        )
        self.assertEqual(status, 500)
        self.assertEqual(
            _error_code(payload),
            "RESPONSE_HUMAN_ACTION_MEMBERS_INVALID",
        )

        def response_for_wrong_subject(
            order_id: str,
            **kwargs: object,
        ) -> dict[str, object]:
            return {
                **original(order_id, **kwargs),
                "subject_id": "SYN-ORDER-M7-WRONG-SUBJECT",
            }

        target.record_sales_credit_manager_outcome = response_for_wrong_subject
        status, _, payload = self.request(
            "POST",
            f"/api/v1/dashboard/sales-credit/{ORDER_ID}/manager-outcome",
            payload={**body, "request_key": "M7-SC-WRONG-SUBJECT"},
            headers=self.post_headers(),
        )
        self.assertEqual(status, 500)
        self.assertEqual(
            _error_code(payload),
            "RESPONSE_HUMAN_ACTION_SUBJECT_INVALID",
        )

    def test_maintenance_action_results_reject_unknown_members(self) -> None:
        original_verify = self.control_center.deep_verify

        def verify_with_unknown() -> dict[str, object]:
            return {**original_verify(), "unexpected_member": True}

        self.control_center.deep_verify = verify_with_unknown  # type: ignore[method-assign]
        status, _, payload = self.request(
            "POST",
            "/api/v1/dashboard/system/database/verify",
            payload={"schema_version": DATABASE_VERIFY_REQUEST_SCHEMA_VERSION},
            headers=self.post_headers(),
        )
        self.assertEqual(status, 500)
        self.assertEqual(_error_code(payload), "DASHBOARD_DATABASE_VIEW_INVALID")

        original_backup = self.control_center.create_verified_backup

        def backup_with_unknown(**kwargs: object) -> dict[str, object]:
            return {**original_backup(**kwargs), "unexpected_member": True}

        target = cast(Any, self.control_center)
        target.create_verified_backup = backup_with_unknown
        status, _, payload = self.request(
            "POST",
            "/api/v1/dashboard/system/backups",
            payload={
                "confirmed": True,
                "request_key": "M7-BACKUP-CLOSED-RESPONSE",
                "request_schema_version": API_REQUEST_SCHEMA_VERSION,
                "schema_version": BACKUP_CREATE_REQUEST_SCHEMA_VERSION,
            },
            headers=self.post_headers(),
        )
        self.assertEqual(status, 500)
        self.assertEqual(
            _error_code(payload),
            "RESPONSE_BACKUP_ACTION_MEMBERS_INVALID",
        )

    def test_database_api_rejects_forged_governed_status(self) -> None:
        original = self.control_center.database_view

        def database_with_forged_status(**kwargs: object) -> dict[str, object]:
            response = original(**kwargs)
            database = cast(dict[str, object], response["database"])
            return {
                **response,
                "database": {**database, "database_status": "TRUST_ME"},
            }

        target = cast(Any, self.control_center)
        target.database_view = database_with_forged_status
        status, _, payload = self.request(
            "GET",
            "/api/v1/dashboard/system/database",
        )
        self.assertEqual(status, 500)
        self.assertEqual(_error_code(payload), "DASHBOARD_DATABASE_STATUS_INVALID")

    def test_doi_action_response_requires_a_synthetic_evaluation_id(self) -> None:
        original = self.control_center.record_doi_overlap_selection

        def response_without_evaluation(
            case_id: str,
            **kwargs: object,
        ) -> dict[str, object]:
            return {**original(case_id, **kwargs), "evaluation_id": None}

        target = cast(Any, self.control_center)
        target.record_doi_overlap_selection = response_without_evaluation
        status, _, payload = self.request(
            "POST",
            f"/api/v1/dashboard/doi/{CASE_ID}/scenario-selection",
            payload={
                "actor_id": ACTOR_ID,
                "confirmed": True,
                "evaluation_id": "SYN-EVALUATION-M7-OVERLAP-0001",
                "occurred_at": "2026-09-01T12:01:00Z",
                "option_opportunity_ids": [OPPORTUNITY_A, OPPORTUNITY_B],
                "request_key": "M7-DOI-CLOSED-RESPONSE",
                "request_schema_version": API_REQUEST_SCHEMA_VERSION,
                "schema_version": DOI_SCENARIO_SELECTION_REQUEST_SCHEMA_VERSION,
                "selected_opportunity_id": OPPORTUNITY_A,
            },
            headers=self.post_headers(),
        )
        self.assertEqual(status, 500)
        self.assertEqual(
            _error_code(payload),
            "RESPONSE_HUMAN_ACTION_EVALUATION_INVALID",
        )

    def test_evidence_and_audit_evaluation_routes_are_closed_gets(self) -> None:
        status, _, payload = self.request("GET", "/api/v1/dashboard/evidence")
        self.assertEqual(status, 200)
        data = cast(dict[str, object], cast(dict[str, object], payload)["data"])
        self.assertEqual(data["selector_prefix"], "data-ssa-dashboard-")
        status, _, payload = self.request(
            "GET", "/api/v1/dashboard/audit/evaluation/SYN-EVALUATION-M7-0001"
        )
        self.assertEqual(status, 200)
        data = cast(dict[str, object], cast(dict[str, object], payload)["data"])
        self.assertEqual(data["subject_kind"], "EVALUATION")

    def test_dashboard_safety_exemptions_do_not_exempt_identity_or_path_members(
        self,
    ) -> None:
        with self.assertRaises(ProhibitedInputError):
            validate_dashboard_response(
                {
                    "order_id": "person" + "@" + "example.com",
                    "schema_version": "synthetic-sales-assist-control-center/v1",
                }
            )
        with self.assertRaises(PortalContractError) as caught:
            validate_dashboard_response(
                {
                    "database_path": "C:/Users/example/private.sqlite3",
                    "schema_version": "synthetic-sales-assist-control-center/v1",
                }
            )
        self.assertEqual(caught.exception.code, "RESPONSE_MEMBER_PROHIBITED")
        with self.assertRaises(PortalContractError) as embedded:
            validate_dashboard_response(
                {
                    "label": "C:/Users/example/private.sqlite3",
                    "schema_version": "synthetic-sales-assist-control-center/v1",
                }
            )
        self.assertEqual(
            embedded.exception.code,
            "DASHBOARD_PRIVATE_PATH_PROHIBITED",
        )


class Milestone7RealApplicationRouteTest(unittest.TestCase):
    def test_empty_schema_four_application_renders_every_fixed_dashboard(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            application = ScenarioApplication.open(Path(directory))
            server = PortalHTTPServer(
                application,
                PortalServerConfig(port=0),
                csrf_token=CSRF,
                shutdown_token=SHUTDOWN,
            )
            port = int(server.server_address[1])
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                for path in (
                    "/overview",
                    "/sales-credit",
                    "/doi",
                    "/review",
                    "/system",
                    "/system/database",
                    "/system/backups",
                    "/system/telemetry",
                    "/system/extension",
                    "/api/v1/dashboard/overview",
                    "/api/v1/dashboard/sales-credit",
                    "/api/v1/dashboard/doi",
                    "/api/v1/dashboard/review",
                    "/api/v1/dashboard/system",
                    "/api/v1/dashboard/system/database",
                    "/api/v1/dashboard/system/backups",
                    "/api/v1/dashboard/system/telemetry",
                    "/api/v1/dashboard/system/extension",
                    "/api/v1/dashboard/evidence",
                ):
                    with self.subTest(path=path):
                        connection = http.client.HTTPConnection(
                            "127.0.0.1", port, timeout=5
                        )
                        connection.request(
                            "GET", path, headers={"Host": f"127.0.0.1:{port}"}
                        )
                        response = connection.getresponse()
                        raw = response.read()
                        connection.close()
                        self.assertEqual(response.status, 200, raw.decode(errors="replace"))
                        self.assertNotIn(str(Path(directory)).encode(), raw)
                        if path == "/api/v1/dashboard/system":
                            data = json.loads(raw)["data"]
                            self.assertEqual(
                                data["benchmark_reference"],
                                M4_BENCHMARK_REFERENCE.to_dict(),
                            )
                            self.assertEqual(data["recent_safe_errors"], [])
                            self.assertEqual(data["database"]["schema_version"], 4)
                            self.assertIsNone(data["database"]["latest_restore"])
                            self.assertTrue(
                                data["database"]["verification_observed_at"].endswith("Z")
                            )
                        if path == "/api/v1/dashboard/system/telemetry":
                            data = json.loads(raw)["data"]
                            self.assertEqual(
                                data["benchmark_reference"],
                                M4_BENCHMARK_REFERENCE.to_dict(),
                            )
                            self.assertEqual(data["metrics"]["database_error_count"], 0)
                            self.assertGreater(
                                data["operational_status"]["database_size_bytes"],
                                0,
                            )
            finally:
                server.shutdown()
                thread.join(timeout=3)
                server.server_close()


if __name__ == "__main__":
    unittest.main()
