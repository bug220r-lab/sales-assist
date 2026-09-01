from __future__ import annotations

import ast
import json
import pydoc
import re
import unittest
from pathlib import Path

from synthetic_sales_assist.application.control_center import (
    CONTROL_CENTER_SCHEMA_VERSION,
    DENOMINATOR_REGISTRY_VERSION,
    METRIC_DENOMINATOR_REGISTRY,
    ControlCenterApplication,
)
from synthetic_sales_assist.audit import audit_bundle
from synthetic_sales_assist.portal.dashboard_rendering import DASHBOARD_DOM_VERSION
from synthetic_sales_assist.portal.server import (
    EXPECTED_EXTENSION_PACKAGE_SHA256,
    EXPECTED_EXTENSION_VERSION,
    _DASHBOARD_API_GET_ROUTES,
    _DASHBOARD_HTML_ROUTES,
    _DASHBOARD_POST_ROUTES,
)


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_EXTENSION_SHA256 = (
    "595044d03c0aa843f7e751167b27b8d16de4cb8cf8fbc7064409f30e88ba885c"
)
REQUIRED_M7_DOCS = {
    "docs/acceptance/milestone6-acceptance.md",
    "docs/milestone7-accessibility-verification.md",
    "docs/milestone7-action-to-service-matrix.json",
    "docs/milestone7-action-to-service-matrix.md",
    "docs/milestone7-architecture-and-routes.md",
    "docs/milestone7-current-projection-history-contract.md",
    "docs/milestone7-dashboard-api-contract.md",
    "docs/milestone7-extension-status-semantics.md",
    "docs/milestone7-human-action-guide.md",
    "docs/milestone7-implementation-requirement-closure.md",
    "docs/milestone7-m8-evidence-surfaces.md",
    "docs/milestone7-manager-demo.md",
    "docs/milestone7-manual-acceptance.md",
    "docs/milestone7-metric-denominator-matrix.md",
    "docs/milestone7-pre-edit-attestation.md",
}


def _collected_test_methods() -> set[str]:
    return {
        node.name
        for path in (ROOT / "tests").glob("test_*.py")
        for node in ast.walk(
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        )
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    }


class Milestone7DocumentationTests(unittest.TestCase):
    def test_required_documents_exist_and_manual_acceptance_is_pending(self) -> None:
        missing = sorted(path for path in REQUIRED_M7_DOCS if not (ROOT / path).is_file())
        self.assertEqual(missing, [])
        manual = (ROOT / "docs/milestone7-manual-acceptance.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("M7_MANUAL_ACCEPTANCE = PENDING", manual)
        self.assertNotIn("M7_MANUAL_ACCEPTANCE = PASS", manual)

        pre_edit = (ROOT / "docs/milestone7-pre-edit-attestation.md").read_text(
            encoding="utf-8"
        )
        for value in (
            "1ff8198e19af7cbcf9f153c36a66bcfef1c5a45f",
            "d07f75737eb6a5e891d002cea8a89c6d0d146c67",
            "acb0ff977e24d69a7d4fab0d1426ef5eba30c0d8ec9b86a1ab744a6b9319210d",
            "1,522/1,522 PASS",
            "M8 implementation/release artifacts | zero",
        ):
            self.assertIn(value, pre_edit)

    def test_all_ten_readiness_requirements_have_executable_closure(self) -> None:
        path = ROOT / "docs/milestone7-implementation-requirement-closure.md"
        text = path.read_text(encoding="utf-8")
        rows = [
            line
            for line in text.splitlines()
            if re.match(r"\| (?:10|[1-9]) \|", line)
        ]
        self.assertEqual(len(rows), 10)
        parsed: dict[int, list[str]] = {}
        referenced: set[str] = set()
        for row in rows:
            cells = [cell.strip() for cell in row.split("|")[1:-1]]
            self.assertEqual(len(cells), 5)
            number = int(cells[0])
            self.assertNotIn(number, parsed)
            self.assertEqual(cells[2], "`CLOSED_M7`")
            tests = set(re.findall(r"`(test_[a-z0-9_]+)`", cells[4]))
            self.assertTrue(tests)
            referenced.update(tests)
            parsed[number] = cells
        self.assertEqual(set(parsed), set(range(1, 11)))
        self.assertEqual(referenced - _collected_test_methods(), set())
        self.assertIn("M7_MANUAL_ACCEPTANCE = PENDING", text)
        self.assertNotIn("M7_MANUAL_ACCEPTANCE = PASS", text)

    def test_action_matrix_matches_rendered_mutation_surface(self) -> None:
        matrix_path = ROOT / "docs/milestone7-action-to-service-matrix.json"
        matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
        self.assertEqual(
            matrix["schema_version"],
            "synthetic-sales-assist-m7-action-service-matrix/v1",
        )
        actions = matrix["actions"]
        by_id = {action["action_id"]: action for action in actions}
        self.assertEqual(len(by_id), len(actions))
        supported = {
            "SUPPORTED_EXISTING_SERVICE",
            "SUPPORTED_BY_M7_THIN_ADAPTER",
            "SUPPORTED_READ_ONLY",
        }
        self.assertTrue(
            all(action["disposition"] in supported for action in actions if action["rendered"])
        )
        mutation_mapping = {
            "manager-outcome": "SALES_CREDIT_MANAGER_OUTCOME",
            "doi-scenario-selection": "DOI_SELECT_OVERLAP_SCENARIO",
            "database-verify": "SYSTEM_DATABASE_DEEP_VERIFY",
            "create-backup": "SYSTEM_CREATE_VERIFIED_BACKUP",
        }
        source = (
            ROOT / "src/synthetic_sales_assist/portal/dashboard_rendering.py"
        ).read_text(encoding="utf-8")
        rendered_actions = set(
            re.findall(r'data-ssa-dashboard-action="([a-z-]+)"', source)
        )
        self.assertEqual(rendered_actions, set(mutation_mapping))
        for selector, action_id in mutation_mapping.items():
            with self.subTest(selector=selector):
                action = by_id[action_id]
                self.assertTrue(action["rendered"])
                self.assertIn(action["disposition"], supported)
        for prohibited in (
            "resolve-attention",
            "verify-intervention",
            "link-resulting-order",
            "append-value",
            "generic-human-fact",
            'data-ssa-dashboard-action="restore"',
            'data-ssa-dashboard-action="reset"',
        ):
            self.assertNotIn(prohibited, source)
        for method in (
            "record_sales_credit_manager_outcome",
            "record_doi_overlap_selection",
            "deep_verify",
            "create_verified_backup",
        ):
            self.assertTrue(callable(getattr(ControlCenterApplication, method)))
        unresolved_symbols = {
            symbol
            for action in actions
            for symbol in action["service_symbols"]
            if pydoc.locate(symbol) is None
        }
        self.assertEqual(unresolved_symbols, set())
        collected = _collected_test_methods()
        referenced = {
            selector.rsplit(".", 1)[-1]
            for action in actions
            for selector in action["underlying_tests"]
        }
        self.assertEqual(referenced - collected, set())

    def test_denominator_documentation_reconciles_to_registry(self) -> None:
        self.assertEqual(
            DENOMINATOR_REGISTRY_VERSION,
            "synthetic-sales-assist-metric-denominators/v1",
        )
        expected = {
            "active_doi_opportunities",
            "active_sales_credit_cases",
            "backup_database_safety_status",
            "doi_state_distribution",
            "fail_closed_rate",
            "human_review_rate",
            "latency",
            "manager_outcome_rate",
            "opportunity_type_count",
            "potential_value",
            "realized_value",
            "requests_received",
            "successful_request_rate",
            "throughput",
            "unique_evaluations",
        }
        registry = {item.metric_id: item for item in METRIC_DENOMINATOR_REGISTRY}
        self.assertEqual(set(registry), expected)
        self.assertTrue(all(item.time_basis for item in registry.values()))
        self.assertTrue(all(item.empty_display for item in registry.values()))
        matrix = (ROOT / "docs/milestone7-metric-denominator-matrix.md").read_text(
            encoding="utf-8"
        )
        self.assertIn(DENOMINATOR_REGISTRY_VERSION, matrix)
        documented_rows = [
            line for line in matrix.splitlines() if line.startswith("| ")
        ][1:]
        self.assertEqual(len(documented_rows), 15)
        self.assertIn("Empty denominators render `N/A`", matrix)
        self.assertIn("No conversion or mixed-currency total", matrix)

    def test_route_selector_and_m8_evidence_traceability(self) -> None:
        architecture = (ROOT / "docs/milestone7-architecture-and-routes.md").read_text(
            encoding="utf-8"
        )
        for route in sorted(
            _DASHBOARD_HTML_ROUTES
            | _DASHBOARD_API_GET_ROUTES
            | _DASHBOARD_POST_ROUTES
        ):
            self.assertIn(f"`{route}`", architecture)
        for dynamic_route in (
            "/sales-credit/{case_id}",
            "/doi/{case_id}",
            "/audit/{subject_kind}/{subject_id}",
            "/api/v1/dashboard/sales-credit/{case_id}",
            "/api/v1/dashboard/doi/{case_id}",
            "/api/v1/dashboard/audit/{subject_kind}/{subject_id}",
        ):
            self.assertIn(f"`{dynamic_route}`", architecture)
        rendering = (
            ROOT / "src/synthetic_sales_assist/portal/dashboard_rendering.py"
        ).read_text(encoding="utf-8")
        selectors = set(re.findall(r"data-ssa-dashboard-([a-z-]+)", rendering))
        self.assertTrue(
            {
                "action",
                "card",
                "current-projection",
                "id",
                "live-region",
                "page",
                "presentation",
                "schema-version",
                "state",
                "status",
                "table",
                "timeline",
            }.issubset(selectors)
        )
        evidence = (ROOT / "docs/milestone7-m8-evidence-surfaces.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("/api/v1/dashboard/evidence", evidence)
        self.assertIn("synthetic-sales-assist-m8-evidence-surfaces/v1", evidence)
        self.assertIn("data-ssa-dashboard-*", evidence)
        self.assertIn("does not implement Milestone 8", evidence)
        self.assertEqual(
            CONTROL_CENTER_SCHEMA_VERSION,
            "synthetic-sales-assist-control-center/v1",
        )
        self.assertEqual(DASHBOARD_DOM_VERSION, "synthetic-sales-assist-dashboard-dom/v1")

    def test_milestone_seven_schema_and_protected_bundle_are_unchanged(self) -> None:
        migrations = sorted(path.name for path in (ROOT / "migrations").glob("*.sql"))
        self.assertEqual(
            migrations,
            [
                "0001_foundation.sql",
                "0002_shared_persistence.sql",
                "0003_sales_credit_persistence.sql",
                "0004_doi_persistence.sql",
            ],
        )
        report = audit_bundle(ROOT)
        self.assertEqual(report.checksum_entries, 66)
        self.assertEqual(report.manifest_entries, 65)
        self.assertEqual(report.specification_files, 34)
        self.assertEqual(report.reference_files, 28)

    def test_extension_development_identity_is_exact(self) -> None:
        manifest = json.loads(
            (ROOT / "chrome_extension/manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["manifest_version"], 3)
        self.assertEqual(manifest["version"], "0.1.1")
        self.assertEqual(manifest["permissions"], ["sidePanel"])
        self.assertEqual(
            manifest["host_permissions"],
            ["http://127.0.0.1/*", "http://localhost/*"],
        )
        self.assertEqual(EXPECTED_EXTENSION_VERSION, "0.1.1")
        self.assertEqual(EXPECTED_EXTENSION_PACKAGE_SHA256, EXPECTED_EXTENSION_SHA256)
        development = (ROOT / "DEVELOPMENT.md").read_text(encoding="utf-8")
        self.assertIn("version = 0.1.1", development)
        self.assertIn(EXPECTED_EXTENSION_SHA256, development)
        self.assertIn("database schema remains version `4`", development.casefold())
        self.assertIn("M7_MANUAL_ACCEPTANCE = PENDING", development)

    def test_milestone_eight_release_artifacts_are_absent(self) -> None:
        self.assertEqual(list((ROOT / "tasks").glob("milestone8*")), [])
        for name in (
            "release",
            "releases",
            "installer",
            "installers",
            "dist",
            "portable",
        ):
            self.assertFalse((ROOT / name).exists(), name)
        evidence = ROOT / "docs/milestone7-m8-evidence-surfaces.md"
        self.assertTrue(evidence.is_file())
        text = evidence.read_text(encoding="utf-8")
        for absent in (
            "M8_MANUAL_ACCEPTANCE = PASS",
            "MILESTONE_8 = PASS",
            "MILESTONE_8_RELEASE = PASS",
        ):
            self.assertNotIn(absent, text)


if __name__ == "__main__":
    unittest.main()
