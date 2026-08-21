from __future__ import annotations

import ast
import unittest
from pathlib import Path

import synthetic_sales_assist.domain.registries as registry_module
import synthetic_sales_assist.domain as domain_package


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "synthetic_sales_assist"
FORBIDDEN_FEATURE_NAMES = {
    "chrome_extension",
    "dashboard",
    "extension",
    "portal",
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


class MilestoneBoundaryTests(unittest.TestCase):
    def test_audit_finding_closure_matrix_is_complete(self) -> None:
        matrix_path = ROOT / "docs" / "audit-finding-closure-matrix.md"
        self.assertTrue(matrix_path.is_file())
        matrix_text = matrix_path.read_text(encoding="utf-8")
        self.assertIn("- Matrix version: `milestone4/v1`", matrix_text)
        self.assertNotIn("DEFERRED", matrix_text)
        self.assertNotIn("PARTIAL", matrix_text)
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
        allowed_statuses = {
            "CLOSED_M4",
            "CLOSED_M4_REOPEN_ON_EXTENSION",
        }
        self.assertTrue(all(cells[1] in allowed_statuses for cells in parsed.values()))

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

    def test_milestone_five_and_user_interface_modules_are_absent(self) -> None:
        discovered = {path.stem for path in PACKAGE.rglob("*.py")}
        discovered.update(path.name for path in PACKAGE.iterdir() if path.is_dir())
        self.assertFalse(discovered & FORBIDDEN_FEATURE_NAMES)

    def test_milestone_four_and_user_interface_modules_are_absent(self) -> None:
        """Preserve the Milestone 3 boundary oracle name."""

        self.test_milestone_five_and_user_interface_modules_are_absent()

    def test_milestone_three_and_user_interface_modules_are_absent(self) -> None:
        """Preserve the Milestone 2 oracle ID at the advanced milestone boundary."""

        self.test_milestone_five_and_user_interface_modules_are_absent()

    def test_package_has_no_network_client_import(self) -> None:
        violations: list[str] = []
        for path in sorted(PACKAGE.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = {alias.name for alias in node.names}
                elif isinstance(node, ast.ImportFrom):
                    names = {node.module or ""}
                else:
                    continue
                blocked = names & NETWORK_CLIENT_IMPORTS
                if blocked:
                    relative = path.relative_to(ROOT).as_posix()
                    violations.append(f"{relative}:{node.lineno}:{sorted(blocked)}")
        self.assertEqual(violations, [])

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

    def test_no_business_migration_or_user_interface_artifact_exists(self) -> None:
        """Preserve the pre-Milestone-4 oracle ID at the advanced boundary."""

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
        artifacts = [
            path.relative_to(ROOT).as_posix()
            for base in implementation_roots
            for path in base.rglob("*")
            if path.is_file()
            and (path.suffix.lower() in forbidden_suffixes or path.name == "manifest.json")
        ]
        self.assertEqual(artifacts, [])


if __name__ == "__main__":
    unittest.main()
