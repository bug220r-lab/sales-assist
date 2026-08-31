from __future__ import annotations

import ast
import unittest
from pathlib import Path

from synthetic_sales_assist.application import (
    ordered_line_manifest_digest_from_mappings,
)
from synthetic_sales_assist.domain.canonical import canonical_json_bytes
from synthetic_sales_assist.safety.repository import (
    AUTHORED_M5_MARKER,
    AUTHORED_M5_PORTAL_ROOTS,
    AUTHORED_M5_SCRIPT_PATHS,
    scan_prohibited_repository_content,
)


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "synthetic_sales_assist"
PORTAL = PACKAGE / "portal"
SCRIPTS = ROOT / "scripts"

EXTERNAL_CLIENT_IMPORTS = {
    "aiohttp",
    "ftplib",
    "http.client",
    "httpx",
    "requests",
    "smtplib",
    "urllib.request",
    "websocket",
    "websockets",
}
DIRECT_RULE_PACK_PREFIXES = (
    "synthetic_sales_assist.demos",
    "synthetic_sales_assist.doi",
    "synthetic_sales_assist.durable_demo_backend",
    "synthetic_sales_assist.sales_credit",
)

KNOWN_ANSWER_DIGEST = (
    "6cd6f84917dcddcd376f9c835a2087f0a94390aca6939174c78c343c229c454f"
)
KNOWN_ANSWER_LINE = {
    "activity": {"reason_code": None, "tag": "KNOWN", "value": "ACTIVE"},
    "availability": {"reason_code": None, "tag": "KNOWN", "value": "IN_STOCK"},
    "drop_ship_state": {"reason_code": None, "tag": "KNOWN", "value": "NON_DS"},
    "eta": {
        "reason_code": None,
        "tag": "KNOWN",
        "value": "2026-08-22T12:00:00Z",
    },
    "line_id": "SYN-EVIDENCE-PORTAL-LINE-0001",
    "line_index": 1,
    "line_value": {
        "reason_code": None,
        "tag": "KNOWN",
        "value": {
            "amount": "10.00",
            "currency_code": "USD",
            "currency_registry_version": "synthetic-iso-style-currency-registry/v1",
            "currency_scale": 2,
        },
    },
    "product_id": "SYN-SKU-PORTAL-0001",
    "quantity": {"reason_code": None, "tag": "KNOWN", "value": "1"},
}
KNOWN_ANSWER_PAYLOAD = {
    "completeness": {
        "declared_relevant_line_count": 1,
        "fixture_version": "shared-fixture/v1",
        "observed_order_id": "SYN-ORDER-PORTAL-0001",
        "ordered_line_manifest_digest": KNOWN_ANSWER_DIGEST,
        "rendered_relevant_line_count": 1,
        "requested_order_id": "SYN-ORDER-PORTAL-0001",
        "source_observed_at": "2026-08-21T12:00:00Z",
        "source_schema_version": "shared-whole-order-completeness/v1",
        "state": "COMPLETE",
    },
    "lines": [KNOWN_ANSWER_LINE],
    "mode": "complete",
    "order_id": "SYN-ORDER-PORTAL-0001",
    "scenario_alias": "doi-overlap",
    "schema_version": "synthetic-sales-assist-dom/v1",
    "source_status": "COMPLETE",
}


def _imports(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.append(node.module or "")
    return tuple(names)


class Milestone5BoundaryTests(unittest.TestCase):
    def test_dom_contract_known_answer_payload_and_digest_are_exact(self) -> None:
        self.assertEqual(
            ordered_line_manifest_digest_from_mappings([KNOWN_ANSWER_LINE]),
            KNOWN_ANSWER_DIGEST,
        )
        canonical = canonical_json_bytes(KNOWN_ANSWER_PAYLOAD).decode("utf-8")
        document = (ROOT / "docs" / "milestone5-dom-contract.md").read_text(
            encoding="utf-8"
        )
        self.assertIn(canonical, document)
        self.assertIn(KNOWN_ANSWER_DIGEST, document)

    def test_schema_four_and_migration_inventory_remain_exact(self) -> None:
        migrations = ROOT / "migrations"
        self.assertEqual(
            {path.name for path in migrations.iterdir() if path.is_file()},
            {
                "0001_foundation.sql",
                "0002_shared_persistence.sql",
                "0003_sales_credit_persistence.sql",
                "0004_doi_persistence.sql",
            },
        )

    def test_authored_milestone5_surface_is_path_exact_and_milestone6_stays_absent(
        self,
    ) -> None:
        self.assertTrue(PORTAL.is_dir())
        permitted_suffixes = {".css", ".html", ".js", ".py"}
        violations: list[str] = []
        for path in PORTAL.rglob("*"):
            if not path.is_file() or path.name.endswith((".pyc", ".pyo")):
                continue
            relative = path.relative_to(ROOT).as_posix()
            if path.suffix.lower() not in permitted_suffixes:
                violations.append(relative)
            if path.suffix.lower() in {".css", ".html", ".js"}:
                text = path.read_text(encoding="utf-8")
                if AUTHORED_M5_MARKER not in text[:8192]:
                    violations.append(relative + ":marker")
        self.assertEqual(violations, [])

        forbidden_parts = {
            "automation",
            "browser",
            "chrome_extension",
            "connector",
            "control-center",
            "control_center",
            "dashboard",
            "extension",
            "milestone6",
        }
        capability_paths = [
            path.relative_to(ROOT).as_posix()
            for path in (ROOT / "src").rglob("*")
            if path.name.lower() in forbidden_parts
        ]
        self.assertEqual(capability_paths, [])
        manifests = [
            path.relative_to(ROOT).as_posix()
            for path in ROOT.rglob("manifest.json")
            if ".git" not in path.parts and "__pycache__" not in path.parts
        ]
        self.assertEqual(manifests, [])

    def test_portal_has_no_external_client_or_direct_rule_pack_import(self) -> None:
        violations: list[str] = []
        for path in sorted(PORTAL.rglob("*.py")):
            for imported in _imports(path):
                if imported in EXTERNAL_CLIENT_IMPORTS:
                    violations.append(f"{path.name}:external:{imported}")
                if any(
                    imported == prefix or imported.startswith(prefix + ".")
                    for prefix in DIRECT_RULE_PACK_PREFIXES
                ):
                    violations.append(f"{path.name}:rule-pack:{imported}")
        self.assertEqual(violations, [])

    def test_repository_scanner_closes_unapproved_milestone5_content(self) -> None:
        self.assertEqual(scan_prohibited_repository_content(ROOT), ())

    def test_lifecycle_script_inventory_is_exact_and_non_elevating(self) -> None:
        paths = {
            path.relative_to(ROOT).as_posix()
            for path in SCRIPTS.rglob("*.ps1")
            if path.is_file()
        }
        self.assertEqual(paths, set(AUTHORED_M5_SCRIPT_PATHS))
        forbidden = (
            "#requires -runasadministrator",
            "-verb runas",
            "taskkill",
            "stop-process -name",
            "get-process -name python",
            "remove-item -recurse",
        )
        for relative in sorted(paths):
            text = (ROOT / relative).read_text(encoding="utf-8")
            lowered = text.lower()
            self.assertIn(AUTHORED_M5_MARKER, text[:4096])
            self.assertFalse(any(value in lowered for value in forbidden), relative)

        reset = (SCRIPTS / "reset-demo.ps1").read_text(encoding="utf-8")
        self.assertIn("ConfirmReset", reset)
        self.assertIn("'db', 'backup'", reset)
        self.assertIn("'db', 'verify', '--deep'", reset)
        self.assertLess(
            reset.index("Enter-SsaLifecycleOperationLock"),
            reset.index("'db', 'backup'"),
        )
        self.assertLess(
            reset.index("$stopOutput"),
            reset.index("$serviceMaintenanceLock = Enter-SsaLeaseCleanupLock"),
        )
        self.assertLess(
            reset.index("$serviceMaintenanceLock = Enter-SsaLeaseCleanupLock"),
            reset.index("$allowedRemovals"),
        )
        self.assertLess(
            reset.index("$allowedRemovals"),
            reset.index("-CommandArguments @('db', 'init')"),
        )
        stop = (SCRIPTS / "stop.ps1").read_text(encoding="utf-8")
        self.assertIn("Invoke-SsaOwnedShutdown", stop)
        start = (SCRIPTS / "start.ps1").read_text(encoding="utf-8")
        self.assertLess(
            start.index("Enter-SsaLifecycleOperationLock"),
            start.index("Start-Process"),
        )
        self.assertNotIn("@('db', 'init')", start)
        server = (PORTAL / "server.py").read_text(encoding="utf-8")
        self.assertLess(
            server.index("self.lease.acquire(self.process_identity_token)"),
            server.index("self.application = factory()"),
        )
        common = (SCRIPTS / "lifecycle-common.ps1").read_text(encoding="utf-8")
        self.assertIn("Enter-SsaLifecycleOperationLock", common)
        self.assertIn("PROCESS_LEASE_IDENTITY_MISMATCH", common)
        self.assertIn("Select-SsaPythonRuntime", common)
        self.assertIn("GetFinalPathNameByHandle", common)
        self.assertIn("PYTHON_VERSION_UNSUPPORTED", common)
        self.assertIn("PYTHON_CODEX_RUNTIME_REQUIRES_SSA_PYTHON", common)
        self.assertIn("X-SSA-CSRF-Token", common)
        self.assertIn("X-SSA-Shutdown-Token", common)
        self.assertNotIn("Get-CimInstance", common)
        self.assertNotIn("Get-WmiObject", common)

    def test_milestone4_acceptance_evidence_is_checksum_bound(self) -> None:
        path = ROOT / "docs" / "acceptance" / "milestone4-acceptance.md"
        text = path.read_text(encoding="utf-8")
        required = {
            "52b9a241d5ae7f3227c519dad18c2b3e9eab66ac",
            "af0e8f165a743a3c09ee20fbc84db900fbfbee20",
            "aa8d0b76e1a95d39524a0471bd919f6858e8f68cf057a8d471afb10d635215d8",
            "8978bf2d3b3e7124555e44f988aa8628ccac7fc01ba707a4e130aaa3789257df",
            "M4_MANUAL_ACCEPTANCE = PASS",
            "M4_OPERATOR_ACCEPTANCE_AUTOMATED = PASS",
        }
        self.assertTrue(all(item in text for item in required))

    def test_milestone5_contract_documents_are_versioned_and_closed(self) -> None:
        api = (ROOT / "docs" / "milestone5-api-contract.md").read_text(encoding="utf-8")
        dom = (ROOT / "docs" / "milestone5-dom-contract.md").read_text(encoding="utf-8")
        manual = (ROOT / "docs" / "milestone5-manual-acceptance.md").read_text(
            encoding="utf-8"
        )
        lifecycle = (ROOT / "docs" / "milestone5-service-lifecycle.md").read_text(
            encoding="utf-8"
        )
        development = (ROOT / "DEVELOPMENT.md").read_text(encoding="utf-8")
        adr = (
            ROOT / "docs" / "adr" / "0021-local-portal-api-dom-and-process-ownership.md"
        ).read_text(encoding="utf-8")
        self.assertIn("synthetic-sales-assist-api/v1", api)
        self.assertIn("synthetic-sales-assist-dom/v1", dom)
        for attribute in (
            "data-ssa-page-kind",
            "data-ssa-schema-version",
            "data-ssa-order-id",
            "data-ssa-interaction-id",
            "data-ssa-field",
            "data-ssa-line-id",
            "data-ssa-line-index",
            "data-ssa-completeness",
            "data-ssa-manifest-digest",
        ):
            self.assertIn(attribute, dom)
        self.assertIn("M5_MANUAL_ACCEPTANCE = PENDING", manual)
        for document in (manual, lifecycle, development, adr):
            self.assertIn("SSA_PYTHON", document)
            self.assertIn("DEVELOPMENT / NONPORTABLE", document)
            self.assertIn("portable release", document)
        self.assertIn("normal local non-reparse Python", lifecycle)
        self.assertIn("exact verified Codex primary-runtime location", lifecycle)
        self.assertIn("independent CSRF and shutdown tokens", adr)

    def test_windows_script_line_endings_are_declared(self) -> None:
        attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
        self.assertIn("/scripts/** text eol=crlf", attributes)


if __name__ == "__main__":
    unittest.main()
