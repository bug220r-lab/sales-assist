"""Real schema-4 HTTP coverage for the two supported M7 human actions."""

from __future__ import annotations

import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from typing import Any, cast

from synthetic_sales_assist.application import ScenarioApplication
from synthetic_sales_assist.application.control_center import ControlCenterApplication
from synthetic_sales_assist.portal.contracts import (
    API_REQUEST_SCHEMA_VERSION,
    DOI_SCENARIO_SELECTION_REQUEST_SCHEMA_VERSION,
    MANAGER_OUTCOME_REQUEST_SCHEMA_VERSION,
)
from synthetic_sales_assist.portal.server import (
    CSRF_HEADER,
    PortalHTTPServer,
    PortalServerConfig,
)


CSRF = "c" * 64
SHUTDOWN = "d" * 64


class Milestone7HumanActionHTTPTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="synthetic-sales-assist-m7-http-")
        self.addCleanup(temporary.cleanup)
        self.data_root = Path(temporary.name) / "owned-data"
        self.application = ScenarioApplication.open(self.data_root)
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
        payload: object | None = None,
    ) -> tuple[int, bytes, dict[str, object] | None]:
        body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode()
        headers = {"Host": f"127.0.0.1:{self.port}"}
        if payload is not None:
            headers.update(
                {
                    "Content-Type": "application/json",
                    "Origin": f"http://127.0.0.1:{self.port}",
                    CSRF_HEADER: CSRF,
                }
            )
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        content_type = response.getheader("Content-Type", "")
        status = response.status
        connection.close()
        decoded = (
            cast(dict[str, object], json.loads(raw))
            if content_type.startswith("application/json")
            else None
        )
        return status, raw, decoded

    def action_time(self) -> str:
        return (
            self.application.database.clock()
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z")
        )

    def test_sales_credit_success_replay_conflict_and_closed_detail(self) -> None:
        order = self.application.instantiate(
            "sales-credit-human-review",
            "m7-http-sc-instance",
        )
        self.application.evaluate(order.order_id, "m7-http-sc-evaluation")
        body = {
            "actor_id": "SYN-REP-M7-HTTP-MANAGER",
            "amount_minor_units": None,
            "confirmed": True,
            "currency_code": None,
            "decided_at": self.action_time(),
            "outcome": "APPROVED",
            "request_key": "M7-HTTP-SC-OUTCOME",
            "request_schema_version": API_REQUEST_SCHEMA_VERSION,
            "schema_version": MANAGER_OUTCOME_REQUEST_SCHEMA_VERSION,
        }
        path = f"/api/v1/dashboard/sales-credit/{order.order_id}/manager-outcome"
        first_status, _, first = self.request("POST", path, payload=body)
        replay_status, _, replay = self.request("POST", path, payload=body)
        conflict_status, _, conflict = self.request(
            "POST",
            path,
            payload={**body, "outcome": "DENIED"},
        )
        self.assertEqual((first_status, replay_status, conflict_status), (200, 200, 409))
        self.assertEqual(cast(dict[str, object], first["data"])["status"], "RECORDED")
        self.assertEqual(cast(dict[str, object], replay["data"])["status"], "EXACT_REPLAY")
        self.assertEqual(
            cast(dict[str, object], cast(dict[str, object], conflict)["error"])["code"],
            "IDEMPOTENCY_KEY_MATERIAL_CONFLICT",
        )
        detail_status, detail, _ = self.request("GET", f"/sales-credit/{order.order_id}")
        self.assertEqual(detail_status, 200, detail.decode(errors="replace"))
        self.assertIn(b"APPROVED", detail)
        self.assertIn(b"Prior outcomes remain", detail)
        self.assertNotIn(str(self.data_root).encode(), detail)
        with self.application.database.read() as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM sc_manager_outcomes WHERE order_id=?",
                (order.order_id,),
            ).fetchone()[0]
        self.assertEqual(count, 1)

        stale_status, _, stale = self.request(
            "POST", path, payload={**body, "outcome": "DENIED", "request_key": "new-after-close"},
        )
        self.assertEqual(stale_status, 409, stale)
        self.assertEqual(stale["error"]["code"], "MANAGER_OUTCOME_CASE_INVALID")

    def test_all_five_manager_outcomes_keep_exact_money_and_system_classification(self) -> None:
        for outcome in ("APPROVED", "DENIED", "PARTIAL", "OTHER_REP", "NOT_PURSUED"):
            with self.subTest(outcome=outcome):
                order = self.application.instantiate("sales-credit-human-review", outcome)
                self.application.evaluate(order.order_id, "evaluate-" + outcome)
                body = {
                    "actor_id": "SYN-REP-M7-HTTP-MANAGER", "confirmed": True,
                    "outcome": outcome, "request_key": "manager-" + outcome,
                    "decided_at": self.action_time(),
                    "amount_minor_units": 1250 if outcome == "PARTIAL" else None,
                    "currency_code": "USD" if outcome == "PARTIAL" else None,
                    "request_schema_version": API_REQUEST_SCHEMA_VERSION,
                    "schema_version": MANAGER_OUTCOME_REQUEST_SCHEMA_VERSION,
                }
                path = f"/api/v1/dashboard/sales-credit/{order.order_id}/manager-outcome"
                status, _, result = self.request("POST", path, payload=body)
                self.assertEqual(status, 200, result)
                status, _, replay = self.request("POST", path, payload=body)
                self.assertEqual(status, 200, replay)
                self.assertEqual(replay["data"]["status"], "EXACT_REPLAY")
                detail = self.server.control_center.sales_credit_detail(order.order_id)
                self.assertEqual(detail["summary"]["attribution"], "UNKNOWN")
                self.assertEqual(detail["summary"]["manager_outcome"], outcome)

    def test_doi_selection_success_replay_conflict_and_timeline(self) -> None:
        order = self.application.instantiate("doi-overlap", "m7-http-doi-instance")
        evaluated = self.application.evaluate(order.order_id, "m7-http-doi-evaluation")
        assert evaluated.case_id is not None
        assert evaluated.evaluation_id is not None
        case_id = str(evaluated.case_id)
        detail = self.server.control_center.doi_detail(case_id)
        opportunities = cast(list[dict[str, object]], detail["opportunities"])
        option_ids = tuple(sorted(str(item["opportunity_id"]) for item in opportunities))
        selected = next(
            str(item["opportunity_id"])
            for item in opportunities
            if item["opportunity_type"] == "EXACT_SKU_RECHECK"
        )
        body = {
            "actor_id": "SYN-REP-M7-HTTP-DOI-MANAGER",
            "confirmed": True,
            "evaluation_id": str(evaluated.evaluation_id),
            "occurred_at": self.action_time(),
            "option_opportunity_ids": list(option_ids),
            "request_key": "M7-HTTP-DOI-SELECTION",
            "request_schema_version": API_REQUEST_SCHEMA_VERSION,
            "schema_version": DOI_SCENARIO_SELECTION_REQUEST_SCHEMA_VERSION,
            "selected_opportunity_id": selected,
        }
        path = f"/api/v1/dashboard/doi/{case_id}/scenario-selection"
        first_status, _, first = self.request("POST", path, payload=body)
        replay_status, _, replay = self.request("POST", path, payload=body)
        other = next(value for value in option_ids if value != selected)
        conflict_status, _, conflict = self.request(
            "POST",
            path,
            payload={**body, "selected_opportunity_id": other},
        )
        self.assertEqual((first_status, replay_status, conflict_status), (200, 200, 409))
        self.assertEqual(cast(dict[str, object], first["data"])["status"], "RECORDED")
        self.assertEqual(cast(dict[str, object], replay["data"])["status"], "EXACT_REPLAY")
        self.assertIn(
            cast(dict[str, object], cast(dict[str, object], conflict)["error"])["code"],
            {"IDEMPOTENCY_KEY_MATERIAL_CONFLICT", "REQUEST_CONFLICT"},
        )
        detail_status, detail_html, _ = self.request("GET", f"/doi/{case_id}")
        self.assertEqual(detail_status, 200, detail_html.decode(errors="replace"))
        self.assertIn(b"SELECTED", detail_html)
        self.assertIn(b"ACTION_CONTEXT", detail_html)
        self.assertIn(b"HUMAN_FACT", detail_html)
        self.assertNotIn(str(self.data_root).encode(), detail_html)
        api_status, api_raw, api_detail = self.request(
            "GET",
            f"/api/v1/dashboard/doi/{case_id}",
        )
        self.assertEqual(api_status, 200, api_raw.decode(errors="replace"))
        api_data = cast(dict[str, object], cast(dict[str, object], api_detail)["data"])
        self.assertEqual(api_data["schema_version"], "synthetic-sales-assist-control-center/v1")
        self.assertIsNotNone(api_data["scenario_selection"])
        self.assertNotIn(str(self.data_root), json.dumps(api_data, sort_keys=True))
        with self.application.database.read() as connection:
            counts = (
                connection.execute(
                    "SELECT COUNT(*) FROM doi_evaluations WHERE case_id=?",
                    (case_id,),
                ).fetchone()[0],
                connection.execute(
                    "SELECT COUNT(*) FROM doi_owner_events e "
                    "JOIN doi_owner_streams s ON s.stream_family=e.stream_family "
                    "AND s.stream_id=e.stream_id WHERE s.case_id=?",
                    (case_id,),
                ).fetchone()[0],
            )
        self.assertEqual(counts, (2, 2))
        for retained in (False, True):
            if retained:
                reopened = ScenarioApplication.open(self.data_root)
                self.server.control_center = ControlCenterApplication(
                    reopened.database, scenario_application=reopened,
                )
            metrics = self.server.control_center.metrics()
            self.assertEqual(metrics.unique_evaluations, 2)
            self.assertEqual(metrics.requests_received, 1)
            for route in (
                "/overview", "/system/telemetry", "/api/v1/dashboard/overview",
                "/api/v1/dashboard/system/telemetry",
            ):
                with self.subTest(route=route, reopened=retained):
                    status, raw, _ = self.request("GET", route)
                    self.assertEqual(status, 200, raw.decode(errors="replace"))

    def test_detail_and_audit_routes_reject_valid_but_wrong_synthetic_subjects(
        self,
    ) -> None:
        first_sc = self.application.instantiate(
            "sales-credit-human-review",
            "m7-route-binding-sc-first",
        )
        second_sc = self.application.instantiate(
            "sales-credit-human-review",
            "m7-route-binding-sc-second",
        )
        self.application.evaluate(first_sc.order_id, "m7-route-binding-sc-eval-first")
        self.application.evaluate(second_sc.order_id, "m7-route-binding-sc-eval-second")
        control_center = cast(Any, self.server.control_center)
        original_sc = control_center.sales_credit_detail
        wrong_sc = original_sc(second_sc.order_id)
        control_center.sales_credit_detail = lambda _order_id: wrong_sc
        status, _, payload = self.request(
            "GET",
            f"/api/v1/dashboard/sales-credit/{first_sc.order_id}",
        )
        self.assertEqual(status, 500)
        error = cast(dict[str, object], cast(dict[str, object], payload)["error"])
        self.assertEqual(error["code"], "DASHBOARD_ROUTE_SUBJECT_MISMATCH")
        status, raw, _ = self.request("GET", f"/sales-credit/{first_sc.order_id}")
        self.assertEqual(status, 500)
        self.assertIn(b"DASHBOARD_ROUTE_SUBJECT_MISMATCH", raw)
        control_center.sales_credit_detail = original_sc

        first_doi = self.application.instantiate(
            "doi-overlap",
            "m7-route-binding-doi-first",
        )
        second_doi = self.application.instantiate(
            "doi-overlap",
            "m7-route-binding-doi-second",
        )
        first_result = self.application.evaluate(
            first_doi.order_id,
            "m7-route-binding-doi-eval-first",
        )
        second_result = self.application.evaluate(
            second_doi.order_id,
            "m7-route-binding-doi-eval-second",
        )
        assert first_result.case_id is not None
        assert second_result.case_id is not None
        first_case_id = str(first_result.case_id)
        second_case_id = str(second_result.case_id)
        original_doi = control_center.doi_detail
        wrong_doi = original_doi(second_case_id)
        control_center.doi_detail = lambda _case_id: wrong_doi
        status, _, payload = self.request(
            "GET",
            f"/api/v1/dashboard/doi/{first_case_id}",
        )
        self.assertEqual(status, 500)
        error = cast(dict[str, object], cast(dict[str, object], payload)["error"])
        self.assertEqual(error["code"], "DASHBOARD_ROUTE_SUBJECT_MISMATCH")
        control_center.doi_detail = original_doi

        original_audit = control_center.audit_view
        wrong_audit = original_audit("SALES_CREDIT_CASE", second_sc.order_id)
        control_center.audit_view = lambda _kind, _subject_id: wrong_audit
        status, _, payload = self.request(
            "GET",
            "/api/v1/dashboard/audit/sales-credit-case/"
            f"{first_sc.order_id}",
        )
        self.assertEqual(status, 500)
        error = cast(dict[str, object], cast(dict[str, object], payload)["error"])
        self.assertEqual(error["code"], "DASHBOARD_ROUTE_SUBJECT_MISMATCH")


if __name__ == "__main__":
    unittest.main()
