"""Milestone 6 extraction, messaging, panel, and packaging regressions."""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

from synthetic_sales_assist.application import (
    ApplicationError,
    ScenarioApplication,
    ordered_line_manifest_digest_from_mappings,
)
from synthetic_sales_assist.domain.canonical import canonical_json_bytes
from synthetic_sales_assist.portal.contracts import DOM_SCHEMA_VERSION
from synthetic_sales_assist.portal.rendering import (
    render_interaction,
    render_order_detail,
)
from tests.test_milestone5_portal import (
    CSRF,
    INTERACTION_ID,
    ORDER_ID,
    APPLICATION_SCHEMA,
    FakeApplication,
    _history,
    _status,
)


ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "chrome_extension"
ORDER_MEMBERS = frozenset(
    {
        "completeness",
        "lines",
        "mode",
        "order_id",
        "scenario_alias",
        "schema_version",
        "source_status",
    }
)
ORDER_BINDING_SCHEMA_VERSION = "synthetic-sales-assist-extension-order-binding/v1"
ORDER_BINDING_MEMBERS = frozenset({"order_id", "rule_pack", "schema_version"})
INTERACTION_MEMBERS = frozenset(
    {
        "direction",
        "evidence_classification",
        "identifier_kind",
        "interaction_id",
        "order_id",
        "schema_version",
        "target_rep_participation",
        "timestamp",
        "timestamp_precision",
    }
)
COMPLETENESS_MEMBERS = (
    "declared_relevant_line_count",
    "fixture_version",
    "observed_order_id",
    "ordered_line_manifest_digest",
    "rendered_relevant_line_count",
    "requested_order_id",
    "source_observed_at",
    "source_schema_version",
    "state",
)
LINE_MEMBERS = (
    "activity",
    "availability",
    "drop_ship_state",
    "eta",
    "line_id",
    "line_index",
    "line_value",
    "product_id",
    "quantity",
)
INTERACTION_DOM_MEMBERS = tuple(
    member for member in sorted(INTERACTION_MEMBERS) if member != "schema_version"
)


class _ContractParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.main_attributes: list[dict[str, str | None]] = []
        self.completeness_attributes: list[dict[str, str | None]] = []
        self.sections: dict[str, list[dict[str, str | None]]] = {}
        self.fields: dict[str, list[object]] = {}
        self.line_rows: list[dict[str, object]] = []
        self._active_line: dict[str, object] | None = None
        self._active_script: str | None = None
        self.scripts: dict[str, list[str]] = {}

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attributes = dict(attrs)
        if tag == "main" and "data-ssa-page-kind" in attributes:
            self.main_attributes.append(attributes)
        if (
            "data-ssa-completeness" in attributes
            and attributes.get("aria-labelledby") == "completeness-heading"
        ):
            self.completeness_attributes.append(attributes)
        section = attributes.get("data-ssa-section")
        if tag == "section" and section is not None:
            self.sections.setdefault(section, []).append(attributes)
        if tag == "tr" and "data-ssa-line-id" in attributes:
            self._active_line = {"_attributes": attributes}
            self.line_rows.append(self._active_line)
        field = attributes.get("data-ssa-field")
        if field is not None:
            raw = attributes.get("data-ssa-value")
            value: object
            try:
                value = json.loads(raw) if raw is not None else _Missing
            except json.JSONDecodeError:
                value = _Malformed
            self.fields.setdefault(field, []).append(value)
            if self._active_line is not None and field.startswith("line."):
                self._active_line[field.removeprefix("line.")] = value
        if tag == "script" and attributes.get("type") == "application/json":
            identifier = attributes.get("id")
            if identifier is not None:
                self._active_script = identifier
                self.scripts.setdefault(identifier, []).append("")

    def handle_endtag(self, tag: str) -> None:
        if tag == "tr":
            self._active_line = None
        if tag == "script":
            self._active_script = None

    def handle_data(self, data: str) -> None:
        if self._active_script is not None:
            payloads = self.scripts[self._active_script]
            payloads[-1] += data


class _MissingType:
    pass


class _MalformedType:
    pass


_Missing = _MissingType()
_Malformed = _MalformedType()


def _parse(raw: bytes | str) -> _ContractParser:
    parser = _ContractParser()
    parser.feed(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
    parser.close()
    return parser


def _one_field(parser: _ContractParser, name: str) -> object:
    values = parser.fields.get(name, [])
    if (
        len(values) != 1
        or values[0] is _Missing
        or values[0] is _Malformed
    ):
        raise ValueError("DOM_FIELD_INVALID")
    return values[0]


def _classify_order_html(raw: bytes | str) -> str:
    parser = _parse(raw)
    if len(parser.main_attributes) != 1:
        return "UNSUPPORTED_PAGE"
    root = parser.main_attributes[0]
    if (
        root.get("data-ssa-page-kind") != "order-detail"
        or root.get("data-ssa-schema-version") != DOM_SCHEMA_VERSION
    ):
        return "UNSUPPORTED_PAGE"
    if len(parser.sections.get("order-summary", [])) != 1:
        return "INCOMPLETE_PAGE"
    order_id = root.get("data-ssa-order-id")
    payloads = parser.scripts.get("ssa-synthetic-order-payload", [])
    if len(payloads) != 1:
        return "INCOMPLETE_PAGE"
    try:
        payload = json.loads(payloads[0])
    except json.JSONDecodeError:
        return "MALFORMED_PAGE"
    if (
        not isinstance(payload, dict)
        or frozenset(payload) != ORDER_MEMBERS
        or canonical_json_bytes(payload).decode("utf-8") != payloads[0]
    ):
        return "MALFORMED_PAGE"
    bindings = parser.scripts.get("ssa-extension-order-binding", [])
    if len(bindings) == 0:
        return "INCOMPLETE_PAGE"
    if len(bindings) != 1:
        return "MALFORMED_PAGE"
    try:
        binding = json.loads(bindings[0])
    except json.JSONDecodeError:
        return "MALFORMED_PAGE"
    if (
        not isinstance(binding, dict)
        or frozenset(binding) != ORDER_BINDING_MEMBERS
        or canonical_json_bytes(binding).decode("utf-8") != bindings[0]
    ):
        return "MALFORMED_PAGE"
    if binding.get("schema_version") != ORDER_BINDING_SCHEMA_VERSION:
        return "UNSUPPORTED_PAGE"
    if binding.get("rule_pack") not in {"SALES_CREDIT", "DOI"}:
        return "MALFORMED_PAGE"
    if (
        binding.get("order_id") != order_id
        or binding.get("order_id") != payload.get("order_id")
    ):
        return "DOM_PAYLOAD_MISMATCH"
    completeness = payload.get("completeness")
    lines = payload.get("lines")
    if not isinstance(completeness, dict) or not isinstance(lines, list):
        return "MALFORMED_PAGE"
    state = completeness.get("state")
    if state not in {"COMPLETE", "INCOMPLETE", "MALFORMED"}:
        return "MALFORMED_PAGE"
    if state == "COMPLETE":
        source_pair = (
            completeness.get("fixture_version"),
            completeness.get("source_schema_version"),
        )
        expected_rule_pack = {
            (
                "sales-credit-m5-fixture/v1",
                "synthetic-sales-credit-domain/v1",
            ): "SALES_CREDIT",
            (
                "shared-fixture/v1",
                "shared-whole-order-completeness/v1",
            ): "DOI",
        }.get(source_pair)
        if expected_rule_pack is None or binding.get("rule_pack") != expected_rule_pack:
            return "DOM_PAYLOAD_MISMATCH"
    if len(parser.completeness_attributes) != 1:
        return "INCOMPLETE_PAGE" if state != "COMPLETE" else "DOM_PAYLOAD_MISMATCH"
    if len(parser.sections.get("completeness", [])) != 1:
        return "INCOMPLETE_PAGE" if state != "COMPLETE" else "DOM_PAYLOAD_MISMATCH"
    if len(parser.sections.get("line-universe", [])) != 1:
        return "INCOMPLETE_PAGE" if state != "COMPLETE" else "DOM_PAYLOAD_MISMATCH"
    try:
        dom_summary = {
            member: _one_field(parser, member)
            for member in (
                "mode",
                "order_id",
                "rule_pack",
                "scenario_alias",
                "source_status",
            )
        }
        dom_completeness = {
            member: _one_field(parser, f"completeness.{member}")
            for member in COMPLETENESS_MEMBERS
        }
    except ValueError:
        return "INCOMPLETE_PAGE" if state != "COMPLETE" else "DOM_PAYLOAD_MISMATCH"
    expected_summary = {
        member: payload[member]
        for member in ("mode", "order_id", "scenario_alias", "source_status")
    }
    expected_summary["rule_pack"] = binding["rule_pack"]
    if dom_summary != expected_summary or dom_completeness != completeness:
        return "DOM_PAYLOAD_MISMATCH"
    marker = parser.fields.get("line-universe-end", [])
    if len(marker) != 1:
        return "INCOMPLETE_PAGE" if state != "COMPLETE" else "DOM_PAYLOAD_MISMATCH"
    dom_lines = []
    for row in parser.line_rows:
        attributes = row.get("_attributes")
        if not isinstance(attributes, dict):
            return "DOM_PAYLOAD_MISMATCH"
        try:
            line = {member: row[member] for member in LINE_MEMBERS}
        except KeyError:
            return "DOM_PAYLOAD_MISMATCH"
        if (
            attributes.get("data-ssa-line-id") != line["line_id"]
            or attributes.get("data-ssa-line-index") != str(line["line_index"])
        ):
            return "DOM_PAYLOAD_MISMATCH"
        dom_lines.append(line)
    if marker[0] != len(dom_lines) or dom_lines != lines:
        return "DOM_PAYLOAD_MISMATCH"
    if state == "MALFORMED":
        return "MALFORMED_PAGE"
    if state != "COMPLETE":
        return "INCOMPLETE_PAGE"
    line_ids = [line.get("line_id") for line in lines]
    coherent = (
        order_id == payload.get("order_id")
        and completeness.get("requested_order_id") == order_id
        and completeness.get("observed_order_id") == order_id
        and completeness.get("declared_relevant_line_count") == len(lines)
        and completeness.get("rendered_relevant_line_count") == len(lines)
        and completeness.get("source_observed_at") is not None
        and len(set(line_ids)) == len(line_ids)
        and all(line.get("line_index") == index for index, line in enumerate(lines, 1))
    )
    if not coherent:
        return "DOM_PAYLOAD_MISMATCH"
    try:
        digest = ordered_line_manifest_digest_from_mappings(lines)
    except (TypeError, ValueError):
        return "MALFORMED_PAGE"
    if completeness.get("ordered_line_manifest_digest") != digest:
        return "DOM_PAYLOAD_MISMATCH"
    return "SUPPORTED_READY"


def _render_mode(mode: str) -> bytes:
    application = FakeApplication()
    return render_order_detail(
        application._representation_order(mode),
        _history(),
        _status(),
        CSRF,
    )


class Milestone6ExtractionContractTests(unittest.TestCase):
    def test_normal_large_zero_and_observed_unknown_orders_are_ready(self) -> None:
        for mode in ("complete", "large", "zero-relevant-lines", "observed-unknown"):
            with self.subTest(mode=mode):
                self.assertEqual(_classify_order_html(_render_mode(mode)), "SUPPORTED_READY")

    def test_every_m5_incomplete_or_malformed_mode_fails_closed(self) -> None:
        expected = {
            "declared-rendered-mismatch": "INCOMPLETE_PAGE",
            "dom-payload-mismatch": "DOM_PAYLOAD_MISMATCH",
            "duplicate-line": "INCOMPLETE_PAGE",
            "identity-mismatch": "INCOMPLETE_PAGE",
            "malformed-value": "MALFORMED_PAGE",
            "missing-required-section": "INCOMPLETE_PAGE",
            "stale-source-changed": "DOM_PAYLOAD_MISMATCH",
        }
        for mode, state in expected.items():
            with self.subTest(mode=mode):
                self.assertEqual(_classify_order_html(_render_mode(mode)), state)

    def test_complete_dom_payload_and_contract_version_drift_fail_closed(self) -> None:
        complete = _render_mode("complete").decode("utf-8")
        changed_fact = complete.replace(
            'data-ssa-value="&quot;complete&quot;"',
            'data-ssa-value="&quot;large&quot;"',
            1,
        )
        self.assertEqual(_classify_order_html(changed_fact), "DOM_PAYLOAD_MISMATCH")
        wrong_version = complete.replace(DOM_SCHEMA_VERSION, "unsupported-dom/v9", 1)
        self.assertEqual(_classify_order_html(wrong_version), "UNSUPPORTED_PAGE")
        unsupported = complete.replace('data-ssa-page-kind="order-detail"', '')
        self.assertEqual(_classify_order_html(unsupported), "UNSUPPORTED_PAGE")

    def test_m5_payload_and_extension_binding_are_separate_canonical_contracts(
        self,
    ) -> None:
        parser = _parse(_render_mode("complete"))
        payloads = parser.scripts["ssa-synthetic-order-payload"]
        bindings = parser.scripts["ssa-extension-order-binding"]
        self.assertEqual(len(payloads), 1)
        self.assertEqual(len(bindings), 1)
        payload = json.loads(payloads[0])
        binding = json.loads(bindings[0])
        self.assertEqual(frozenset(payload), ORDER_MEMBERS)
        self.assertNotIn("rule_pack", payload)
        self.assertEqual(frozenset(binding), ORDER_BINDING_MEMBERS)
        self.assertEqual(binding["schema_version"], ORDER_BINDING_SCHEMA_VERSION)
        self.assertEqual(binding["order_id"], payload["order_id"])
        self.assertIn(binding["rule_pack"], {"SALES_CREDIT", "DOI"})
        self.assertEqual(
            canonical_json_bytes(payload).decode("utf-8"),
            payloads[0],
        )
        self.assertEqual(
            canonical_json_bytes(binding).decode("utf-8"),
            bindings[0],
        )

    def test_extension_order_binding_drift_fails_closed(self) -> None:
        complete = _render_mode("complete").decode("utf-8")
        parser = _parse(complete)
        binding_text = parser.scripts["ssa-extension-order-binding"][0]
        binding = json.loads(binding_text)
        tag = (
            '<script type="application/json" id="ssa-extension-order-binding">'
            f"{binding_text}</script>"
        )
        self.assertEqual(
            _classify_order_html(complete.replace(tag, "", 1)),
            "INCOMPLETE_PAGE",
        )
        with_unknown = {**binding, "unrestricted_notes": "forbidden"}
        self.assertEqual(
            _classify_order_html(
                complete.replace(
                    binding_text,
                    canonical_json_bytes(with_unknown).decode("utf-8"),
                    1,
                )
            ),
            "MALFORMED_PAGE",
        )
        wrong_version = {**binding, "schema_version": "unsupported-binding/v9"}
        self.assertEqual(
            _classify_order_html(
                complete.replace(
                    binding_text,
                    canonical_json_bytes(wrong_version).decode("utf-8"),
                    1,
                )
            ),
            "UNSUPPORTED_PAGE",
        )
        wrong_order = {**binding, "order_id": "SYN-ORDER-BINDING-MISMATCH"}
        self.assertEqual(
            _classify_order_html(
                complete.replace(
                    binding_text,
                    canonical_json_bytes(wrong_order).decode("utf-8"),
                    1,
                )
            ),
            "DOM_PAYLOAD_MISMATCH",
        )
        other_pack = (
            "DOI" if binding["rule_pack"] == "SALES_CREDIT" else "SALES_CREDIT"
        )
        wrong_pack = {**binding, "rule_pack": other_pack}
        self.assertEqual(
            _classify_order_html(
                complete.replace(
                    binding_text,
                    canonical_json_bytes(wrong_pack).decode("utf-8"),
                    1,
                )
            ),
            "DOM_PAYLOAD_MISMATCH",
        )

    def test_interaction_dom_has_exact_canonical_allowlisted_payload(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="synthetic-sales-assist-m6-interaction-"
        ) as directory:
            application = ScenarioApplication.open(Path(directory) / "data")
            detail = application.instantiate(
                "sales-credit-human-review", "interaction-dom"
            )
            interaction = application.get_interaction(detail.interaction_ids[0]).to_dict()
        rendered = render_interaction(interaction, CSRF)
        parser = _parse(rendered)
        self.assertEqual(len(parser.main_attributes), 1)
        root = parser.main_attributes[0]
        self.assertEqual(root["data-ssa-page-kind"], "interaction-detail")
        self.assertEqual(root["data-ssa-schema-version"], DOM_SCHEMA_VERSION)
        self.assertEqual(root["data-ssa-interaction-id"], interaction["interaction_id"])
        self.assertEqual(root["data-ssa-order-id"], interaction["order_id"])
        self.assertEqual(len(parser.sections.get("interaction-summary", [])), 1)
        payloads = parser.scripts["ssa-synthetic-interaction-payload"]
        self.assertEqual(payloads, [canonical_json_bytes(interaction).decode("utf-8")])
        self.assertEqual(frozenset(json.loads(payloads[0])), INTERACTION_MEMBERS)
        for member in INTERACTION_DOM_MEMBERS:
            self.assertEqual(
                _one_field(parser, f"interaction.{member}"),
                interaction[member],
            )
        self.assertNotIn("interaction.schema_version", parser.fields)
        self.assertEqual(interaction["identifier_kind"], "EMAIL")
        self.assertEqual(interaction["evidence_classification"], "SYNTHETIC_SOURCE_INTERACTION")
        self.assertIn(
            interaction["timestamp_precision"],
            {"EXACT", "CORRECTED", "REVISION_DERIVED", "HISTORICAL_APPROXIMATION"},
        )


class Milestone6StaticExtensionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = json.loads((EXTENSION / "manifest.json").read_text("utf-8"))

    def test_manifest_permission_and_static_page_inventory_is_exact(self) -> None:
        self.assertEqual(self.manifest["manifest_version"], 3)
        self.assertEqual(self.manifest["version"], "0.1.2")
        self.assertEqual(self.manifest["permissions"], ["sidePanel"])
        self.assertEqual(
            self.manifest["host_permissions"],
            ["http://127.0.0.1/*", "http://localhost/*"],
        )
        scripts = self.manifest["content_scripts"]
        self.assertEqual(len(scripts), 1)
        self.assertEqual(
            set(scripts[0]["matches"]),
            {
                "http://127.0.0.1/orders/*",
                "http://127.0.0.1/interactions/*",
                "http://localhost/orders/*",
                "http://localhost/interactions/*",
            },
        )
        self.assertEqual(scripts[0]["world"], "ISOLATED")
        self.assertEqual(scripts[0]["run_at"], "document_idle")
        self.assertNotIn("optional_permissions", self.manifest)
        self.assertNotIn("optional_host_permissions", self.manifest)

    def test_panel_state_and_extraction_allowlist_vocabulary_is_closed(self) -> None:
        contracts = (EXTENSION / "shared" / "contracts.js").read_text("utf-8")
        states = {
            "UNSUPPORTED_PAGE",
            "SUPPORTED_READY",
            "INCOMPLETE_PAGE",
            "MALFORMED_PAGE",
            "DOM_PAYLOAD_MISMATCH",
            "BACKEND_OFFLINE",
            "BACKEND_UNHEALTHY",
            "EVALUATING",
            "SALES_CREDIT_RESULT",
            "DOI_OPPORTUNITY",
            "DOI_MANUAL_REVIEW",
            "DOI_EXCLUDED",
            "DOI_MONITOR",
            "EXACT_REPLAY",
            "REQUEST_CONFLICT",
            "SAFE_ERROR",
        }
        state_match = re.search(
            r"const PANEL_STATES = Object\.freeze\(\[(.*?)\]\);",
            contracts,
            re.DOTALL,
        )
        self.assertIsNotNone(state_match)
        assert state_match is not None
        self.assertEqual(set(json.loads(f"[{state_match.group(1)}]")), states)
        for member in ORDER_MEMBERS | ORDER_BINDING_MEMBERS | INTERACTION_MEMBERS:
            self.assertIn(f'"{member}"', contracts)
        self.assertIn("synthetic-sales-assist-extension-extraction/v1", contracts)
        self.assertIn("synthetic-sales-assist-extension-message/v1", contracts)
        self.assertIn(ORDER_BINDING_SCHEMA_VERSION, contracts)

    def test_runtime_has_no_remote_code_storage_or_generic_page_action(self) -> None:
        runtime_paths = sorted(
            path
            for path in EXTENSION.rglob("*")
            if path.is_file() and path.suffix in {".css", ".html", ".js", ".json"}
        )
        text = "\n".join(path.read_text("utf-8") for path in runtime_paths)
        forbidden_patterns = (
            r"https://",
            r"wss?://",
            r"file://",
            r"\beval\s*\(",
            r"\bFunction\s*\(",
            r"document\.cookie",
            r"localStorage",
            r"sessionStorage",
            r"innerHTML",
            r"XMLHttpRequest",
            r"WebSocket",
            r"navigator\.clipboard",
            r"\.click\s*\(",
            r"dispatchEvent\s*\(",
        )
        for pattern in forbidden_patterns:
            with self.subTest(pattern=pattern):
                self.assertIsNone(re.search(pattern, text, re.IGNORECASE))

    def test_messaging_and_api_are_explicit_bounded_and_base_url_immune(self) -> None:
        worker = (EXTENSION / "service_worker.js").read_text("utf-8")
        content = (EXTENSION / "content" / "content_script.js").read_text("utf-8")
        panel = (EXTENSION / "side_panel" / "panel.js").read_text("utf-8")
        self.assertNotIn("fetch(", worker)
        self.assertIn("chrome.tabs.query", worker)
        self.assertIn("chrome.tabs.sendMessage", worker)
        self.assertIn('fetchClosedJson(origin, "/health"', content)
        self.assertIn("/api/v1/orders/", content)
        self.assertIn("encodeURIComponent", content)
        self.assertIn("AbortController", content)
        self.assertIn("ssa-csrf-token", content)
        self.assertIn("function closedRequestUrl(origin, path)", content)
        self.assertIn("originPolicy.normalizeServiceOrigin", content)
        self.assertIn("const requestUrl = `${normalizedOrigin}${path}`", content)
        self.assertIn("response = await fetch(requestUrl,", content)
        self.assertNotIn("response = await fetch(path,", content)
        self.assertNotIn("setInterval", content)
        self.assertNotIn("setTimeout(() => evaluate", content)
        self.assertIn('kind: "EVALUATE"', panel)
        self.assertIn("addEventListener", panel)
        self.assertIn("request_key", panel)

    def test_panel_result_mapping_covers_every_m6_business_result_partition(self) -> None:
        expected = {
            "sales-credit-target-rep": "SALES_CREDIT_RESULT",
            "sales-credit-human-review": "SALES_CREDIT_RESULT",
            "doi-fulfillment-split": "DOI_OPPORTUNITY",
            "doi-manual-review": "DOI_MANUAL_REVIEW",
            "doi-full-ds": "DOI_EXCLUDED",
            "doi-dedupe-review": "DOI_MONITOR",
        }
        with tempfile.TemporaryDirectory(
            prefix="synthetic-sales-assist-m6-panel-partitions-"
        ) as directory:
            application = ScenarioApplication.open(Path(directory) / "data")
            results: dict[str, dict[str, object]] = {}
            for index, (alias, panel_state) in enumerate(expected.items(), start=1):
                detail = application.instantiate(alias, f"m6-panel-instance-{index}")
                result = application.evaluate(
                    detail.order_id,
                    f"m6-panel-evaluation-{index}",
                ).to_dict()
                results[alias] = result
                actual = (
                    "SALES_CREDIT_RESULT"
                    if result["rule_pack"] == "SALES_CREDIT"
                    else result["top_level_result"]
                )
                self.assertEqual(actual, panel_state)
                self.assertFalse(result["replayed"])
                self.assertFalse(result["conflict"])

            target = application.list_orders()[0]
            first_key = "m6-panel-exact-replay"
            initial = application.evaluate(target.order_id, first_key).to_dict()
            replay = application.evaluate(target.order_id, first_key).to_dict()
            self.assertFalse(initial["replayed"])
            self.assertTrue(replay["replayed"])
            self.assertEqual(replay["evaluation_id"], initial["evaluation_id"])
            conflict_target = next(
                item for item in application.list_orders() if item.order_id != target.order_id
            )
            with self.assertRaises(ApplicationError) as conflict:
                application.evaluate(conflict_target.order_id, first_key)
            self.assertEqual(
                conflict.exception.code,
                "IDEMPOTENCY_KEY_MATERIAL_CONFLICT",
            )

        contracts = (EXTENSION / "shared" / "contracts.js").read_text("utf-8")
        self.assertIn(
            'if (result.replayed === true) return "EXACT_REPLAY";', contracts
        )
        self.assertIn(
            'if (result.conflict === true) return "REQUEST_CONFLICT";', contracts
        )
        self.assertIn(
            'if (result.rule_pack === "SALES_CREDIT") return "SALES_CREDIT_RESULT";',
            contracts,
        )
        for state in set(expected.values()) - {"SALES_CREDIT_RESULT"}:
            self.assertIn(f'"{state}"', contracts)

    def test_offline_unhealthy_timeout_retry_and_history_paths_are_reachable(
        self,
    ) -> None:
        content = (EXTENSION / "content" / "content_script.js").read_text("utf-8")
        panel = (EXTENSION / "side_panel" / "panel.js").read_text("utf-8")
        for required in (
            "const state = backendHealthFailureState(error);",
            'return contracts.response("BACKEND_UNHEALTHY"',
            'transportError("REQUEST_TIMEOUT")',
            'return contracts.response("REQUEST_CONFLICT"',
        ):
            self.assertIn(required, content)
        self.assertIn(
            'elements.retry.addEventListener("click", () => evaluate(true))', panel
        )
        self.assertIn("const candidate = useLastKey ? lastRequestKey", panel)
        self.assertIn('showLink(elements.historyLink, data.origin, "ORDER"', panel)
        self.assertIn('credentials: "omit"', content)
        self.assertNotIn('credentials: "include"', content)
        self.assertNotIn('credentials: "same-origin"', content)

    def test_reachable_invalid_health_media_is_backend_unhealthy(self) -> None:
        content = (EXTENSION / "content" / "content_script.js").read_text("utf-8")
        self.assertIn("function backendHealthFailureState(error)", content)
        self.assertIn(
            '["BACKEND_OFFLINE", "REQUEST_TIMEOUT"].includes(error.code)',
            content,
        )

    def test_backend_projection_status_and_offline_card_are_coherent(self) -> None:
        content = (EXTENSION / "content" / "content_script.js").read_text("utf-8")
        contracts = (EXTENSION / "shared" / "contracts.js").read_text("utf-8")
        panel = (EXTENSION / "side_panel" / "panel.js").read_text("utf-8")
        self.assertIn('status: healthy ? "PASS" : "FAIL"', content)
        self.assertIn(
            'value.status !== (value.healthy ? "PASS" : "FAIL")',
            contracts,
        )
        self.assertIn(
            "value.healthy && !value.safety_counters_zero",
            contracts,
        )
        self.assertIn(
            'const data = state === "BACKEND_OFFLINE"\n'
            "        ? summary\n"
            "        : withBackend(summary, backend);",
            content,
        )
        self.assertIn(
            "value.error_code === null || backend !== null",
            contracts,
        )
        self.assertIn(
            "backend ? text(backend.status) : \"Not checked\"",
            panel,
        )
        self.assertNotIn(
            'backend.healthy ? "PASS" : text(backend.status)',
            panel,
        )
        self.assertIn('transportError("RESPONSE_MEDIA_TYPE_INVALID")', content)
        self.assertEqual(
            content.count("const state = backendHealthFailureState(error);"),
            2,
        )
        self.assertNotIn(
            'error.transport ? "BACKEND_OFFLINE" : "BACKEND_UNHEALTHY"',
            content,
        )

    def test_post_health_timeout_is_safe_error_with_same_key_retry(self) -> None:
        content = (EXTENSION / "content" / "content_script.js").read_text("utf-8")
        panel = (EXTENSION / "side_panel" / "panel.js").read_text("utf-8")
        self.assertIn(
            'const state = error && error.code === "BACKEND_OFFLINE"',
            content,
        )
        self.assertIn(
            '? "BACKEND_OFFLINE"\n        : "SAFE_ERROR";',
            content,
        )
        self.assertNotIn(
            'const state = error.transport ? "BACKEND_OFFLINE" : "SAFE_ERROR";',
            content,
        )
        self.assertIn(
            'SAFE_ERROR: ["Request failed closed", '
            '"No external action was taken. A safe retry may use the same request key."]',
            panel,
        )
        self.assertIn(
            '["SAFE_ERROR", "BACKEND_OFFLINE"].includes(state)',
            panel,
        )

    def test_result_projection_and_panel_display_include_required_governed_fields(self) -> None:
        content = (EXTENSION / "content" / "content_script.js").read_text("utf-8")
        panel = (EXTENSION / "side_panel" / "panel.js").read_text("utf-8")
        required_projection = {
            "aggregate_potential_status",
            "aggregate_potential_value",
            "case_id",
            "closure_state",
            "command_id",
            "conflict",
            "evaluation_id",
            "handling_flags",
            "human_review_required",
            "opportunities",
            "order_id",
            "processing_duration_ns",
            "reasons",
            "replayed",
            "rule_pack",
            "rule_pack_version",
            "run_id",
            "scenario_alias",
            "snapshot_id",
            "top_level_result",
            "value",
            "value_status",
            "workflow_state",
        }
        for member in required_projection:
            with self.subTest(member=member):
                self.assertIn(f"{member}: data.{member}", content)
        for label in (
            "Rule pack version",
            "Workflow",
            "Human review",
            "Aggregate potential value",
            "Closure state",
            "Handling flags",
            "Evaluation ID",
            "Run ID",
            "Snapshot ID",
            "Processing duration (ns)",
        ):
            with self.subTest(label=label):
                self.assertIn(f'["{label}"', panel)

    def test_manual_acceptance_and_installation_guides_are_complete(self) -> None:
        manual = (ROOT / "docs" / "milestone6-manual-acceptance.md").read_text("utf-8")
        readme = (EXTENSION / "README.md").read_text("utf-8")
        for phrase in (
            "Load unpacked",
            "permission",
            "offline",
            "replay",
            "conflict",
            "uninstall",
            "loopback",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase.lower(), (manual + readme).lower())


if __name__ == "__main__":
    unittest.main()
