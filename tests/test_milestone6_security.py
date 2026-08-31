from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

from synthetic_sales_assist.safety.chrome import (
    ALLOWED_CHROME_CONTENT_MATCH_PATTERNS,
    ALLOWED_CHROME_HOST_PATTERNS,
    EXTENSION_PAGE_CSP,
    validate_chrome_permissions,
)
from synthetic_sales_assist.safety.repository import (
    AUTHORED_M6_EXTENSION_SUFFIXES,
    AUTHORED_M6_MARKER,
    MAX_AUTHORED_M6_ASSET_BYTES,
    scan_prohibited_repository_content,
)
from synthetic_sales_assist.application import ScenarioApplication


ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "chrome_extension"


def _node_executable() -> Path | None:
    dependency_root = Path(sys.executable).resolve().parent.parent
    for candidate in (
        dependency_root / "node" / "bin" / "node.exe",
        dependency_root / "node" / "bin" / "node",
    ):
        if candidate.is_file():
            return candidate
    discovered = shutil.which("node")
    return None if discovered is None else Path(discovered)


class _LocalHtmlAudit(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.violations: list[str] = []
        self.resources: list[str] = []
        self._script_depth = 0

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        attributes = dict(attrs)
        if tag == "script":
            self._script_depth += 1
            source = attributes.get("src")
            if not source or source.startswith(("/", "\\")):
                self.violations.append("script-source")
        if tag == "style":
            self.violations.append("inline-style-element")
        for name, value in attrs:
            lowered = name.lower()
            if lowered.startswith("on") or lowered == "style":
                self.violations.append(f"inline-attribute:{lowered}")
            if lowered in {"href", "src"} and value:
                if "://" in value or value.startswith(("//", "data:", "javascript:")):
                    self.violations.append(f"remote-resource:{lowered}")
                else:
                    self.resources.append(value)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._script_depth:
            self._script_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._script_depth and data.strip():
            self.violations.append("inline-script")


class Milestone6ExtensionSecurityTests(unittest.TestCase):
    def test_manifest_exposes_only_closed_m6_surfaces(self) -> None:
        manifest = json.loads((EXTENSION / "manifest.json").read_text(encoding="utf-8"))
        inventory = validate_chrome_permissions(manifest)
        self.assertEqual(inventory.api_permissions, ("sidePanel",))
        self.assertEqual(set(inventory.host_permissions), ALLOWED_CHROME_HOST_PATTERNS)
        self.assertEqual(inventory.optional_api_permissions, ())
        self.assertEqual(inventory.optional_host_permissions, ())
        self.assertEqual(
            set(inventory.match_surfaces[0][1]),
            ALLOWED_CHROME_CONTENT_MATCH_PATTERNS,
        )
        self.assertEqual(
            manifest["content_security_policy"]["extension_pages"],
            EXTENSION_PAGE_CSP,
        )

    def test_extension_source_inventory_is_regular_marked_and_bounded(self) -> None:
        self.assertTrue(EXTENSION.is_dir())
        files = tuple(path for path in EXTENSION.rglob("*") if path.is_file())
        self.assertGreater(len(files), 1)
        violations: list[str] = []
        for path in files:
            relative = path.relative_to(ROOT).as_posix()
            if path.is_symlink() or not path.resolve().is_relative_to(EXTENSION.resolve()):
                violations.append(relative + ":linked")
                continue
            if path.stat().st_size > MAX_AUTHORED_M6_ASSET_BYTES:
                violations.append(relative + ":oversize")
            if path.name == "manifest.json":
                continue
            if path.suffix.lower() not in AUTHORED_M6_EXTENSION_SUFFIXES:
                violations.append(relative + ":suffix")
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                violations.append(relative + ":utf8")
                continue
            if AUTHORED_M6_MARKER not in text[:8192]:
                violations.append(relative + ":marker")
        self.assertEqual(violations, [])

    def test_javascript_has_no_remote_dynamic_or_page_mutation_capability(self) -> None:
        forbidden_patterns = {
            "dynamic-eval": re.compile(r"\beval\s*\("),
            "dynamic-function": re.compile(r"\b(?:new\s+)?Function\s*\("),
            "dynamic-import": re.compile(r"\bimport\s*\("),
            "dynamic-timer": re.compile(r"\bset(?:Timeout|Interval)\s*\(\s*['\"]"),
            "html-mutation": re.compile(
                r"\b(?:innerHTML|outerHTML|insertAdjacentHTML|document\.write)\b"
            ),
            "generic-control": re.compile(r"\.(?:click|submit)\s*\(|\bdispatchEvent\s*\("),
            "browser-storage": re.compile(
                r"\b(?:localStorage|sessionStorage|indexedDB|document\.cookie)\b"
            ),
            "unbounded-network": re.compile(
                r"\b(?:XMLHttpRequest|WebSocket|EventSource|sendBeacon|SharedWorker|Worker)\b"
            ),
            "forbidden-chrome-api": re.compile(
                r"\bchrome\.(?:cookies|debugger|downloads|history|nativeMessaging|"
                r"scripting|webNavigation|webRequest)\b"
            ),
            "tab-mutation": re.compile(
                r"\bchrome\.tabs\.(?:create|discard|duplicate|executeScript|goBack|"
                r"goForward|group|highlight|move|reload|remove|update)\s*\("
            ),
        }
        violations: list[str] = []
        for path in sorted(EXTENSION.rglob("*.js")):
            text = path.read_text(encoding="utf-8")
            for name, pattern in forbidden_patterns.items():
                if pattern.search(text):
                    violations.append(f"{path.relative_to(ROOT).as_posix()}:{name}")
        self.assertEqual(violations, [])

    def test_network_and_worker_code_loading_sites_are_exact(self) -> None:
        javascript = {
            path.relative_to(EXTENSION).as_posix(): path.read_text(encoding="utf-8")
            for path in sorted(EXTENSION.rglob("*.js"))
        }
        fetch_sites = {
            relative: text.count("fetch(")
            for relative, text in javascript.items()
            if "fetch(" in text
        }
        self.assertEqual(fetch_sites, {"content/content_script.js": 1})
        self.assertIn(
            "response = await fetch(requestUrl,",
            javascript["content/content_script.js"],
        )
        worker = javascript["service_worker.js"]
        self.assertEqual(worker.count("importScripts("), 1)
        self.assertIn(
            'importScripts("shared/canonical.js", "shared/contracts.js");',
            worker,
        )

    def test_all_javascript_grammars_use_true_end_assertions(self) -> None:
        for relative in (
            "content/content_script.js",
            "shared/contracts.js",
            "shared/extraction.js",
            "shared/origin.js",
        ):
            source = (EXTENSION / relative).read_text(encoding="utf-8")
            with self.subTest(relative=relative):
                self.assertNotIn("$/", source)
                self.assertNotIn("$)/", source)
                for line in source.splitlines():
                    if "new RegExp(" in line:
                        self.assertIn("(?![\\\\s\\\\S])", line)

    def test_true_end_grammar_families_execute_in_ecmascript(self) -> None:
        node = _node_executable()
        if node is None:
            self.skipTest("Node.js runtime unavailable")
        script = r"""
const path = require("node:path");
const extensionRoot = process.argv[1];
for (const relative of [
  "shared/canonical.js",
  "shared/contracts.js",
  "shared/origin.js",
  "shared/extraction.js"
]) {
  require(path.join(extensionRoot, relative));
}
const C = globalThis.SSA.Contracts;
const E = globalThis.SSA.Extraction;
const O = globalThis.SSA.Origin;
const terminators = ["\n", "\r", "\u2028", "\u2029"];
let count = 0;
function accepts(operation, value) {
  try {
    operation(value);
    return true;
  } catch (_error) {
    return false;
  }
}
function expectTrueEnd(name, operation, valid) {
  if (!accepts(operation, valid)) throw new Error(name + "_VALID_REJECTED");
  for (const suffix of terminators) {
    if (accepts(operation, valid + suffix)) {
      throw new Error(name + "_TRAILING_TERMINATOR_ACCEPTED");
    }
  }
  count += 1;
}
expectTrueEnd("request_key", (value) => C.validateRequestKey(value), "M6-REQ:1");
expectTrueEnd("safe_code", (value) => {
  if (C.validateSafeCode(value, null) !== value) throw new Error("invalid");
}, "SAFE_CODE");
expectTrueEnd("token", (value) => C.validateToken(value, "TOKEN_INVALID"), "TOKEN_1");
expectTrueEnd("alias", (value) => C.validateAlias(value), "scenario-1");
expectTrueEnd(
  "origin",
  (value) => O.normalizeServiceOrigin(value),
  "http://127.0.0.1:8765/"
);
for (const [namespace, value] of Object.entries({
  ORDER: "SYN-ORDER-CANARY",
  INTERACTION: "SYN-INTERACTION-CANARY",
  EVIDENCE: "SYN-EVIDENCE-CANARY",
  SKU: "SYN-SKU-CANARY",
  RUN: "SYN-RUN-CANARY",
  SNAPSHOT: "SYN-SNAPSHOT-CANARY",
  EVALUATION: "SYN-EVALUATION-CANARY"
})) {
  expectTrueEnd(
    "synthetic_id_" + namespace,
    (candidate) => C.validateSyntheticId(candidate, namespace),
    value
  );
}
const orderId = "SYN-ORDER-CANARY";
expectTrueEnd("fingerprint", (value) => C.validateMessage({
  expected_order_id: orderId,
  expected_origin: "http://127.0.0.1:8765",
  expected_source_fingerprint: value,
  kind: "EVALUATE",
  request_key: "M6-REQ:1",
  schema_version: C.MESSAGE_SCHEMA_VERSION
}), "a".repeat(64));
const completeness = {
  declared_relevant_line_count: 0,
  fixture_version: "shared-fixture/v1",
  observed_order_id: orderId,
  ordered_line_manifest_digest: null,
  rendered_relevant_line_count: 0,
  requested_order_id: orderId,
  source_observed_at: "2026-08-31T12:34:56Z",
  source_schema_version: "shared-whole-order-completeness/v1",
  state: "COMPLETE"
};
expectTrueEnd("digest", (value) => E.validateCompleteness({
  ...completeness,
  ordered_line_manifest_digest: value
}, orderId), "b".repeat(64));
expectTrueEnd("quantity", (value) => E.validateFact("quantity", {
  reason_code: null,
  tag: "KNOWN",
  value
}, "COMPLETE"), "42");
expectTrueEnd("money", (value) => E.validateFact("line_value", {
  reason_code: null,
  tag: "KNOWN",
  value: {
    amount: value,
    currency_code: "USD",
    currency_registry_version: "synthetic-iso-style-currency-registry/v1",
    currency_scale: 2
  }
}, "COMPLETE"), "12.34");
expectTrueEnd(
  "timestamp",
  (value) => E.validateTimestamp(value, "TIMESTAMP_INVALID"),
  "2026-08-31T12:34:56.123Z"
);
expectTrueEnd("reason", (value) => {
  if (!C.isDoiReason(value)) throw new Error("invalid");
}, "RC-001");
C.validateNoRedirectResponse({status: 200, type: "basic"});
for (const response of [
  {status: 0, type: "opaqueredirect"},
  {status: 302, type: "basic"}
]) {
  try {
    C.validateNoRedirectResponse(response);
    throw new Error("REDIRECT_ACCEPTED");
  } catch (error) {
    if (error.code !== "RESPONSE_REDIRECT_INVALID") throw error;
  }
}
process.stdout.write(
  "M6_TRUE_END_RUNTIME_CANARIES=" + count +
  " TERMINATORS=" + terminators.length
);
"""
        completed = subprocess.run(
            [str(node), "-e", script, str(EXTENSION)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            completed.stdout,
            "M6_TRUE_END_RUNTIME_CANARIES=18 TERMINATORS=4",
        )

    def test_raw_empty_query_and_configured_fragment_delimiters_fail_closed(self) -> None:
        node = _node_executable()
        if node is None:
            self.skipTest("Node.js runtime unavailable")
        script = r"""
const path = require("node:path");
const extensionRoot = process.argv[1];
for (const relative of [
  "shared/canonical.js",
  "shared/contracts.js",
  "shared/origin.js"
]) {
  require(path.join(extensionRoot, relative));
}
const O = globalThis.SSA.Origin;
let count = 0;
function expectRejected(name, operation) {
  try {
    operation();
    throw new Error(name + "_ACCEPTED");
  } catch (error) {
    if (error.message === name + "_ACCEPTED") throw error;
    if (error.code !== "LOOPBACK_ORIGIN_INVALID") throw error;
  }
  count += 1;
}
for (const candidate of [
  "http://127.0.0.1:8765/?",
  "http://127.0.0.1:8765/?#fragment",
  "http://127.0.0.1:8765/#"
]) {
  expectRejected("CONFIGURED_ORIGIN_DELIMITER", () =>
    O.normalizeServiceOrigin(candidate)
  );
}
for (const candidate of [
  "http://127.0.0.1:8765/orders/SYN-ORDER-CANARY?",
  "http://127.0.0.1:8765/orders/SYN-ORDER-CANARY?#fragment",
  "http://localhost:8765/interactions/SYN-INTERACTION-CANARY?"
]) {
  expectRejected("PAGE_QUERY_DELIMITER", () => O.validatePageLocation(candidate));
}
if (O.normalizeServiceOrigin("http://127.0.0.1:8765/") !==
    "http://127.0.0.1:8765") throw new Error("VALID_ORIGIN_REJECTED");
const withFragment = O.validatePageLocation(
  "http://127.0.0.1:8765/orders/SYN-ORDER-CANARY#history?view"
);
if (withFragment.path !== "/orders/SYN-ORDER-CANARY" ||
    withFragment.url !==
      "http://127.0.0.1:8765/orders/SYN-ORDER-CANARY#history?view") {
  throw new Error("VALID_PAGE_FRAGMENT_REJECTED");
}
process.stdout.write("M6_RAW_DELIMITER_CANARIES=" + count);
"""
        completed = subprocess.run(
            [str(node), "-e", script, str(EXTENSION)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "M6_RAW_DELIMITER_CANARIES=6")

    def test_health_registry_telemetry_relations_fail_closed(self) -> None:
        node = _node_executable()
        if node is None:
            self.skipTest("Node.js runtime unavailable")
        source = (EXTENSION / "content" / "content_script.js").read_text(
            encoding="utf-8"
        )
        for guard in (
            "data.registry_capacity < 1",
            "data.registry_capacity > 256",
            "data.evaluated_count > data.registry_count",
            "data.registry_count > data.registry_capacity",
        ):
            with self.subTest(guard=guard):
                self.assertIn(guard, source)
        script = r"""
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const extensionRoot = process.argv[1];
for (const relative of [
  "shared/canonical.js",
  "shared/contracts.js",
  "shared/origin.js",
  "shared/extraction.js"
]) {
  require(path.join(extensionRoot, relative));
}
globalThis.chrome = {
  runtime: {id: "m6-health-canary", onMessage: {addListener() {}}}
};
const contentPath = path.join(extensionRoot, "content/content_script.js");
let contentSource = fs.readFileSync(contentPath, "utf8");
const marker = "  chrome.runtime.onMessage.addListener";
if (!contentSource.includes(marker)) throw new Error("CONTENT_EXPOSURE_MARKER_MISSING");
contentSource = contentSource.replace(
  marker,
  "  globalThis.__M6ValidateHealth = validateHealth;\n" + marker
);
vm.runInThisContext(contentSource, {filename: contentPath});
const C = globalThis.SSA.Contracts;
const validateHealth = globalThis.__M6ValidateHealth;
const counters = Object.fromEntries(C.SAFETY_COUNTER_NAMES.map((name) => [name, 0]));
const valid = {
  app_version: "0.1.0",
  build_version: "synthetic-sales-assist-m5/v1",
  database_schema_version: 4,
  database_status: "PASS",
  evaluated_count: 2,
  expected_schema_version: 4,
  integrity_check: "not_run",
  migration_status: "CURRENT",
  projection_status: "PASS",
  quick_check: "ok",
  registry_capacity: 256,
  registry_count: 3,
  safety_counters: counters,
  schema_version: C.APPLICATION_SCHEMA_VERSION,
  status: "PASS"
};
if (!validateHealth(valid, 200).healthy) throw new Error("VALID_HEALTH_REJECTED");
let rejected = 0;
for (const candidate of [
  {...valid, registry_capacity: 0},
  {...valid, registry_capacity: 257},
  {...valid, evaluated_count: 4},
  {...valid, registry_capacity: 2}
]) {
  try {
    validateHealth(candidate, 200);
    throw new Error("INCOHERENT_HEALTH_ACCEPTED");
  } catch (error) {
    if (error.code !== "HEALTH_CONTRACT_INVALID") throw error;
    rejected += 1;
  }
}
process.stdout.write("M6_HEALTH_RELATION_CANARIES=" + rejected);
"""
        completed = subprocess.run(
            [str(node), "-e", script, str(EXTENSION)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "M6_HEALTH_RELATION_CANARIES=4")

    def test_summary_origin_rejects_non_strings_without_regex_coercion(self) -> None:
        node = _node_executable()
        if node is None:
            self.skipTest("Node.js runtime unavailable")
        contracts_source = (EXTENSION / "shared" / "contracts.js").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            'typeof value.origin !== "string" ||\n'
            "      !LOOPBACK_ORIGIN_PATTERN.test(value.origin)",
            contracts_source,
        )
        script = r"""
const path = require("node:path");
const extensionRoot = process.argv[1];
require(path.join(extensionRoot, "shared/canonical.js"));
require(path.join(extensionRoot, "shared/contracts.js"));
const C = globalThis.SSA.Contracts;
const baseSummary = {
  backend: null,
  can_evaluate: false,
  completeness_state: null,
  evaluation: null,
  interaction_id: null,
  order_id: null,
  origin: "http://127.0.0.1:8765",
  page_identity: null,
  page_kind: "unsupported",
  rule_pack: null,
  scenario_alias: null,
  source_fingerprint: null
};
function response(origin) {
  return {
    data: {...baseSummary, origin},
    error_code: null,
    panel_state: "UNSUPPORTED_PAGE",
    schema_version: C.MESSAGE_SCHEMA_VERSION
  };
}
C.validateResponse(response(baseSummary.origin));
let rejected = 0;
for (const origin of [[baseSummary.origin], {}, 8765]) {
  try {
    C.validateResponse(response(origin));
    throw new Error("NON_STRING_ORIGIN_ACCEPTED");
  } catch (error) {
    if (error.code !== "SUMMARY_CONTRACT_INVALID") throw error;
    rejected += 1;
  }
}
process.stdout.write("M6_SUMMARY_ORIGIN_TYPE_CANARIES=" + rejected);
"""
        completed = subprocess.run(
            [str(node), "-e", script, str(EXTENSION)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "M6_SUMMARY_ORIGIN_TYPE_CANARIES=3")

    def test_source_failure_responses_require_summary_or_safe_error(self) -> None:
        node = _node_executable()
        if node is None:
            self.skipTest("Node.js runtime unavailable")
        script = r"""
const path = require("node:path");
const extensionRoot = process.argv[1];
require(path.join(extensionRoot, "shared/canonical.js"));
require(path.join(extensionRoot, "shared/contracts.js"));
const C = globalThis.SSA.Contracts;
const orderId = "SYN-ORDER-SOURCE-FAILURE";
function summary(completenessState) {
  return {
    backend: null,
    can_evaluate: false,
    completeness_state: completenessState,
    evaluation: null,
    interaction_id: null,
    order_id: orderId,
    origin: "http://127.0.0.1:8765",
    page_identity: orderId,
    page_kind: "order-detail",
    rule_pack: "SALES_CREDIT",
    scenario_alias: "source-failure-canary",
    source_fingerprint: null
  };
}
let rejected = 0;
let accepted = 0;
for (const [panelState, completenessState] of [
  ["INCOMPLETE_PAGE", "INCOMPLETE"],
  ["MALFORMED_PAGE", "MALFORMED"]
]) {
  try {
    C.validateResponse({
      data: null,
      error_code: null,
      panel_state: panelState,
      schema_version: C.MESSAGE_SCHEMA_VERSION
    });
    throw new Error(panelState + "_EMPTY_SUCCESS_ACCEPTED");
  } catch (error) {
    if (error.code !== "RESPONSE_SOURCE_FAILURE_BINDING_INVALID") throw error;
    rejected += 1;
  }
  C.validateResponse({
    data: null,
    error_code: "SOURCE_EXTRACTION_FAILED",
    panel_state: panelState,
    schema_version: C.MESSAGE_SCHEMA_VERSION
  });
  accepted += 1;
  C.validateResponse({
    data: summary(completenessState),
    error_code: null,
    panel_state: panelState,
    schema_version: C.MESSAGE_SCHEMA_VERSION
  });
  accepted += 1;
}
process.stdout.write(
  "M6_SOURCE_FAILURE_RESPONSE_CANARIES=REJECTED:" + rejected +
  " ACCEPTED:" + accepted
);
"""
        completed = subprocess.run(
            [str(node), "-e", script, str(EXTENSION)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            completed.stdout,
            "M6_SOURCE_FAILURE_RESPONSE_CANARIES=REJECTED:2 ACCEPTED:4",
        )

    def test_complete_source_version_pairs_are_bound_to_exact_rule_pack(self) -> None:
        node = _node_executable()
        if node is None:
            self.skipTest("Node.js runtime unavailable")
        extraction_source = (EXTENSION / "shared" / "extraction.js").read_text(
            encoding="utf-8"
        )
        binding_call = (
            "validateSourceRulePackBinding(payload.completeness, "
            "binding.rule_pack);"
        )
        self.assertIn(binding_call, extraction_source)
        self.assertLess(
            extraction_source.index(binding_call),
            extraction_source.index("const rootCompleteness ="),
        )
        for path in (
            EXTENSION / "README.md",
            ROOT / "docs" / "milestone6-extension-contract.md",
            ROOT
            / "docs"
            / "adr"
            / "0022-localhost-extension-permissions-and-message-boundary.md",
        ):
            document = path.read_text(encoding="utf-8")
            with self.subTest(document=path.name):
                self.assertIn("sales-credit-m5-fixture/v1", document)
                self.assertIn("synthetic-sales-credit-domain/v1", document)
                self.assertIn("shared-whole-order-completeness/v1", document)
                self.assertIn("m5-malformed-fixture/v1", document)
        script = r"""
const path = require("node:path");
const extensionRoot = process.argv[1];
for (const relative of [
  "shared/canonical.js",
  "shared/contracts.js",
  "shared/origin.js",
  "shared/extraction.js"
]) {
  require(path.join(extensionRoot, relative));
}
const E = globalThis.SSA.Extraction;
const sales = {
  fixture_version: "sales-credit-m5-fixture/v1",
  source_schema_version: "synthetic-sales-credit-domain/v1",
  state: "COMPLETE"
};
const doi = {
  fixture_version: "shared-fixture/v1",
  source_schema_version: "shared-whole-order-completeness/v1",
  state: "COMPLETE"
};
const malformed = {
  fixture_version: "m5-malformed-fixture/v1",
  source_schema_version: "synthetic-malformed-input/v1",
  state: "MALFORMED"
};
if (E.validateSourceRulePackBinding(sales, "SALES_CREDIT") !== "SALES_CREDIT") {
  throw new Error("SALES_CREDIT_VALID_BINDING_REJECTED");
}
if (E.validateSourceRulePackBinding(doi, "DOI") !== "DOI") {
  throw new Error("DOI_VALID_BINDING_REJECTED");
}
if (E.validateSourceRulePackBinding(malformed, "DOI") !== null) {
  throw new Error("MALFORMED_SOURCE_BECAME_EVALUABLE");
}
let rejected = 0;
for (const [completeness, rulePack, code] of [
  [sales, "DOI", "SOURCE_RULE_PACK_BINDING_INVALID"],
  [doi, "SALES_CREDIT", "SOURCE_RULE_PACK_BINDING_INVALID"],
  [{...malformed, state: "COMPLETE"}, "DOI", "MALFORMED_SOURCE_PROMOTION_INVALID"]
]) {
  try {
    E.validateSourceRulePackBinding(completeness, rulePack);
    throw new Error("SOURCE_RULE_PACK_TAMPER_ACCEPTED");
  } catch (error) {
    if (error.code !== code || error.panelState !== "DOM_PAYLOAD_MISMATCH") {
      throw error;
    }
    rejected += 1;
  }
}
process.stdout.write("M6_SOURCE_RULE_PACK_CANARIES=" + rejected);
"""
        completed = subprocess.run(
            [str(node), "-e", script, str(EXTENSION)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "M6_SOURCE_RULE_PACK_CANARIES=3")

    def test_source_versions_currency_and_reason_codes_reject_type_coercion(self) -> None:
        node = _node_executable()
        if node is None:
            self.skipTest("Node.js runtime unavailable")
        extraction_source = (EXTENSION / "shared" / "extraction.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("function sourceVersionPair(completeness)", extraction_source)
        self.assertIn('typeof value !== "string" || value.length === 0', extraction_source)
        for relative, guard in (
            ("shared/extraction.js", 'typeof value.currency_code !== "string"'),
            ("shared/contracts.js", 'typeof value.currency_code !== "string"'),
            ("content/content_script.js", 'typeof value.currency_code !== "string"'),
        ):
            source = (EXTENSION / relative).read_text(encoding="utf-8")
            with self.subTest(relative=relative):
                self.assertLess(
                    source.index(guard),
                    source.index("CURRENCY_SCALES[value.currency_code]"),
                )
        script = r"""
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const extensionRoot = process.argv[1];
require(path.join(extensionRoot, "shared/canonical.js"));
const contractsPath = path.join(extensionRoot, "shared/contracts.js");
let contractsSource = fs.readFileSync(contractsPath, "utf8");
const contractsMarker = "  const root = globalThis.SSA ||";
if (!contractsSource.includes(contractsMarker)) {
  throw new Error("CONTRACTS_EXPOSURE_MARKER_MISSING");
}
contractsSource = contractsSource.replace(
  contractsMarker,
  "  globalThis.__M6ProjectedMoney = validateMoney;\n" + contractsMarker
);
vm.runInThisContext(contractsSource, {filename: contractsPath});
for (const relative of ["shared/origin.js", "shared/extraction.js"]) {
  require(path.join(extensionRoot, relative));
}
globalThis.chrome = {
  runtime: {id: "m6-canary", onMessage: {addListener() {}}}
};
const contentPath = path.join(extensionRoot, "content/content_script.js");
let contentSource = fs.readFileSync(contentPath, "utf8");
const marker = "  chrome.runtime.onMessage.addListener";
if (!contentSource.includes(marker)) throw new Error("CONTENT_EXPOSURE_MARKER_MISSING");
contentSource = contentSource.replace(
  marker,
  "  globalThis.__M6ContentValidators = " +
  "Object.freeze({isDoiReason, validateMoney});\n" + marker
);
vm.runInThisContext(contentSource, {filename: contentPath});
const C = globalThis.SSA.Contracts;
const E = globalThis.SSA.Extraction;
const A = globalThis.__M6ContentValidators;
const P = globalThis.__M6ProjectedMoney;
function rejectCode(operation, code) {
  try {
    operation();
    throw new Error("COERCIBLE_VALUE_ACCEPTED");
  } catch (error) {
    if (error.code !== code) throw error;
  }
}
const orderId = "SYN-ORDER-SOURCE-TYPE-CANARY";
const completeness = {
  declared_relevant_line_count: 0,
  fixture_version: "shared-fixture/v1",
  observed_order_id: orderId,
  ordered_line_manifest_digest: null,
  rendered_relevant_line_count: 0,
  requested_order_id: orderId,
  source_observed_at: "2026-08-31T12:34:56Z",
  source_schema_version: "shared-whole-order-completeness/v1",
  state: "COMPLETE"
};
E.validateCompleteness(completeness, orderId);
let sourceRejected = 0;
for (const member of ["fixture_version", "source_schema_version"]) {
  for (const candidate of [[completeness[member]], {}, 1]) {
    try {
      E.validateCompleteness({...completeness, [member]: candidate}, orderId);
      throw new Error("SOURCE_VERSION_TYPE_ACCEPTED");
    } catch (error) {
      if (
        error.code !== "SOURCE_VERSION_BINDING_INVALID" ||
        error.panelState !== "UNSUPPORTED_PAGE"
      ) throw error;
      sourceRejected += 1;
    }
  }
}
const money = {
  amount: "12.34",
  currency_code: "USD",
  currency_registry_version: "synthetic-iso-style-currency-registry/v1",
  currency_scale: 2
};
const extractionMoney = (value) => E.validateFact("line_value", {
  reason_code: null,
  tag: "KNOWN",
  value
}, "COMPLETE");
extractionMoney(money);
P(money, "PROJECTED_MONEY_TYPE_INVALID");
A.validateMoney(money, "API_MONEY_TYPE_INVALID");
let currencyRejected = 0;
for (const candidate of [["USD"], {}, 840]) {
  rejectCode(
    () => extractionMoney({...money, currency_code: candidate}),
    "MONEY_VALUE_INVALID"
  );
  rejectCode(
    () => P({...money, currency_code: candidate}, "PROJECTED_MONEY_TYPE_INVALID"),
    "PROJECTED_MONEY_TYPE_INVALID"
  );
  rejectCode(
    () => A.validateMoney({...money, currency_code: candidate}, "API_MONEY_TYPE_INVALID"),
    "API_MONEY_TYPE_INVALID"
  );
  currencyRejected += 3;
}
if (!C.isDoiReason("RC-001") || !A.isDoiReason("RC-001")) {
  throw new Error("VALID_DOI_REASON_REJECTED");
}
let reasonRejected = 0;
for (const candidate of [["RC-001"], {}, 1]) {
  if (C.isDoiReason(candidate) || A.isDoiReason(candidate)) {
    throw new Error("DOI_REASON_TYPE_ACCEPTED");
  }
  reasonRejected += 2;
}
process.stdout.write(
  "M6_TYPE_COERCION_CANARIES=" + sourceRejected + "/" +
  currencyRejected + "/" + reasonRejected
);
"""
        completed = subprocess.run(
            [str(node), "-e", script, str(EXTENSION)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "M6_TYPE_COERCION_CANARIES=6/9/6")

    def test_full_and_projected_result_display_partitions_fail_closed(self) -> None:
        node = _node_executable()
        if node is None:
            self.skipTest("Node.js runtime unavailable")
        human_workflows = {
            "INBOUND_EVIDENCE_HUMAN_REVIEW",
            "MANUAL_REVIEW_REQUIRED",
            "ORDER_CHANGED_HUMAN_REVIEW",
            "OTHER_REP_HUMAN_REVIEW",
            "OUTBOUND_EVIDENCE_HUMAN_REVIEW",
            "POSSIBLE_REPLACEMENT_HUMAN_REVIEW",
            "TIMING_UNCERTAIN_HUMAN_REVIEW",
        }
        for relative in ("shared/contracts.js", "content/content_script.js"):
            source = (EXTENSION / relative).read_text(encoding="utf-8")
            with self.subTest(relative=relative):
                for workflow in human_workflows:
                    self.assertIn(f'"{workflow}"', source)
                self.assertIn('flags.has("NO_PERSISTENCE_MILESTONE_2")', source)
                self.assertIn('flags.has("ZERO_ACTIVE_VALUE") === canceled', source)
                self.assertIn('data.closure_state === "NONE"', source.replace("value.", "data."))

        with tempfile.TemporaryDirectory(
            prefix="synthetic-sales-assist-m6-result-coherence-"
        ) as directory:
            directory_path = Path(directory)
            application = ScenarioApplication.open(directory_path / "data")
            aliases = {
                "sc_review": "sales-credit-human-review",
                "sc_no_review": "sales-credit-target-rep",
                "sc_canceled": "sales-credit-cancellation-replacement",
                "doi_manual": "doi-manual-review",
                "doi_opportunity": "doi-fulfillment-split",
                "doi_excluded": "doi-full-ds",
                "doi_monitor": "doi-dedupe-review",
            }
            fixtures: dict[str, object] = {}
            for index, (name, alias) in enumerate(aliases.items(), start=1):
                detail = application.instantiate(alias, f"m6-coherence-source-{index}")
                result = application.evaluate(
                    detail.order_id,
                    f"m6-coherence-evaluation-{index}",
                ).to_dict()
                order = application.get_order(detail.order_id).to_dict()
                fixtures[name] = {
                    "line_ids": [line["line_id"] for line in order["lines"]],
                    "result": result,
                }
            fixture_path = directory_path / "result-coherence-canaries.json"
            fixture_path.write_text(
                json.dumps(fixtures, separators=(",", ":"), sort_keys=True),
                encoding="utf-8",
            )
            script = r"""
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const extensionRoot = process.argv[1];
const fixtures = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
require(path.join(extensionRoot, "shared/canonical.js"));
const contractsPath = path.join(extensionRoot, "shared/contracts.js");
let contractsSource = fs.readFileSync(contractsPath, "utf8");
const contractsMarker = "  const root = globalThis.SSA ||";
if (!contractsSource.includes(contractsMarker)) {
  throw new Error("CONTRACTS_EXPOSURE_MARKER_MISSING");
}
contractsSource = contractsSource.replace(
  contractsMarker,
  "  globalThis.__M6ProjectedEvaluation = validateProjectedEvaluation;\n" +
    contractsMarker
);
vm.runInThisContext(contractsSource, {filename: contractsPath});
for (const relative of ["shared/origin.js", "shared/extraction.js"]) {
  require(path.join(extensionRoot, relative));
}
globalThis.chrome = {
  runtime: {id: "m6-coherence-canary", onMessage: {addListener() {}}}
};
const contentPath = path.join(extensionRoot, "content/content_script.js");
let contentSource = fs.readFileSync(contentPath, "utf8");
const contentMarker = "  chrome.runtime.onMessage.addListener";
if (!contentSource.includes(contentMarker)) {
  throw new Error("CONTENT_EXPOSURE_MARKER_MISSING");
}
contentSource = contentSource.replace(
  contentMarker,
  "  globalThis.__M6FullEvaluation = " +
    "Object.freeze({projectEvaluation, validateEvaluation});\n" + contentMarker
);
vm.runInThisContext(contentSource, {filename: contentPath});
const F = globalThis.__M6FullEvaluation;
const P = globalThis.__M6ProjectedEvaluation;
function validateFull(item, result) {
  return F.validateEvaluation(
    result,
    result.order_id,
    result.scenario_alias,
    result.rule_pack,
    new Set(item.line_ids)
  );
}
function reject(operation, code) {
  try {
    operation();
    throw new Error("INCOHERENT_RESULT_ACCEPTED");
  } catch (error) {
    if (error.code !== code) throw error;
  }
}
for (const item of Object.values(fixtures)) {
  const valid = validateFull(item, item.result);
  P(F.projectEvaluation(valid));
}
const money = fixtures.sc_no_review.result.aggregate_potential_value;
if (money === null) throw new Error("SALES_CREDIT_PLACED_VALUE_CANARY_MISSING");
const zeroMoney = {...money, amount: "0.00"};
const mutations = [
  ["sc_review", (value) => ({...value, human_review_required: false}), "SC"],
  ["sc_no_review", (value) => ({...value, human_review_required: true}), "SC"],
  ["doi_manual", (value) => ({...value, human_review_required: false}), "DOI"],
  ["doi_manual", (value) => ({
    ...value,
    aggregate_potential_status: "AVAILABLE",
    aggregate_potential_value: money,
    value: money,
    value_status: "AVAILABLE"
  }), "DOI"],
  ["doi_manual", (value) => ({
    ...value,
    closure_state: "SHIPPED",
    top_level_result: "DOI_EXCLUDED",
    workflow_state: "ACTIVE"
  }), "DOI"],
  ["doi_manual", (value) => ({
    ...value,
    closure_state: "SHIPPED",
    workflow_state: "CLOSED_HARD"
  }), "DOI"],
  ["sc_no_review", (value) => ({...value, value: null}), "SC"],
  ["sc_no_review", (value) => ({
    ...value,
    aggregate_potential_status: "CURRENT_ONLY",
    value_status: "CURRENT_ONLY"
  }), "SC"],
  ["sc_no_review", (value) => ({
    ...value,
    aggregate_potential_status: "UNKNOWN",
    value_status: "UNKNOWN"
  }), "SC"],
  ["sc_no_review", (value) => ({
    ...value,
    aggregate_potential_status: "CHANGED_REVIEW",
    value: null,
    value_status: "CHANGED_REVIEW"
  }), "SC"],
  ["sc_no_review", (value) => ({
    ...value,
    handling_flags: value.handling_flags.filter(
      (item) => item !== "NO_PERSISTENCE_MILESTONE_2"
    )
  }), "SC"],
  ["sc_no_review", (value) => ({
    ...value,
    handling_flags: [
      ...value.handling_flags.filter(
        (item) => item !== "ACTIVE_CASE_CLASSIFICATION"
      ),
      "HUMAN_REVIEW_REQUIRED"
    ]
  }), "SC"],
  ["sc_no_review", (value) => ({
    ...value,
    handling_flags: [...value.handling_flags, "ZERO_ACTIVE_VALUE"]
  }), "SC"],
  ["sc_canceled", (value) => ({
    ...value,
    handling_flags: value.handling_flags.filter(
      (item) => item !== "ZERO_ACTIVE_VALUE"
    )
  }), "SC"],
  ["sc_canceled", (value) => ({...value, closure_state: "ACTIVE"}), "SC"],
  ["sc_no_review", (value) => ({...value, closure_state: "CANCELED"}), "SC"],
  ["sc_canceled", (value) => ({
    ...value,
    value: value.aggregate_potential_value
  }), "SC"],
  ["sc_no_review", (value) => ({...value, value: zeroMoney}), "SC"]
];
let fullRejected = 0;
let projectedRejected = 0;
for (const [name, mutation, partition] of mutations) {
  const item = fixtures[name];
  const full = mutation(item.result);
  reject(
    () => validateFull(item, full),
    partition === "SC"
      ? "SALES_CREDIT_RESULT_SEMANTICS_INVALID"
      : "DOI_RESULT_SEMANTICS_INVALID"
  );
  fullRejected += 1;
  const projected = mutation(F.projectEvaluation(item.result));
  reject(
    () => P(projected),
    partition === "SC"
      ? "PROJECTED_SALES_CREDIT_SEMANTICS_INVALID"
      : "PROJECTED_DOI_SEMANTICS_INVALID"
  );
  projectedRejected += 1;
}
process.stdout.write(
  "M6_RESULT_COHERENCE_CANARIES=" + fullRejected + "/" + projectedRejected
);
"""
            completed = subprocess.run(
                [str(node), "-e", script, str(EXTENSION), str(fixture_path)],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "M6_RESULT_COHERENCE_CANARIES=18/18")

    def test_redirects_are_never_followed_and_are_precisely_classified(self) -> None:
        content = (EXTENSION / "content" / "content_script.js").read_text(
            encoding="utf-8"
        )
        contracts = (EXTENSION / "shared" / "contracts.js").read_text(
            encoding="utf-8"
        )
        for fragment in (
            'redirect: "manual"',
            "contracts.validateNoRedirectResponse(response)",
            '"BACKEND_OFFLINE", "REQUEST_TIMEOUT"',
            'error && error.code === "BACKEND_OFFLINE"',
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, content)
        self.assertNotIn('redirect: "follow"', content)
        self.assertNotIn('redirect: "error"', content)
        for fragment in (
            'responseValue.type === "opaqueredirect"',
            "responseValue.status >= 300 && responseValue.status <= 399",
            'contractError("RESPONSE_REDIRECT_INVALID")',
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, contracts)

    def test_mismatch_copy_promises_zero_evaluation_posts_not_zero_health_reads(self) -> None:
        panel = (EXTENSION / "side_panel" / "panel.js").read_text(encoding="utf-8")
        extension_contract = (
            ROOT / "docs" / "milestone6-extension-contract.md"
        ).read_text(encoding="utf-8")
        self.assertIn(
            '"Evaluation failed closed before any evaluation POST."',
            panel,
        )
        self.assertNotIn("before any successful API call", panel)
        for fragment in (
            "An initial mismatch makes zero requests.",
            "sole read-only `/health` probe",
            "zero evaluation POSTs",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, extension_contract)

    def test_route_docs_count_event_bound_health_reads_without_polling(self) -> None:
        route_contract = (ROOT / "docs" / "milestone6-route-contract.md").read_text(
            encoding="utf-8"
        )
        adr = (
            ROOT
            / "docs"
            / "adr"
            / "0022-localhost-extension-permissions-and-message-boundary.md"
        ).read_text(encoding="utf-8")
        for fragment in (
            "once per supported-page refresh/open, plus once per explicit evaluation",
            "one extension Fetch API invocation after each explicit user Evaluate click",
            "There is no hidden or repeated polling",
            "Chrome may retransmit that same byte-identical POST",
        ):
            with self.subTest(document="route-contract", fragment=fragment):
                self.assertIn(fragment, route_contract)
        for fragment in (
            "one additional `GET /health` preflight after an explicit evaluation click",
            "one extension Fetch API invocation for",
            "Chrome may retransmit the same byte-identical POST",
            "These event-bound reads are not polling.",
        ):
            with self.subTest(document="adr-0022", fragment=fragment):
                self.assertIn(fragment, adr)

    def test_hostile_base_cannot_retarget_absolute_closed_request_url(self) -> None:
        content = (EXTENSION / "content" / "content_script.js").read_text(
            encoding="utf-8"
        )
        required = (
            "function closedRequestUrl(origin, path)",
            "originPolicy.normalizeServiceOrigin(`${origin}/`)",
            'path !== "/health"',
            "contracts.validateSyntheticId(match[1], \"ORDER\")",
            "const requestUrl = `${normalizedOrigin}${path}`",
            "const parsed = new URL(requestUrl)",
            "const parsedPath = `${parsed.pathname}${parsed.search}${parsed.hash}`",
            "parsed.origin !== normalizedOrigin || parsedPath !== path",
            "const requestUrl = closedRequestUrl(origin, path)",
            "response = await fetch(requestUrl,",
            'credentials: "omit"',
            'redirect: "manual"',
            'referrerPolicy: "no-referrer"',
            'response.headers.get("content-type") !== "application/json; charset=utf-8"',
            'transportError("RESPONSE_MEDIA_TYPE_INVALID")',
        )
        for fragment in required:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, content)
        self.assertNotIn("fetch(path,", content)
        self.assertNotIn("fetch(origin,", content)

    def test_response_body_is_streamed_with_a_canonical_byte_limit(self) -> None:
        content = (EXTENSION / "content" / "content_script.js").read_text(
            encoding="utf-8"
        )
        required = (
            "async function readBoundedResponseText(response, controller)",
            'response.headers.get("Content-Length")',
            'typeof response.body.getReader !== "function"',
            "const reader = response.body.getReader()",
            "declared > canonical.MAX_DOCUMENT_BYTES",
            "total > canonical.MAX_DOCUMENT_BYTES",
            'new TextDecoder("utf-8", {fatal: true})',
            "await rejectResponseBody(reader, controller",
            "const text = await readBoundedResponseText(response, controller)",
        )
        for fragment in required:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, content)
        self.assertNotIn("response.text()", content)

    def test_local_csrf_nonce_is_ephemeral_and_not_extension_data(self) -> None:
        content = (EXTENSION / "content" / "content_script.js").read_text(
            encoding="utf-8"
        )
        self.assertEqual(content.count('meta[name="ssa-csrf-token"]'), 1)
        self.assertEqual(content.count('"X-SSA-CSRF-Token"'), 1)
        for fragment in (
            "document.querySelectorAll('meta[name=\"ssa-csrf-token\"]')",
            "metas.length !== 1",
            "LOWER_SHA256.test(metas[0].content)",
            'credentials: "omit"',
            '"X-SSA-CSRF-Token": metas[0].content',
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, content)
        for relative in (
            "service_worker.js",
            "shared/contracts.js",
            "side_panel/panel.js",
        ):
            source = (EXTENSION / relative).read_text(encoding="utf-8").casefold()
            with self.subTest(relative=relative):
                self.assertNotIn("csrf", source)

    def test_panel_serializes_operations_and_ignores_stale_responses(self) -> None:
        panel = (EXTENSION / "side_panel" / "panel.js").read_text(encoding="utf-8")
        required = (
            "let inFlight = false",
            "let operationGeneration = 0",
            "if (inFlight) return null",
            "inFlight = true",
            "operationGeneration += 1",
            "elements.evaluate.disabled = inFlight",
            "elements.refresh.disabled = inFlight",
            "elements.retry.disabled = inFlight",
            "function finishOperation(generation, response)",
            "if (generation !== operationGeneration) return",
            "inFlight = false",
            "const generation = beginOperation(",
            "finishOperation(generation, response)",
        )
        for fragment in required:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, panel)

    def test_message_replies_are_validated_and_state_bound(self) -> None:
        contracts = (EXTENSION / "shared" / "contracts.js").read_text(
            encoding="utf-8"
        )
        for code in (
            "RESPONSE_RESULT_BINDING_INVALID",
            "RESPONSE_READY_BINDING_INVALID",
            "RESPONSE_UNSUPPORTED_BINDING_INVALID",
            "RESPONSE_UNHEALTHY_BINDING_INVALID",
            "RESPONSE_OFFLINE_BINDING_INVALID",
            "RESPONSE_CONFLICT_BINDING_INVALID",
            "RESPONSE_SOURCE_FAILURE_BINDING_INVALID",
            "RESPONSE_ERROR_CODE_REQUIRED",
            "RESPONSE_EVALUATING_PROHIBITED",
        ):
            with self.subTest(code=code):
                self.assertIn(code, contracts)
        worker = (EXTENSION / "service_worker.js").read_text(encoding="utf-8")
        panel = (EXTENSION / "side_panel" / "panel.js").read_text(encoding="utf-8")
        self.assertIn(".then(contracts.validateResponse)", worker)
        self.assertGreaterEqual(panel.count("contracts.validateResponse("), 2)

    def test_unknown_governed_dom_field_names_are_not_prefix_admitted(self) -> None:
        extraction = (EXTENSION / "shared" / "extraction.js").read_text(
            encoding="utf-8"
        )
        required = (
            "const completenessFields = new Set(",
            "allowlist.completeness.map((member) => `completeness.${member}`)",
            "const lineFields = new Set(allowlist.line.map((member) => `line.${member}`))",
            "accepts: (name) => completenessFields.has(name)",
            'accepts: (name) => name === "line-universe-end" || lineFields.has(name)',
            "const interactionFields = new Set(",
            ".filter((member) => member !== \"schema_version\")",
            ".map((member) => `interaction.${member}`)",
            "accepts: (name) => interactionFields.has(name)",
            'fail("GOVERNED_FIELD_MISPLACED", "DOM_PAYLOAD_MISMATCH")',
        )
        for fragment in required:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, extraction)
        for prohibited in (
            'name.startsWith("completeness.")',
            'name.startsWith("line.")',
            'name.startsWith("interaction.")',
        ):
            self.assertNotIn(prohibited, extraction)

    def test_line_end_marker_counts_all_descendants_and_is_direct_child(self) -> None:
        extraction = (EXTENSION / "shared" / "extraction.js").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "section.querySelectorAll(\n"
            "      '[data-ssa-field=\"line-universe-end\"]'\n"
            "    )",
            extraction,
        )
        self.assertIn(
            "markerMatches.length !== 1 || "
            "markerMatches[0].parentElement !== section",
            extraction,
        )
        self.assertNotIn(
            "section.querySelectorAll(':scope > "
            "[data-ssa-field=\"line-universe-end\"]')",
            extraction,
        )

    def test_null_manifest_digest_has_one_exact_dom_spelling(self) -> None:
        extraction = (EXTENSION / "shared" / "extraction.js").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            'const digestText = result.ordered_line_manifest_digest === null ? "None"',
            extraction,
        )
        self.assertIn("if (digestAttribute !== digestText) {", extraction)
        self.assertNotIn(
            "digestAttribute !== String(result.ordered_line_manifest_digest)",
            extraction,
        )

    def test_html_has_no_inline_script_style_or_remote_asset(self) -> None:
        violations: list[str] = []
        for path in sorted(EXTENSION.rglob("*.html")):
            parser = _LocalHtmlAudit()
            parser.feed(path.read_text(encoding="utf-8"))
            violations.extend(
                f"{path.relative_to(ROOT).as_posix()}:{item}"
                for item in parser.violations
            )
            for resource in parser.resources:
                resolved = (path.parent / resource).resolve()
                if (
                    not resolved.is_relative_to(EXTENSION.resolve())
                    or not resolved.is_file()
                ):
                    violations.append(
                        f"{path.relative_to(ROOT).as_posix()}:resource-boundary"
                    )
        self.assertEqual(violations, [])

    def test_tab_api_is_message_only_and_needs_no_tabs_permission(self) -> None:
        methods: set[str] = set()
        for path in sorted(EXTENSION.rglob("*.js")):
            methods.update(
                re.findall(
                    r"\bchrome\.tabs\.([A-Za-z][A-Za-z0-9]*)\s*\(",
                    path.read_text(encoding="utf-8"),
                )
            )
        self.assertEqual(methods, {"query", "sendMessage"})
        manifest = json.loads((EXTENSION / "manifest.json").read_text(encoding="utf-8"))
        self.assertNotIn("tabs", manifest["permissions"])

    def test_repository_scanner_reaudits_the_extension_input_boundary(self) -> None:
        self.assertEqual(scan_prohibited_repository_content(ROOT), ())

    def test_m7_artifact_inventory_remains_zero(self) -> None:
        forbidden_parts = {
            "connector",
            "connectors",
            "control-center",
            "control_center",
            "dashboard",
            "milestone7",
        }
        violations = [
            path.relative_to(ROOT).as_posix()
            for root_name in ("src", "chrome_extension")
            for path in (ROOT / root_name).rglob("*")
            if path.name.lower() in forbidden_parts
        ]
        self.assertEqual(violations, [])
        self.assertEqual(
            {path.name for path in (ROOT / "migrations").iterdir() if path.is_file()},
            {
                "0001_foundation.sql",
                "0002_shared_persistence.sql",
                "0003_sales_credit_persistence.sql",
                "0004_doi_persistence.sql",
            },
        )


if __name__ == "__main__":
    unittest.main()
