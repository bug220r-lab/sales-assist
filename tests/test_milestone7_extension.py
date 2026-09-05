"""Focused Milestone 7 tests for the minimal no-new-permission extension delta."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import types
import unittest
from html.parser import HTMLParser
from pathlib import Path

from synthetic_sales_assist.safety.chrome import (
    ALLOWED_CHROME_API_PERMISSIONS,
    ALLOWED_CHROME_CONTENT_MATCH_PATTERNS,
    ALLOWED_CHROME_HOST_PATTERNS,
    CHROME_EXTENSION_VERSION,
    EXTENSION_PAGE_CSP,
    validate_chrome_permissions,
)


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


class _AnchorInventory(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.anchors: dict[str, dict[str, str | None]] = {}

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        attributes = dict(attrs)
        if tag == "a" and isinstance(attributes.get("id"), str):
            self.anchors[str(attributes["id"])] = attributes


class Milestone7ExtensionTests(unittest.TestCase):
    @staticmethod
    def _packager() -> types.ModuleType:
        path = ROOT / "tools" / "package_milestone6_extension.py"
        name = "_synthetic_sales_assist_m7_extension_packager_test"
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise AssertionError("extension packager module could not be loaded")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module

    def test_patch_version_and_permission_surface_are_exact(self) -> None:
        manifest = json.loads((EXTENSION / "manifest.json").read_text("utf-8"))
        inventory = validate_chrome_permissions(manifest)
        self.assertEqual(manifest["manifest_version"], 3)
        self.assertEqual(manifest["version"], "0.1.2")
        self.assertEqual(CHROME_EXTENSION_VERSION, "0.1.2")
        self.assertEqual(set(inventory.api_permissions), ALLOWED_CHROME_API_PERMISSIONS)
        self.assertEqual(set(inventory.host_permissions), ALLOWED_CHROME_HOST_PATTERNS)
        self.assertEqual(
            set(inventory.match_surfaces[0][1]),
            ALLOWED_CHROME_CONTENT_MATCH_PATTERNS,
        )
        self.assertEqual(manifest["permissions"], ["sidePanel"])
        self.assertEqual(
            manifest["host_permissions"],
            ["http://127.0.0.1/*", "http://localhost/*"],
        )
        self.assertEqual(
            manifest["content_security_policy"]["extension_pages"],
            EXTENSION_PAGE_CSP,
        )
        for member in (
            "optional_permissions",
            "optional_host_permissions",
            "web_accessible_resources",
        ):
            self.assertNotIn(member, manifest)

    def test_handshake_request_and_response_contracts_are_closed(self) -> None:
        contracts = (EXTENSION / "shared" / "contracts.js").read_text("utf-8")
        content = (EXTENSION / "content" / "content_script.js").read_text("utf-8")
        self.assertIn(
            'const HANDSHAKE_SCHEMA_VERSION = '
            '"synthetic-sales-assist-extension-handshake/v1";',
            contracts,
        )
        self.assertIn('const EXTENSION_VERSION = "0.1.2";', contracts)
        self.assertIn(
            'const HANDSHAKE_PATH = "/api/v1/system/extension/handshake";',
            content,
        )
        self.assertIn(
            "canonical.exactMembers(data, HANDSHAKE_MEMBERS, "
            '"HANDSHAKE_MEMBERS_INVALID")',
            content,
        )
        for member in (
            "expected_extension_version",
            "last_seen_at",
            "observed_extension_version",
            "stale_after_seconds",
            "status",
        ):
            self.assertIn(f'"{member}"', content)
        for fragment in (
            'extension_version: contracts.EXTENSION_VERSION',
            'schema_version: contracts.HANDSHAKE_SCHEMA_VERSION',
            '["LAST_SEEN_HEALTHY", "VERSION_MISMATCH"]',
            "data.stale_after_seconds !== 300",
            'extractionModule.validateTimestamp(data.last_seen_at, '
            '"HANDSHAKE_TIMESTAMP_INVALID")',
            '{body, headers: localCsrfHeaders(), method: "POST"}',
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, content)
        self.assertEqual(content.count('meta[name="ssa-csrf-token"]'), 1)
        self.assertEqual(content.count('"X-SSA-CSRF-Token"'), 1)
        self.assertEqual(content.count("fetch("), 1)

    def test_handshake_is_event_bound_and_never_polled(self) -> None:
        panel = (EXTENSION / "side_panel" / "panel.js").read_text("utf-8")
        content = (EXTENSION / "content" / "content_script.js").read_text("utf-8")
        page_state = content.split("async function pageState()", 1)[1].split(
            "async function evaluateObserved", 1
        )[0]
        evaluation = content.split("async function evaluateObserved", 1)[1]
        self.assertEqual(page_state.count("await extensionHandshake(extraction.origin)"), 1)
        self.assertNotIn("extensionHandshake(", evaluation)
        self.assertIn('elements.refresh.addEventListener("click", refresh)', panel)
        self.assertTrue(panel.rstrip().endswith("refresh();\n})();"))
        for source in (panel, content):
            self.assertNotIn("setInterval", source)
            self.assertNotIn("requestAnimationFrame", source)
        self.assertNotIn("chrome.alarms", content)

    def test_closed_dashboard_url_builder_accepts_only_loopback_routes_and_ids(
        self,
    ) -> None:
        node = _node_executable()
        if node is None:
            self.skipTest("Node.js runtime unavailable")
        script = r"""
const path = require("node:path");
const root = process.argv[1];
require(path.join(root, "shared/canonical.js"));
require(path.join(root, "shared/contracts.js"));
require(path.join(root, "shared/origin.js"));
const O = globalThis.SSA.Origin;
const valid = [
  ["http://127.0.0.1:8765", "OVERVIEW", null,
    "http://127.0.0.1:8765/overview"],
  ["http://localhost:8765", "SYSTEM", null,
    "http://localhost:8765/system"],
  ["http://127.0.0.1:8765", "REVIEW", null,
    "http://127.0.0.1:8765/review"],
  ["http://127.0.0.1:8765", "ORDER", "SYN-ORDER-LINK-1",
    "http://127.0.0.1:8765/orders/SYN-ORDER-LINK-1"],
  ["http://127.0.0.1:8765", "SALES_CREDIT_CASE", "SYN-ORDER-LINK-1",
    "http://127.0.0.1:8765/sales-credit/SYN-ORDER-LINK-1"],
  ["http://127.0.0.1:8765", "DOI_CASE", "SYN-EVIDENCE-CASE-1",
    "http://127.0.0.1:8765/doi/SYN-EVIDENCE-CASE-1"],
  ["http://127.0.0.1:8765", "EVALUATION_AUDIT", "SYN-EVALUATION-LINK-1",
    "http://127.0.0.1:8765/audit/evaluation/SYN-EVALUATION-LINK-1"]
];
for (const item of valid) {
  if (O.dashboardUrl(item[0], item[1], item[2]) !== item[3]) {
    throw new Error("VALID_DASHBOARD_LINK_REJECTED");
  }
}
const invalid = [
  ["https:" + "/".repeat(2) + "127.0.0.1:8765", "OVERVIEW", null],
  ["http://127.0.0.1:8766", "OVERVIEW", null],
  ["http:" + "/".repeat(2) + "user" + "@" + "127.0.0.1:8765", "SYSTEM", null],
  ["http://127.0.0.1:8765?next=/overview", "OVERVIEW", null],
  ["http://127.0.0.1:8765", "ARBITRARY", null],
  ["http://127.0.0.1:8765", "ORDER", "REAL-ORDER-1"],
  ["http://127.0.0.1:8765", "ORDER", "SYN-ORDER-LINK-1/telemetry"],
  ["http://127.0.0.1:8765", "DOI_CASE", "SYN-ORDER-LINK-1"],
  ["http://127.0.0.1:8765", "EVALUATION_AUDIT", "SYN-EVIDENCE-LINK-1"]
];
for (const item of invalid) {
  let rejected = false;
  try { O.dashboardUrl(item[0], item[1], item[2]); }
  catch (_error) { rejected = true; }
  if (!rejected) throw new Error("UNSAFE_DASHBOARD_LINK_ACCEPTED");
}
"""
        completed = subprocess.run(
            [str(node), "-e", script, str(EXTENSION)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_panel_link_inventory_is_closed_and_nonprivileged(self) -> None:
        parser = _AnchorInventory()
        parser.feed((EXTENSION / "side_panel" / "index.html").read_text("utf-8"))
        expected = {
            "audit-link",
            "case-link",
            "history-link",
            "overview-link",
            "review-link",
            "system-link",
        }
        self.assertEqual(set(parser.anchors), expected)
        for anchor in parser.anchors.values():
            self.assertNotIn("href", anchor)
            self.assertEqual(anchor.get("target"), "_blank")
            self.assertEqual(anchor.get("rel"), "noreferrer")
            self.assertIn("hidden", anchor)
        panel = (EXTENSION / "side_panel" / "panel.js").read_text("utf-8")
        self.assertIn("originPolicy.dashboardUrl(origin, kind, identifier)", panel)
        self.assertIn(
            '!["order-detail", "interaction-detail"].includes(data.page_kind)', panel
        )
        for kind in (
            "OVERVIEW",
            "SYSTEM",
            "ORDER",
            "SALES_CREDIT_CASE",
            "DOI_CASE",
            "EVALUATION_AUDIT",
            "REVIEW",
        ):
            self.assertIn(f'"{kind}"', panel)
        for prohibited in (
            "window.open",
            "chrome.tabs.create",
            "chrome.tabs.update",
            "localStorage",
            "sessionStorage",
        ):
            self.assertNotIn(prohibited, panel)

    def test_m6_extraction_runtime_and_message_partition_are_unchanged(self) -> None:
        unchanged = {
            "service_worker.js": "4d7f471720d6a1d22e67ab6e944abe6ab6138f4c52f06004f37497a84d1ae7b0",
            "shared/canonical.js": (
                "3937612403f1e021d877fab047ecd44524c27ce854fd7354a6398599e1e7a8d7"
            ),
            "shared/extraction.js": (
                "f4dde4464a764a4bfedb20a4c091033e6af228bcde16ae08ac8ab8d9e85f2e9c"
            ),
        }
        for relative, digest in unchanged.items():
            with self.subTest(relative=relative):
                self.assertEqual(
                    hashlib.sha256((EXTENSION / relative).read_bytes()).hexdigest(),
                    digest,
                )
        contracts = (EXTENSION / "shared" / "contracts.js").read_text("utf-8")
        self.assertIn(
            'const MESSAGE_KINDS = Object.freeze(["GET_PAGE_STATE", "EVALUATE"]);',
            contracts,
        )

    def test_current_package_inventory_and_deterministic_bytes_are_exact(self) -> None:
        packager = self._packager()
        manifest = packager.check_package()
        self.assertEqual(manifest["version"], "0.1.2")
        snapshot = packager._snapshot_files()
        first = packager._zip_bytes(snapshot)
        second = packager._zip_bytes(snapshot)
        self.assertEqual(first, second)
        self.assertEqual(hashlib.sha256(first).hexdigest(), hashlib.sha256(second).hexdigest())


if __name__ == "__main__":
    unittest.main()
