from __future__ import annotations

import ast
import unittest
from pathlib import Path

import synthetic_sales_assist.sales_credit as sales_credit_package
from synthetic_sales_assist.sales_credit import (
    accumulator,
    discovery,
    evaluator,
    fixtures,
    metrics,
    models,
    retention,
    traceability,
    windows,
)


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "synthetic_sales_assist" / "sales_credit"
SALES_CREDIT_MODULES = {
    "__init__.py",
    "accumulator.py",
    "discovery.py",
    "evaluator.py",
    "fixtures.py",
    "metrics.py",
    "models.py",
    "retention.py",
    "traceability.py",
    "windows.py",
}
PURE_MODULES = {"evaluator.py", "metrics.py", "windows.py"}
FORBIDDEN_IMPORT_PREFIXES = (
    "aiohttp",
    "ftplib",
    "http.client",
    "httpx",
    "random",
    "requests",
    "secrets",
    "smtplib",
    "socket",
    "sqlite3",
    "synthetic_sales_assist.domain.registries",
    "synthetic_sales_assist.doi",
    "synthetic_sales_assist.persistence",
    "threading",
    "urllib.request",
)


def imported_names(tree: ast.AST) -> tuple[str, ...]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.append(node.module or "")
    return tuple(names)


class Milestone2BoundaryTests(unittest.TestCase):
    def test_sales_credit_package_inventory_and_public_facade_are_closed(self) -> None:
        files = {path.name for path in PACKAGE.iterdir() if path.is_file()}
        self.assertEqual(files, SALES_CREDIT_MODULES)
        self.assertFalse(
            [
                path.name
                for path in PACKAGE.iterdir()
                if path.is_dir() and path.name != "__pycache__"
            ]
        )

        declared_modules = (
            models,
            windows,
            discovery,
            evaluator,
            accumulator,
            retention,
            metrics,
            fixtures,
            traceability,
        )
        declared = [name for module in declared_modules for name in module.__all__]
        self.assertEqual(sales_credit_package.__all__, declared)
        self.assertEqual(len(declared), len(set(declared)))
        self.assertTrue(all(hasattr(sales_credit_package, name) for name in declared))

    def test_rule_pack_has_no_doi_registry_database_or_network_dependency(self) -> None:
        violations: list[str] = []
        for path in sorted(PACKAGE.glob("*.py")):
            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text, filename=str(path))
            for name in imported_names(tree):
                if any(
                    name == prefix or name.startswith(prefix + ".")
                    for prefix in FORBIDDEN_IMPORT_PREFIXES
                    if prefix not in {"random", "secrets", "threading"}
                ):
                    violations.append(f"{path.name}:import:{name}")
            for forbidden in ("ReasonRef", "load_doi_registries"):
                if forbidden in text:
                    violations.append(f"{path.name}:symbol:{forbidden}")
            upper = text.upper()
            for fragment in ("CREATE TABLE", "INSERT INTO", "UPDATE ", "DELETE FROM"):
                if fragment in upper:
                    violations.append(f"{path.name}:sql:{fragment.strip()}")
        self.assertEqual(violations, [])

    def test_pure_rules_have_no_clock_random_thread_or_io_escape_hatch(self) -> None:
        violations: list[str] = []
        forbidden_calls = {"now", "today", "utcnow"}
        for name in sorted(PURE_MODULES):
            path = PACKAGE / name
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for imported in imported_names(tree):
                if any(
                    imported == prefix or imported.startswith(prefix + ".")
                    for prefix in FORBIDDEN_IMPORT_PREFIXES
                ):
                    violations.append(f"{name}:import:{imported}")
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in forbidden_calls
                ):
                    violations.append(f"{name}:{node.lineno}:clock")
        self.assertEqual(violations, [])

    def test_no_milestone_four_persistence_or_user_interface_artifact_exists(self) -> None:
        migrations = ROOT / "migrations"
        self.assertEqual(
            {path.name for path in migrations.iterdir() if path.is_file()},
            {"0001_foundation.sql"},
        )
        forbidden_names = {
            "api",
            "browser",
            "chrome_extension",
            "dashboard",
            "extension",
            "portal",
        }
        discovered_names = {
            path.stem
            for root in (ROOT / "src", ROOT / "tests", ROOT / "tools")
            for path in root.rglob("*")
            if path.is_file()
        }
        self.assertFalse(discovered_names & forbidden_names)

    def test_candidate_contains_no_temporary_or_backup_artifact(self) -> None:
        disallowed: list[str] = []
        for root in (ROOT / "src", ROOT / "tests", ROOT / "docs"):
            for path in root.rglob("*"):
                if not path.is_file():
                    continue
                lowered = path.name.lower()
                if lowered.endswith((".bak", ".orig", ".rej", ".swp", ".tmp", "~")):
                    disallowed.append(path.relative_to(ROOT).as_posix())
        self.assertEqual(disallowed, [])


if __name__ == "__main__":
    unittest.main()
