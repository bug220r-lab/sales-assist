from __future__ import annotations

import http.client
import json
import threading
import unittest
from copy import deepcopy
from html.parser import HTMLParser
from unittest.mock import patch

from synthetic_sales_assist.application import ordered_line_manifest_digest_from_mappings
from synthetic_sales_assist.portal.contracts import (
    API_REQUEST_SCHEMA_VERSION,
    API_SCHEMA_VERSION,
    DOM_SCHEMA_VERSION,
    PortalContractError,
    validate_evaluation_response,
    validate_line_mapping,
    validate_order_detail_response,
    validate_shutdown_response,
)
from synthetic_sales_assist.portal.rendering import order_source_payload
from synthetic_sales_assist.portal.server import PortalHTTPServer, PortalServerConfig


CSRF = "a" * 64
SHUTDOWN = "b" * 64
ORDER_ID = "SYN-ORDER-PORTAL-0001"
INTERACTION_ID = "SYN-INTERACTION-PORTAL-0001"
RUN_ID = "SYN-RUN-PORTAL-0001"
OTHER_ORDER_ID = "SYN-ORDER-PORTAL-0002"
OTHER_INTERACTION_ID = "SYN-INTERACTION-PORTAL-0002"
OTHER_RUN_ID = "SYN-RUN-PORTAL-0002"
OTHER_LINE_ID = "SYN-EVIDENCE-PORTAL-LINE-0002"
APPLICATION_SCHEMA = "synthetic-sales-assist-application/v1"


def _fact(value: object, *, tag: str = "KNOWN", reason: str | None = None) -> dict[str, object]:
    return {"reason_code": reason, "tag": tag, "value": value}


def _evaluation(*, replayed: bool = False) -> dict[str, object]:
    return {
        "aggregate_potential_status": "UNAVAILABLE",
        "aggregate_potential_value": None,
        "case_id": "SYN-EVIDENCE-PORTAL-CASE-0001",
        "closure_state": None,
        "command_id": "SYN-EVIDENCE-PORTAL-COMMAND-0001",
        "conflict": False,
        "evaluation_id": "SYN-EVALUATION-PORTAL-0001",
        "explanation": {
            "normalized_facts": ["ORDER_ID"],
            "precedence_decision": "DOI_OPPORTUNITY",
            "reason_ownership": ["RC-087:TR-034"],
            "rules_evaluated": ["TR-034"],
            "supplied_facts": ["ORDER_ID", "LINES"],
            "unavailable_facts": ["AGGREGATE_POTENTIAL"],
        },
        "fired_rules": ["TR-034"],
        "handling_flags": ["HUMAN_SCENARIO_SELECTION_REQUIRED"],
        "human_review_required": True,
        "opportunities": [
            {
                "line_ids": ["SYN-EVIDENCE-PORTAL-LINE-0001"],
                "opportunity_type": "FULFILLMENT_SPLIT",
                "potential_value": None,
            },
            {
                "line_ids": ["SYN-EVIDENCE-PORTAL-LINE-0001"],
                "opportunity_type": "EXACT_SKU",
                "potential_value": None,
            },
        ],
        "order_id": ORDER_ID,
        "processing_duration_ns": 1500,
        "processing_stages": [
            {"duration_ns": 1000, "stage": "RULE_EVALUATION", "status": "SUCCEEDED"},
            {"duration_ns": 500, "stage": "PERSISTENCE", "status": "SUCCEEDED"},
        ],
        "reasons": ["RC-087"],
        "replayed": replayed,
        "rule_pack": "DOI",
        "rule_pack_version": "synthetic-doi-rule-pack/v1",
        "run_id": RUN_ID,
        "scenario_alias": "doi-overlap",
        "schema_version": APPLICATION_SCHEMA,
        "snapshot_id": "SYN-SNAPSHOT-PORTAL-0001",
        "top_level_result": "DOI_OPPORTUNITY",
        "value": None,
        "value_status": "UNAVAILABLE",
        "workflow_state": "DOI_OPPORTUNITY",
    }


def _line() -> dict[str, object]:
    return {
        "activity": _fact("ACTIVE"),
        "availability": _fact("IN_STOCK"),
        "drop_ship_state": _fact("NON_DS"),
        "eta": _fact("2026-08-22T12:00:00Z"),
        "line_id": "SYN-EVIDENCE-PORTAL-LINE-0001",
        "line_index": 1,
        "line_value": _fact(
            {
                "amount": "10.00",
                "currency_code": "USD",
                "currency_registry_version": "synthetic-iso-style-currency-registry/v1",
                "currency_scale": 2,
            }
        ),
        "product_id": "SYN-SKU-PORTAL-0001",
        "quantity": _fact("1"),
    }


def _order(*, description_mode: str = "complete") -> dict[str, object]:
    lines = [_line()]
    return {
        "completeness": {
            "declared_relevant_line_count": 1,
            "fixture_version": "shared-fixture/v1",
            "observed_order_id": ORDER_ID,
            "ordered_line_manifest_digest": ordered_line_manifest_digest_from_mappings(
                lines
            ),
            "rendered_relevant_line_count": 1,
            "requested_order_id": ORDER_ID,
            "source_observed_at": "2026-08-21T12:00:00Z",
            "source_schema_version": "shared-whole-order-completeness/v1",
            "state": "COMPLETE",
        },
        "created_at": "2026-08-21T12:00:00Z",
        "doi_state": "DOI_OPPORTUNITY",
        "evaluated": True,
        "human_review_required": True,
        "interaction_ids": [INTERACTION_ID],
        "latest_evaluation": _evaluation(),
        "lines": lines,
        "mode": description_mode,
        "order_id": ORDER_ID,
        "order_status": "ACTIVE",
        "relevant_line_count": 1,
        "rule_pack": "DOI",
        "sales_credit_state": None,
        "scenario_alias": "doi-overlap",
        "schema_version": APPLICATION_SCHEMA,
        "source_status": "COMPLETE",
        "updated_at": "2026-08-21T12:00:01Z",
    }


def _rebind_order(
    *,
    order_id: str = OTHER_ORDER_ID,
    scenario_alias: str = "doi-overlap",
) -> dict[str, object]:
    order = deepcopy(_order())
    order["order_id"] = order_id
    order["scenario_alias"] = scenario_alias
    completeness = order["completeness"]
    evaluation = order["latest_evaluation"]
    assert type(completeness) is dict and type(evaluation) is dict
    completeness["observed_order_id"] = order_id
    completeness["requested_order_id"] = order_id
    evaluation["order_id"] = order_id
    evaluation["scenario_alias"] = scenario_alias
    return order


def _summary() -> dict[str, object]:
    order = _order()
    return {
        key: order[key]
        for key in (
            "doi_state",
            "evaluated",
            "human_review_required",
            "mode",
            "order_id",
            "order_status",
            "relevant_line_count",
            "rule_pack",
            "sales_credit_state",
            "scenario_alias",
            "schema_version",
            "updated_at",
        )
    }


def _history() -> dict[str, object]:
    return {
        "artifacts": [
            {
                "artifact_id": "SYN-SNAPSHOT-PORTAL-0001",
                "artifact_type": "IMMUTABLE_SNAPSHOT",
                "occurred_at": "2026-08-21T12:00:00Z",
                "reasons": [],
                "state": "COMPLETE",
                "transition_id": None,
                "value": None,
            }
        ],
        "attention_causes": [],
        "attempt_receipts": [],
        "conflict_count": 0,
        "events": [
            {
                "evaluation_id": "SYN-EVALUATION-PORTAL-0001",
                "event_id": "SYN-EVIDENCE-PORTAL-EVENT-0001",
                "event_kind": "DOI_EVALUATION",
                "occurred_at": "2026-08-21T12:00:01Z",
                "sequence": 1,
                "state": "DOI_OPPORTUNITY",
            }
        ],
        "exact_replay_count": 0,
        "intervention_events": [],
        "manager_outcomes": [],
        "order_id": ORDER_ID,
        "receipts": [
            {
                "command_id": "SYN-EVIDENCE-PORTAL-COMMAND-0001",
                "recorded_at": "2026-08-21T12:00:01Z",
                "replayed": False,
            }
        ],
        "schema_version": APPLICATION_SCHEMA,
        "telemetry_event_count": 1,
        "value_events": [],
    }


def _status(*, healthy: bool = True) -> dict[str, object]:
    state = "PASS" if healthy else "FAIL"
    return {
        "app_version": "0.1.2",
        "build_version": "synthetic-sales-assist-m8/v1",
        "database_schema_version": 4,
        "database_status": state,
        "evaluated_count": 1,
        "expected_schema_version": 4,
        "integrity_check": "ok" if healthy else "corrupt",
        "migration_status": state,
        "projection_status": state,
        "quick_check": "ok" if healthy else "corrupt",
        "registry_capacity": 256,
        "registry_count": 1,
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
        "schema_version": APPLICATION_SCHEMA,
    }


class FakeApplicationError(RuntimeError):
    def __init__(self, code: str, category: str) -> None:
        self.code = code
        self.category = category
        super().__init__(code)


class FakeApplication:
    def __init__(self) -> None:
        self.instantiate_calls: list[tuple[str, str | None, str]] = []
        self.evaluate_calls: list[tuple[str, str | None]] = []
        self.description = "Synthetic overlap scenario"
        self.order_representation_mode = "complete"
        self.healthy = True

    def _representation_order(self, mode: str | None = None) -> dict[str, object]:
        selected = self.order_representation_mode if mode is None else mode
        order = _order(description_mode=selected)
        completeness = order["completeness"]
        assert isinstance(completeness, dict)
        incomplete = {
            "declared-rendered-mismatch",
            "dom-payload-mismatch",
            "duplicate-line",
            "identity-mismatch",
            "missing-required-section",
            "stale-source-changed",
        }
        if selected in incomplete:
            completeness["state"] = "INCOMPLETE"
            order["source_status"] = "INCOMPLETE"
        elif selected == "malformed-value":
            completeness["state"] = "MALFORMED"
            order["source_status"] = "MALFORMED"
        if selected == "observed-unknown":
            lines = order["lines"]
            assert isinstance(lines, list)
            lines[0]["availability"] = _fact(  # type: ignore[index]
                None, tag="UNKNOWN", reason="RC-016"
            )
            completeness["ordered_line_manifest_digest"] = (
                ordered_line_manifest_digest_from_mappings(lines)
            )
        elif selected == "zero-relevant-lines":
            order["lines"] = []
            order["relevant_line_count"] = 0
            order["doi_state"] = None
            order["evaluated"] = False
            order["human_review_required"] = False
            order["latest_evaluation"] = None
            completeness["declared_relevant_line_count"] = 0
            completeness["rendered_relevant_line_count"] = 0
            completeness["ordered_line_manifest_digest"] = (
                ordered_line_manifest_digest_from_mappings([])
            )
        elif selected == "large":
            template = _line()
            lines = []
            for index in range(1, 65):
                line = dict(template)
                line["line_id"] = f"SYN-EVIDENCE-PORTAL-LINE-{index:04d}"
                line["line_index"] = index
                line["product_id"] = f"SYN-SKU-PORTAL-{index:04d}"
                lines.append(line)
            order["lines"] = lines
            order["relevant_line_count"] = len(lines)
            completeness["declared_relevant_line_count"] = len(lines)
            completeness["rendered_relevant_line_count"] = len(lines)
            completeness["ordered_line_manifest_digest"] = (
                ordered_line_manifest_digest_from_mappings(lines)
            )
        if selected == "duplicate-line":
            duplicate = dict(_line())
            duplicate["line_index"] = 2
            lines = order["lines"]
            assert isinstance(lines, list)
            lines.append(duplicate)
            completeness["rendered_relevant_line_count"] = 2
            order["relevant_line_count"] = 2
        elif selected == "identity-mismatch":
            completeness["observed_order_id"] = "SYN-ORDER-PORTAL-MISMATCH"
        elif selected == "declared-rendered-mismatch":
            completeness["declared_relevant_line_count"] = 2
        return order

    def list_scenarios(self) -> list[dict[str, object]]:
        return [
            {
                "alias": "doi-overlap",
                "allowed_modes": ["complete", "malformed"],
                "collected_scenario": "OVERLAP_UNAVAILABLE_THEN_HUMAN_SELECTED",
                "complexity": "overlap",
                "description": self.description,
                "expected_result": "DOI_OPPORTUNITY",
                "rule_pack": "DOI",
                "schema_version": APPLICATION_SCHEMA,
            }
        ]

    def instantiate(
        self, alias: str, request_key: str | None = None, mode: str = "complete"
    ) -> dict[str, object]:
        self.instantiate_calls.append((alias, request_key, mode))
        return self._representation_order(mode)

    def list_orders(self) -> list[dict[str, object]]:
        return [_summary()]

    def get_order(self, order_id: str) -> dict[str, object]:
        if order_id != ORDER_ID:
            raise FakeApplicationError("ORDER_NOT_FOUND", "NOT_FOUND")
        return self._representation_order()

    def evaluate(self, order_id: str, request_key: str | None = None) -> dict[str, object]:
        self.evaluate_calls.append((order_id, request_key))
        evaluable_modes = {
            "backend-evaluation-failure",
            "complete",
            "large",
            "observed-unknown",
            "zero-relevant-lines",
        }
        if self.order_representation_mode not in evaluable_modes:
            raise FakeApplicationError(
                "SOURCE_REPRESENTATION_NOT_EVALUABLE", "UNAVAILABLE"
            )
        if self.order_representation_mode == "backend-evaluation-failure":
            raise FakeApplicationError("BACKEND_EVALUATION_FAILURE", "UNAVAILABLE")
        if request_key == "conflict":
            raise FakeApplicationError("REQUEST_KEY_CONFLICT", "CONFLICT")
        return _evaluation(replayed=request_key == "replay")

    def get_history(self, order_id: str) -> dict[str, object]:
        if order_id != ORDER_ID:
            raise FakeApplicationError("ORDER_NOT_FOUND", "NOT_FOUND")
        return _history()

    def get_interaction(self, interaction_id: str) -> dict[str, object]:
        if interaction_id != INTERACTION_ID:
            raise FakeApplicationError("INTERACTION_NOT_FOUND", "NOT_FOUND")
        return {
            "direction": "INBOUND",
            "evidence_classification": "TARGET_REP_PARTICIPATED",
            "identifier_kind": "SYNTHETIC_ORDER_NUMBER",
            "interaction_id": INTERACTION_ID,
            "order_id": ORDER_ID,
            "schema_version": APPLICATION_SCHEMA,
            "target_rep_participation": "KNOWN_PRESENT",
            "timestamp": "2026-08-21T12:00:00Z",
            "timestamp_precision": "SECOND",
        }

    def get_run(self, run_id: str) -> dict[str, object]:
        if run_id != RUN_ID:
            raise FakeApplicationError("RUN_NOT_FOUND", "NOT_FOUND")
        return {
            "completed_at": "2026-08-21T12:00:01Z",
            "event_count": 1,
            "order_id": ORDER_ID,
            "rule_pack": "DOI",
            "run_id": RUN_ID,
            "run_type": "RECHECK_ORDER",
            "schema_version": APPLICATION_SCHEMA,
            "started_at": "2026-08-21T12:00:00Z",
            "status": "COMPLETED",
        }

    def metrics_summary(self) -> dict[str, object]:
        return {
            "conflict_count": 0,
            "database_error_count": 0,
            "exact_replay_count": 0,
            "failed_closed_count": 0,
            "human_review_count": 1,
            "median_latency_ns": 1500,
            "p95_latency_ns": 1500,
            "safety_counters": _status()["safety_counters"],
            "schema_version": APPLICATION_SCHEMA,
            "success_count": 1,
            "success_rate": {"defined": True, "denominator": 1, "numerator": 1},
            "throughput_per_second": "1.000000",
            "total_processed": 1,
        }

    def system_status(self, deep: bool = False) -> dict[str, object]:
        del deep
        return _status(healthy=self.healthy)


class OrderHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.main_attributes: dict[str, str | None] = {}
        self.line_attributes: list[dict[str, str | None]] = []
        self.payload_parts: list[str] = []
        self.in_payload = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "main":
            self.main_attributes = values
        if tag == "tr" and "data-ssa-line-id" in values:
            self.line_attributes.append(values)
        if tag == "script" and values.get("id") == "ssa-synthetic-order-payload":
            self.in_payload = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self.in_payload:
            self.in_payload = False

    def handle_data(self, data: str) -> None:
        if self.in_payload:
            self.payload_parts.append(data)


class PortalHTTPTestCase(unittest.TestCase):
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
        request_headers = {} if headers is None else dict(headers)
        request_headers.setdefault("Host", f"127.0.0.1:{self.port}")
        connection.request(method, path, body=body, headers=request_headers)
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    def post_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Origin": "http" + f"://127.0.0.1:{self.port}",
            "X-SSA-CSRF-Token": CSRF,
        }

    def test_health_and_closed_get_api_routes(self) -> None:
        status, headers, raw = self.request("GET", "/health")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "application/json; charset=utf-8")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("default-src 'none'", headers["Content-Security-Policy"])
        payload = json.loads(raw)
        self.assertEqual(payload["schema_version"], API_SCHEMA_VERSION)
        self.assertEqual(payload["data"]["status"], "PASS")
        for path in (
            "/api/v1/scenarios",
            "/api/v1/orders",
            f"/api/v1/orders/{ORDER_ID}",
            f"/api/v1/orders/{ORDER_ID}/history",
            f"/api/v1/interactions/{INTERACTION_ID}",
            f"/api/v1/runs/{RUN_ID}",
            "/api/v1/metrics/summary",
            "/api/v1/system/status",
        ):
            with self.subTest(path=path):
                status, _, raw = self.request("GET", path)
                self.assertEqual(status, 200)
                self.assertEqual(json.loads(raw)["schema_version"], API_SCHEMA_VERSION)
                self.assertNotIn(b"database_path", raw)

    def test_every_json_route_rejects_nonclosed_application_views_before_success(
        self,
    ) -> None:
        instantiate_body = json.dumps(
            {
                "mode": "complete",
                "request_key": "PORTAL-CLOSED-INSTANTIATE",
                "schema_version": API_REQUEST_SCHEMA_VERSION,
            },
            separators=(",", ":"),
        ).encode()
        evaluate_body = json.dumps(
            {
                "request_key": "PORTAL-CLOSED-EVALUATE",
                "schema_version": API_REQUEST_SCHEMA_VERSION,
            },
            separators=(",", ":"),
        ).encode()

        def add_member(value: object) -> object:
            changed = deepcopy(value)
            target = changed[0] if type(changed) is list else changed
            assert type(target) is dict
            target["unexpected_member"] = "PROHIBITED"
            return changed

        def wrong_member(member: str, replacement: object):
            def mutate(value: object) -> object:
                changed = deepcopy(value)
                target = changed[0] if type(changed) is list else changed
                assert type(target) is dict
                target[member] = replacement
                return changed

            return mutate

        def wrong_namespace(member: str, replacement: str):
            return wrong_member(member, replacement)

        cases = (
            (
                "health",
                "system_status",
                "GET",
                "/health",
                _status(),
                wrong_member("registry_count", "1"),
                None,
                None,
            ),
            (
                "scenarios",
                "list_scenarios",
                "GET",
                "/api/v1/scenarios",
                self.application.list_scenarios(),
                wrong_member("description", 7),
                None,
                None,
            ),
            (
                "instantiate",
                "instantiate",
                "POST",
                "/api/v1/scenarios/doi-overlap/instantiate",
                _order(),
                wrong_member("evaluated", "true"),
                wrong_namespace("order_id", RUN_ID),
                instantiate_body,
            ),
            (
                "orders",
                "list_orders",
                "GET",
                "/api/v1/orders",
                [_summary()],
                wrong_member("evaluated", "true"),
                wrong_namespace("order_id", RUN_ID),
                None,
            ),
            (
                "order-detail",
                "get_order",
                "GET",
                f"/api/v1/orders/{ORDER_ID}",
                _order(),
                wrong_member("relevant_line_count", "1"),
                wrong_namespace("order_id", RUN_ID),
                None,
            ),
            (
                "evaluate",
                "evaluate",
                "POST",
                f"/api/v1/orders/{ORDER_ID}/evaluate",
                _evaluation(),
                wrong_member("replayed", "false"),
                wrong_namespace("order_id", RUN_ID),
                evaluate_body,
            ),
            (
                "history",
                "get_history",
                "GET",
                f"/api/v1/orders/{ORDER_ID}/history",
                _history(),
                wrong_member("conflict_count", "0"),
                wrong_namespace("order_id", RUN_ID),
                None,
            ),
            (
                "interaction",
                "get_interaction",
                "GET",
                f"/api/v1/interactions/{INTERACTION_ID}",
                self.application.get_interaction(INTERACTION_ID),
                wrong_member("direction", 1),
                wrong_namespace("interaction_id", RUN_ID),
                None,
            ),
            (
                "run",
                "get_run",
                "GET",
                f"/api/v1/runs/{RUN_ID}",
                self.application.get_run(RUN_ID),
                wrong_member("event_count", "1"),
                wrong_namespace("run_id", INTERACTION_ID),
                None,
            ),
            (
                "metrics",
                "metrics_summary",
                "GET",
                "/api/v1/metrics/summary",
                self.application.metrics_summary(),
                wrong_member("total_processed", "1"),
                None,
                None,
            ),
            (
                "system-status",
                "system_status",
                "GET",
                "/api/v1/system/status",
                _status(),
                wrong_member("registry_count", "1"),
                None,
                None,
            ),
        )
        for (
            name,
            application_method,
            http_method,
            path,
            valid,
            wrong_type,
            wrong_id,
            body,
        ) in cases:
            mutations = [("extra-member", add_member), ("wrong-type", wrong_type)]
            if wrong_id is not None:
                mutations.append(("wrong-namespace", wrong_id))
            for mutation_name, mutate in mutations:
                with self.subTest(route=name, mutation=mutation_name):
                    with patch.object(
                        self.application,
                        application_method,
                        return_value=mutate(valid),
                    ):
                        status, _, raw = self.request(
                            http_method,
                            path,
                            body=body,
                            headers=(
                                self.post_headers() if http_method == "POST" else None
                            ),
                        )
                self.assertEqual(status, 500)
                self.assertEqual(json.loads(raw)["schema_version"], API_SCHEMA_VERSION)

        validate_shutdown_response({"status": "SHUTDOWN_ACCEPTED"})
        for invalid in (
            {"status": "SHUTDOWN_ACCEPTED", "unexpected_member": "PROHIBITED"},
            {"status": 202},
        ):
            with self.assertRaises(PortalContractError) as failure:
                validate_shutdown_response(invalid)
            self.assertEqual(failure.exception.status, 500)

    def test_instantiation_and_evaluation_delegate_exactly(self) -> None:
        body = json.dumps(
            {
                "mode": "complete",
                "request_key": "PORTAL-INSTANTIATE-1",
                "schema_version": API_REQUEST_SCHEMA_VERSION,
            },
            separators=(",", ":"),
        ).encode()
        status, _, raw = self.request(
            "POST",
            "/api/v1/scenarios/doi-overlap/instantiate",
            body=body,
            headers=self.post_headers(),
        )
        self.assertEqual(status, 201)
        self.assertEqual(json.loads(raw)["data"]["order_id"], ORDER_ID)
        self.assertEqual(
            self.application.instantiate_calls,
            [("doi-overlap", "PORTAL-INSTANTIATE-1", "complete")],
        )
        evaluate = json.dumps(
            {"request_key": "replay", "schema_version": API_REQUEST_SCHEMA_VERSION},
            separators=(",", ":"),
        ).encode()
        status, _, raw = self.request(
            "POST",
            f"/api/v1/orders/{ORDER_ID}/evaluate",
            body=evaluate,
            headers=self.post_headers(),
        )
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(raw)["data"]["replayed"])
        self.assertEqual(self.application.evaluate_calls, [(ORDER_ID, "replay")])

    def test_every_resource_response_is_bound_to_its_requested_route(self) -> None:
        instantiate_body = json.dumps(
            {
                "mode": "complete",
                "request_key": None,
                "schema_version": API_REQUEST_SCHEMA_VERSION,
            },
            separators=(",", ":"),
        ).encode()
        evaluate_body = json.dumps(
            {
                "request_key": None,
                "schema_version": API_REQUEST_SCHEMA_VERSION,
            },
            separators=(",", ":"),
        ).encode()
        mismatched_history = deepcopy(_history())
        mismatched_history["order_id"] = OTHER_ORDER_ID
        mismatched_interaction = self.application.get_interaction(INTERACTION_ID)
        mismatched_interaction["interaction_id"] = OTHER_INTERACTION_ID
        mismatched_run = self.application.get_run(RUN_ID)
        mismatched_run["run_id"] = OTHER_RUN_ID
        mismatched_evaluation = deepcopy(_evaluation())
        mismatched_evaluation["order_id"] = OTHER_ORDER_ID
        api_cases = (
            (
                "instantiate-alias",
                "instantiate",
                "/api/v1/scenarios/doi-overlap/instantiate",
                _rebind_order(
                    order_id=ORDER_ID,
                    scenario_alias="doi-fulfillment-split",
                ),
                instantiate_body,
            ),
            (
                "instantiate-mode",
                "instantiate",
                "/api/v1/scenarios/doi-overlap/instantiate",
                _order(description_mode="observed-unknown"),
                instantiate_body,
            ),
            (
                "order-id",
                "get_order",
                f"/api/v1/orders/{ORDER_ID}",
                _rebind_order(),
                None,
            ),
            (
                "history-order-id",
                "get_history",
                f"/api/v1/orders/{ORDER_ID}/history",
                mismatched_history,
                None,
            ),
            (
                "evaluation-order-id",
                "evaluate",
                f"/api/v1/orders/{ORDER_ID}/evaluate",
                mismatched_evaluation,
                evaluate_body,
            ),
            (
                "interaction-id",
                "get_interaction",
                f"/api/v1/interactions/{INTERACTION_ID}",
                mismatched_interaction,
                None,
            ),
            (
                "run-id",
                "get_run",
                f"/api/v1/runs/{RUN_ID}",
                mismatched_run,
                None,
            ),
        )
        for name, method_name, path, response, body in api_cases:
            with self.subTest(route=name):
                with patch.object(
                    self.application,
                    method_name,
                    return_value=response,
                ):
                    method = "POST" if body is not None else "GET"
                    status, _, raw = self.request(
                        method,
                        path,
                        body=body,
                        headers=self.post_headers() if body is not None else None,
                    )
                self.assertEqual(status, 500)
                self.assertIn("error", json.loads(raw))

        html_cases = (
            ("get_order", f"/orders/{ORDER_ID}", _rebind_order()),
            ("get_history", f"/orders/{ORDER_ID}", mismatched_history),
            (
                "get_interaction",
                f"/interactions/{INTERACTION_ID}",
                mismatched_interaction,
            ),
            ("get_run", f"/runs/{RUN_ID}", mismatched_run),
        )
        for method_name, path, response in html_cases:
            with self.subTest(html_path=path, source=method_name):
                with patch.object(
                    self.application,
                    method_name,
                    return_value=response,
                ):
                    status, _, raw = self.request("GET", path)
                self.assertEqual(status, 500)
                self.assertNotIn(b'data-ssa-action="evaluate"', raw)

    def test_evaluation_case_and_opportunity_scope_are_context_bound(self) -> None:
        validate_evaluation_response(_evaluation())
        wrong_doi_case = deepcopy(_evaluation())
        wrong_doi_case["case_id"] = ORDER_ID
        with self.assertRaises(PortalContractError):
            validate_evaluation_response(wrong_doi_case)

        sales_credit = deepcopy(_evaluation())
        sales_credit["rule_pack"] = "SALES_CREDIT"
        sales_credit["case_id"] = ORDER_ID
        validate_evaluation_response(sales_credit)
        sales_credit["case_id"] = OTHER_ORDER_ID
        with self.assertRaises(PortalContractError):
            validate_evaluation_response(sales_credit)

        wrong_line = deepcopy(_evaluation())
        opportunities = wrong_line["opportunities"]
        assert type(opportunities) is list and type(opportunities[0]) is dict
        opportunities[0]["line_ids"] = [OTHER_LINE_ID]
        body = json.dumps(
            {
                "request_key": None,
                "schema_version": API_REQUEST_SCHEMA_VERSION,
            },
            separators=(",", ":"),
        ).encode()
        with patch.object(
            self.application,
            "evaluate",
            return_value=wrong_line,
        ):
            status, _, raw = self.request(
                "POST",
                f"/api/v1/orders/{ORDER_ID}/evaluate",
                body=body,
                headers=self.post_headers(),
            )
        self.assertEqual(status, 500)
        self.assertEqual(
            json.loads(raw)["error"]["code"],
            "RESPONSE_OPPORTUNITY_LINE_SCOPE_INVALID",
        )

    def test_complete_payload_and_manifest_known_answer_are_exact(self) -> None:
        status, _, raw = self.request("GET", f"/orders/{ORDER_ID}")
        self.assertEqual(status, 200)
        parser = OrderHTMLParser()
        parser.feed(raw.decode("utf-8"))
        self.assertEqual(parser.main_attributes["data-ssa-page-kind"], "order-detail")
        self.assertEqual(parser.main_attributes["data-ssa-schema-version"], DOM_SCHEMA_VERSION)
        self.assertEqual(parser.main_attributes["data-ssa-order-id"], ORDER_ID)
        self.assertEqual(parser.main_attributes["data-ssa-completeness"], "COMPLETE")
        self.assertEqual(
            parser.main_attributes["data-ssa-manifest-digest"],
            "6cd6f84917dcddcd376f9c835a2087f0a94390aca6939174c78c343c229c454f",
        )
        self.assertEqual(
            parser.line_attributes,
            [{"data-ssa-line-id": "SYN-EVIDENCE-PORTAL-LINE-0001", "data-ssa-line-index": "1"}],
        )
        embedded = json.loads("".join(parser.payload_parts))
        self.assertEqual(embedded, order_source_payload(_order()))
        self.assertNotIn("latest_evaluation", embedded)
        self.assertNotIn("interaction_ids", embedded)
        self.assertNotIn("request_key", embedded)
        self.assertNotIn(b"&lt;script", raw)
        self.assertIn(b"Local service status", raw)
        self.assertIn(b"synthetic-sales-assist-m8/v1", raw)
        self.assertIn(b"Processing stages", raw)

    def test_line_fact_policy_rejects_cross_field_reasons_and_wrong_codecs(self) -> None:
        swaps = (
            ("activity", "RC-016"),
            ("availability", "RC-017"),
            ("drop_ship_state", "RC-115"),
            ("eta", "RC-129"),
            ("quantity", "RC-134"),
            ("line_value", "RC-125"),
        )
        for field, wrong_reason in swaps:
            with self.subTest(field=field, wrong_reason=wrong_reason):
                line = _line()
                line[field] = _fact(None, tag="UNKNOWN", reason=wrong_reason)
                with self.assertRaises(PortalContractError):
                    validate_line_mapping(line)
        for field, wrong_value in (
            ("quantity", 1),
            ("line_value", "10.00 USD"),
            ("eta", "2026-08-22 12:00:00"),
            ("availability", "ARBITRARY"),
        ):
            with self.subTest(field=field, wrong_value=wrong_value):
                line = _line()
                line[field] = _fact(wrong_value)
                with self.assertRaises(PortalContractError):
                    validate_line_mapping(line)
        line = _line()
        line["product_id"] = "SYN-ORDER-WRONG-NAMESPACE"
        with self.assertRaises(PortalContractError):
            validate_line_mapping(line)

    def test_incomplete_structural_defects_are_typed_but_not_complete(self) -> None:
        diagnostic = _order(description_mode="duplicate-line")
        lines = diagnostic["lines"]
        completeness = diagnostic["completeness"]
        assert type(lines) is list and type(completeness) is dict
        duplicate = deepcopy(lines[0])
        duplicate["line_index"] = 1
        lines.append(duplicate)
        diagnostic["source_status"] = "INCOMPLETE"
        diagnostic["relevant_line_count"] = 7
        completeness["state"] = "INCOMPLETE"
        completeness["declared_relevant_line_count"] = 3
        completeness["rendered_relevant_line_count"] = 9
        self.assertEqual(validate_order_detail_response(diagnostic), diagnostic)
        complete_claim = deepcopy(diagnostic)
        complete_claim["source_status"] = "COMPLETE"
        complete_completeness = complete_claim["completeness"]
        assert type(complete_completeness) is dict
        complete_completeness["state"] = "COMPLETE"
        with self.assertRaises(PortalContractError):
            validate_order_detail_response(complete_claim)

    def test_special_render_mismatch_modes_cannot_claim_complete(self) -> None:
        for mode in (
            "dom-payload-mismatch",
            "missing-required-section",
            "stale-source-changed",
        ):
            poisoned = _order(description_mode=mode)
            with self.subTest(mode=mode, boundary="validator"):
                with self.assertRaises(PortalContractError):
                    validate_order_detail_response(poisoned)
            with self.subTest(mode=mode, boundary="html"):
                with patch.object(
                    self.application,
                    "get_order",
                    return_value=poisoned,
                ):
                    status, _, raw = self.request("GET", f"/orders/{ORDER_ID}")
                self.assertEqual(status, 500)
                self.assertNotIn(b'data-ssa-action="evaluate"', raw)
                self.assertNotIn(b"ssa-synthetic-order-payload", raw)

    def test_dom_payload_mismatch_mode_is_concrete_and_fails_closed(self) -> None:
        self.application.order_representation_mode = "dom-payload-mismatch"
        status, _, raw = self.request("GET", f"/orders/{ORDER_ID}")
        self.assertEqual(status, 200)
        parser = OrderHTMLParser()
        parser.feed(raw.decode("utf-8"))
        embedded = json.loads("".join(parser.payload_parts))
        self.assertEqual(parser.main_attributes["data-ssa-completeness"], "INCOMPLETE")
        self.assertEqual(parser.line_attributes, [])
        self.assertEqual(len(embedded["lines"]), 1)
        self.assertNotIn(b'data-ssa-action="evaluate"', raw)
        status, _, raw = self.request(
            "POST",
            f"/api/v1/orders/{ORDER_ID}/evaluate",
            body=json.dumps(
                {
                    "request_key": None,
                    "schema_version": API_REQUEST_SCHEMA_VERSION,
                },
                separators=(",", ":"),
            ).encode(),
            headers=self.post_headers(),
        )
        self.assertEqual(status, 503)
        self.assertEqual(
            json.loads(raw)["error"]["code"],
            "SOURCE_REPRESENTATION_NOT_EVALUABLE",
        )

    def test_malformed_value_mode_is_fail_closed_and_not_evaluable(self) -> None:
        self.application.order_representation_mode = "malformed-value"
        status, _, raw = self.request("GET", f"/orders/{ORDER_ID}")
        self.assertEqual(status, 200)
        self.assertIn(b'MALFORMED', raw)
        self.assertNotIn(b'data-ssa-action="evaluate"', raw)
        status, _, raw = self.request(
            "POST",
            f"/api/v1/orders/{ORDER_ID}/evaluate",
            body=json.dumps(
                {
                    "request_key": None,
                    "schema_version": API_REQUEST_SCHEMA_VERSION,
                },
                separators=(",", ":"),
            ).encode(),
            headers=self.post_headers(),
        )
        self.assertEqual(status, 503)
        self.assertEqual(
            json.loads(raw)["error"]["code"],
            "SOURCE_REPRESENTATION_NOT_EVALUABLE",
        )

    def test_missing_section_and_stale_source_modes_are_actual_mismatches(self) -> None:
        self.application.order_representation_mode = "missing-required-section"
        status, _, missing = self.request("GET", f"/orders/{ORDER_ID}")
        self.assertEqual(status, 200)
        self.assertIn(b"Required source section is missing", missing)
        self.assertNotIn(b"Complete relevant line universe", missing)
        self.assertNotIn(b'data-ssa-action="evaluate"', missing)

        self.application.order_representation_mode = "stale-source-changed"
        status, _, stale = self.request("GET", f"/orders/{ORDER_ID}")
        self.assertEqual(status, 200)
        self.assertIn(b"1970-01-01T00:00:00Z", stale)
        self.assertIn(b"2026-08-21T12:00:00Z", stale)
        self.assertNotIn(b'data-ssa-action="evaluate"', stale)

    def test_all_other_completeness_modes_remain_visible_and_bounded(self) -> None:
        for mode in (
            "declared-rendered-mismatch",
            "duplicate-line",
            "identity-mismatch",
        ):
            with self.subTest(mode=mode):
                self.application.order_representation_mode = mode
                status, _, raw = self.request("GET", f"/orders/{ORDER_ID}")
                self.assertEqual(status, 200)
                self.assertIn(b"INCOMPLETE", raw)
                self.assertNotIn(b'data-ssa-action="evaluate"', raw)

    def test_large_zero_line_unknown_and_backend_failure_modes_are_distinct(self) -> None:
        self.application.order_representation_mode = "large"
        status, _, large = self.request("GET", f"/orders/{ORDER_ID}")
        self.assertEqual(status, 200)
        parser = OrderHTMLParser()
        parser.feed(large.decode("utf-8"))
        self.assertEqual(len(parser.line_attributes), 64)

        self.application.order_representation_mode = "zero-relevant-lines"
        status, _, zero = self.request("GET", f"/orders/{ORDER_ID}")
        self.assertEqual(status, 200)
        self.assertIn(b"Final line-universe marker \xc2\xb7 0 rendered line(s)", zero)

        self.application.order_representation_mode = "observed-unknown"
        status, _, unknown = self.request("GET", f"/orders/{ORDER_ID}")
        self.assertEqual(status, 200)
        self.assertIn(b"UNKNOWN \xc2\xb7 RC-016", unknown)
        self.assertIn(b'data-ssa-action="evaluate"', unknown)

        self.application.order_representation_mode = "backend-evaluation-failure"
        status, _, raw = self.request(
            "POST",
            f"/api/v1/orders/{ORDER_ID}/evaluate",
            body=json.dumps(
                {
                    "request_key": None,
                    "schema_version": API_REQUEST_SCHEMA_VERSION,
                },
                separators=(",", ":"),
            ).encode(),
            headers=self.post_headers(),
        )
        self.assertEqual(status, 503)
        self.assertEqual(json.loads(raw)["error"]["code"], "BACKEND_EVALUATION_FAILURE")

    def test_pages_escape_fictional_display_text_and_assets_are_local(self) -> None:
        self.application.description = "Synthetic <b> & fictional"
        status, _, raw = self.request("GET", "/scenarios")
        self.assertEqual(status, 200)
        self.assertIn(b"Synthetic &lt;b&gt; &amp; fictional", raw)
        self.assertNotIn(b"Synthetic <b>", raw)
        self.assertIn(b'Synthetic demo', raw)
        for path in ("/static/ssa.css", "/static/ssa.js"):
            asset_status, _, asset = self.request("GET", path)
            self.assertEqual(asset_status, 200)
            self.assertIn(b"SYNTHETIC-SALES-ASSIST-AUTHORED-M5", asset)
            self.assertNotIn(b"https://", asset)
            self.assertNotIn(b"http://", asset)
        self.assertEqual(self.request("GET", "/static/unknown.js")[0], 404)

    def test_all_html_routes_and_accessibility_landmarks_are_deterministic(self) -> None:
        expected = {
            "/scenarios": b'data-ssa-page-kind="scenarios"',
            "/orders": b'data-ssa-page-kind="orders"',
            f"/orders/{ORDER_ID}": b'data-ssa-page-kind="order-detail"',
            f"/interactions/{INTERACTION_ID}": b'data-ssa-page-kind="interaction-detail"',
            f"/runs/{RUN_ID}": b'data-ssa-page-kind="run-detail"',
        }
        for path, page_kind in expected.items():
            with self.subTest(path=path):
                status, headers, raw = self.request("GET", path)
                self.assertEqual(status, 200)
                self.assertEqual(headers["Content-Type"], "text/html; charset=utf-8")
                self.assertIn(page_kind, raw)
                self.assertIn(b'<main ', raw)
                self.assertIn(b'<nav aria-label="Primary">', raw)
                self.assertIn(b'Synthetic demo', raw)
                self.assertNotIn(b'https://', raw)
        self.assertIn(b'<table>', self.request("GET", "/orders")[2])
        scenarios = self.request("GET", "/scenarios")[2]
        self.assertIn(b'<label>Variant ', scenarios)
        self.assertIn(b'role="status"', scenarios)
        self.assertIn(b"Sales Credit", scenarios)
        self.assertIn(b">DOI</h2>", scenarios)
        interaction = self.request("GET", f"/interactions/{INTERACTION_ID}")[2]
        self.assertIn(ORDER_ID.encode(), interaction)
        self.assertIn(b"No unrestricted message body", interaction)
        css = self.request("GET", "/static/ssa.css")[2]
        self.assertIn(b":focus-visible", css)

    def test_safe_not_found_and_conflict_errors(self) -> None:
        status, _, raw = self.request("GET", "/api/v1/orders/SYN-ORDER-PORTAL-MISSING")
        self.assertEqual(status, 404)
        self.assertEqual(json.loads(raw)["error"]["code"], "ORDER_NOT_FOUND")
        body = json.dumps(
            {"request_key": "conflict", "schema_version": API_REQUEST_SCHEMA_VERSION},
            separators=(",", ":"),
        ).encode()
        status, _, raw = self.request(
            "POST",
            f"/api/v1/orders/{ORDER_ID}/evaluate",
            body=body,
            headers=self.post_headers(),
        )
        self.assertEqual(status, 409)
        self.assertEqual(json.loads(raw)["error"]["code"], "REQUEST_KEY_CONFLICT")
        self.assertNotIn(b"Traceback", raw)


if __name__ == "__main__":
    unittest.main()
