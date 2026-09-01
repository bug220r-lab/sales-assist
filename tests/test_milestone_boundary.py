from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

import synthetic_sales_assist.domain.registries as registry_module
import synthetic_sales_assist.domain as domain_package
from synthetic_sales_assist.safety.repository import (
    AUTHORED_M5_MARKER,
    AUTHORED_M5_PORTAL_ROOTS,
    AUTHORED_M5_PORTAL_SUFFIXES,
)


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "synthetic_sales_assist"
FORBIDDEN_FEATURE_NAMES = {
    "chrome_extension",
    "connector",
    "control_center",
    "dashboard",
    "extension",
    "milestone6",
    "rules_engine",
}
ALLOWED_DOMAIN_MODULES = {
    "__init__.py",
    "canonical.py",
    "identities.py",
    "idempotency.py",
    "normalization.py",
    "numeric.py",
    "observed.py",
    "records.py",
    "registries.py",
    "timestamps.py",
    "tokens.py",
}
NETWORK_CLIENT_IMPORTS = {
    "aiohttp",
    "ftplib",
    "http.client",
    "httpx",
    "requests",
    "smtplib",
    "socket",
    "urllib.request",
}
M5_LOOPBACK_SERVER = "src/synthetic_sales_assist/portal/server.py"


def _network_client_violations(source: str, relative: str) -> list[str]:
    tree = ast.parse(source, filename=relative)
    violations: list[str] = []
    socket_imported = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = {alias.name for alias in node.names}
            exact_socket_import = any(
                alias.name == "socket" and alias.asname is None for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom):
            names = {node.module or ""}
            exact_socket_import = False
        else:
            continue
        socket_imported = socket_imported or "socket" in names
        blocked = names & NETWORK_CLIENT_IMPORTS
        if (
            "socket" in blocked
            and relative == M5_LOOPBACK_SERVER
            and exact_socket_import
        ):
            blocked.remove("socket")
        if blocked:
            violations.append(f"{relative}:{node.lineno}:import:{sorted(blocked)}")

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        direct_socket_call = (
            isinstance(node.func.value, ast.Name)
            and node.func.value.id == "socket"
            and node.func.attr in {"create_connection", "socket"}
        )
        socket_connect_call = socket_imported and node.func.attr in {
            "connect",
            "connect_ex",
        }
        if direct_socket_call or socket_connect_call:
            violations.append(
                f"{relative}:{node.lineno}:socket-client-call:{node.func.attr}"
            )
    return violations


class MilestoneBoundaryTests(unittest.TestCase):
    def test_audit_finding_closure_matrix_is_complete(self) -> None:
        matrix_path = ROOT / "docs" / "audit-finding-closure-matrix.md"
        self.assertTrue(matrix_path.is_file())
        matrix_text = matrix_path.read_text(encoding="utf-8")
        self.assertIn("- Matrix version: `milestone7/v1`", matrix_text)
        self.assertNotIn("| DEFERRED |", matrix_text)
        self.assertNotIn("| PARTIAL |", matrix_text)
        rows = [
            line
            for line in matrix_text.splitlines()
            if line.startswith("| R01-") or line.startswith("| R02-")
        ]
        expected = {
            *(f"R01-{index:02d}" for index in range(1, 17)),
            *(f"R02-{index:02d}" for index in range(1, 4)),
        }
        parsed: dict[str, list[str]] = {}
        for row in rows:
            cells = [cell.strip() for cell in row.split("|")[1:-1]]
            self.assertEqual(len(cells), 8)
            self.assertTrue(all(cells))
            self.assertNotIn(cells[0], parsed)
            parsed[cells[0]] = cells
        self.assertEqual(set(parsed), expected)
        self.assertTrue(all(cells[1] == "CLOSED_M6" for cells in parsed.values()))
        m7_rows = [
            line
            for line in matrix_text.splitlines()
            if line.startswith("| M7-R01-") or line.startswith("| M7-R02-")
        ]
        m7_parsed: dict[str, list[str]] = {}
        for row in m7_rows:
            cells = [cell.strip() for cell in row.split("|")[1:-1]]
            self.assertEqual(len(cells), 4)
            self.assertTrue(all(cells))
            self.assertNotIn(cells[0], m7_parsed)
            m7_parsed[cells[0]] = cells
        self.assertEqual(
            set(m7_parsed),
            {f"M7-{finding}" for finding in expected},
        )
        self.assertTrue(
            all(cells[1] == "CLOSED_M7" for cells in m7_parsed.values())
        )
        collected_methods = {
            node.name
            for path in (ROOT / "tests").glob("test_*.py")
            for node in ast.walk(
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            )
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
        }
        m6_methods = {
            node.name
            for path in (ROOT / "tests").glob("test_milestone6*.py")
            for node in ast.walk(
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            )
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
        }
        referenced = set(re.findall(r"`(test_[a-z0-9_]+)`", matrix_text))
        self.assertTrue(referenced)
        self.assertEqual(referenced - collected_methods, set())
        for finding, cells in parsed.items():
            with self.subTest(finding=finding):
                accepted = set(re.findall(r"`(test_[a-z0-9_]+)`", cells[4]))
                self.assertTrue(accepted & m6_methods)
                self.assertIn("ADR 0022", cells[3])
        m7_methods = {
            node.name
            for path in (ROOT / "tests").glob("test_milestone7*.py")
            for node in ast.walk(
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            )
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
        }
        for finding, cells in m7_parsed.items():
            with self.subTest(m7_finding=finding):
                accepted = set(re.findall(r"`(test_[a-z0-9_]+)`", cells[3]))
                self.assertTrue(accepted)
                self.assertTrue(accepted <= m7_methods)
        for adr in ("ADR 0023", "ADR 0024", "ADR 0025", "ADR 0026"):
            self.assertIn(adr, matrix_text)
        self.assertIn("M7_MANUAL_ACCEPTANCE = PENDING", matrix_text)

    def test_public_domain_facade_exports_every_declared_shared_type(self) -> None:
        exported = domain_package.__all__
        self.assertEqual(len(exported), len(set(exported)))
        self.assertTrue(all(hasattr(domain_package, name) for name in exported))
        required = {
            "DomainRecordError",
            "ErrorPathMember",
            "EvaluationExplanationItem",
            "NonNegativeCount",
            "PositiveOrdinal",
            "RequiredSectionProof",
            "SourceKind",
            "StructuredErrorCode",
            "WholeOrderCompletenessProof",
        }
        self.assertTrue(required.issubset(exported))

    def test_milestone_seven_dashboard_connector_and_embedded_extension_are_absent(
        self,
    ) -> None:
        domain = PACKAGE / "domain"
        discovered = {path.stem for path in domain.rglob("*.py")}
        discovered.update(path.name for path in domain.iterdir() if path.is_dir())
        self.assertFalse(discovered & FORBIDDEN_FEATURE_NAMES)

    def test_milestone_five_and_user_interface_modules_are_absent(self) -> None:
        """Preserve the old selector while advancing its prohibited-capability boundary."""

        self.test_milestone_seven_dashboard_connector_and_embedded_extension_are_absent()

    def test_milestone_four_and_user_interface_modules_are_absent(self) -> None:
        """Preserve the Milestone 3 boundary oracle name."""

        self.test_milestone_seven_dashboard_connector_and_embedded_extension_are_absent()

    def test_milestone_three_and_user_interface_modules_are_absent(self) -> None:
        """Preserve the Milestone 2 oracle ID at the advanced milestone boundary."""

        self.test_milestone_seven_dashboard_connector_and_embedded_extension_are_absent()

    def test_package_has_no_network_client_import(self) -> None:
        violations: list[str] = []
        for path in sorted(PACKAGE.rglob("*.py")):
            relative = path.relative_to(ROOT).as_posix()
            violations.extend(
                _network_client_violations(
                    path.read_text(encoding="utf-8"),
                    relative,
                )
            )
        self.assertEqual(violations, [])

    def test_loopback_socket_import_does_not_allow_network_client_calls(self) -> None:
        canaries = {
            "socket-constructor": "import socket\nsocket.socket()\n",
            "create-connection": (
                "import socket\nsocket.create_connection(('127.0.0.1', 1))\n"
            ),
            "client-connect": "import socket\nclient.connect(('127.0.0.1', 1))\n",
        }
        for name, source in canaries.items():
            with self.subTest(name=name):
                violations = _network_client_violations(source, M5_LOOPBACK_SERVER)
                self.assertTrue(
                    any("socket-client-call" in item for item in violations),
                    violations,
                )

    def test_shared_domain_engine_has_an_exact_milestone_one_module_inventory(self) -> None:
        domain = PACKAGE / "domain"
        discovered = {path.name for path in domain.iterdir() if path.is_file()}
        self.assertEqual(discovered, ALLOWED_DOMAIN_MODULES)
        persistent_directories = [
            path for path in domain.iterdir() if path.is_dir() and path.name != "__pycache__"
        ]
        self.assertFalse(persistent_directories)

    def test_shared_domain_engine_has_no_database_or_sql_capability(self) -> None:
        violations: list[str] = []
        domain = PACKAGE / "domain"
        blocked_imports = {"sqlite3", "synthetic_sales_assist.persistence"}
        blocked_sql = ("CREATE TABLE", "INSERT INTO", "UPDATE ", "DELETE FROM")
        for path in sorted(domain.glob("*.py")):
            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text, filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = {alias.name for alias in node.names}
                elif isinstance(node, ast.ImportFrom):
                    names = {node.module or ""}
                else:
                    continue
                if any(
                    name in blocked_imports
                    or name.startswith("synthetic_sales_assist.persistence.")
                    for name in names
                ):
                    violations.append(f"{path.name}:{node.lineno}:database_import")
            upper = text.upper()
            if any(fragment in upper for fragment in blocked_sql):
                violations.append(f"{path.name}:sql_statement")
        self.assertEqual(violations, [])

    def test_milestone_one_registry_loading_is_bound_to_the_verified_checkout(self) -> None:
        self.assertEqual(registry_module.PROJECT_ROOT, ROOT)
        paths = (
            registry_module._REASON_PATH,
            registry_module._OWNERSHIP_PATH,
            registry_module._TRANSITION_PATH,
        )
        for path in paths:
            with self.subTest(path=path.name):
                resolved = path.resolve(strict=True)
                self.assertTrue(resolved.is_relative_to(ROOT))
                self.assertTrue(resolved.is_file())
                self.assertFalse(path.is_symlink())

    def test_no_business_migration_or_unapproved_user_interface_artifact_exists(self) -> None:
        """Admit only marked Milestone 5 portal assets; preserve schema version four."""

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
        implementation_roots = (ROOT / "src", ROOT / "tests", ROOT / "tools")
        forbidden_suffixes = {".html", ".js", ".jsx", ".ts", ".tsx"}
        artifacts: list[str] = []
        for base in implementation_roots:
            for path in base.rglob("*"):
                if not path.is_file():
                    continue
                relative = path.relative_to(ROOT).as_posix()
                suffix = path.suffix.lower()
                if path.name == "manifest.json":
                    artifacts.append(relative)
                    continue
                if suffix not in forbidden_suffixes:
                    continue
                approved_root = any(
                    relative == root or relative.startswith(root + "/")
                    for root in AUTHORED_M5_PORTAL_ROOTS
                )
                text = path.read_text(encoding="utf-8")
                if (
                    suffix not in AUTHORED_M5_PORTAL_SUFFIXES
                    or not approved_root
                    or AUTHORED_M5_MARKER not in text[:8192]
                ):
                    artifacts.append(relative)
        self.assertEqual(artifacts, [])

    def test_no_business_migration_or_user_interface_artifact_exists(self) -> None:
        """Preserve the pre-Milestone-5 selector at the advanced boundary."""

        self.test_no_business_migration_or_unapproved_user_interface_artifact_exists()


if __name__ == "__main__":
    unittest.main()
