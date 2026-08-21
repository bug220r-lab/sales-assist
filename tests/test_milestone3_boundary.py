from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "synthetic_sales_assist" / "doi"
DOI_MODULES = {
    "__init__.py",
    "boundaries.py",
    "case_attention.py",
    "demo.py",
    "evaluator.py",
    "extraction.py",
    "fixtures.py",
    "identities.py",
    "interventions.py",
    "knowledge.py",
    "lifecycle.py",
    "models.py",
    "retention.py",
    "source.py",
    "state.py",
    "traceability.py",
}
PURE_MODULES = DOI_MODULES - {
    "__init__.py",
    "demo.py",
    "fixtures.py",
    "retention.py",
    "source.py",
    "state.py",
    "traceability.py",
}
FORBIDDEN_IMPORT_PREFIXES = (
    "aiohttp",
    "ftplib",
    "http.client",
    "httpx",
    "requests",
    "smtplib",
    "socket",
    "sqlite3",
    "synthetic_sales_assist.persistence",
    "synthetic_sales_assist.sales_credit",
    "urllib.request",
)


def _imported_names(tree: ast.AST) -> tuple[str, ...]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.append(node.module or "")
    return tuple(names)


class Milestone3BoundaryTests(unittest.TestCase):
    def test_doi_package_inventory_is_exact(self) -> None:
        self.assertTrue(PACKAGE.is_dir())
        files = {path.name for path in PACKAGE.iterdir() if path.is_file()}
        self.assertEqual(files, DOI_MODULES)
        self.assertFalse(
            [
                path.name
                for path in PACKAGE.iterdir()
                if path.is_dir() and path.name != "__pycache__"
            ]
        )

    def test_doi_has_no_sales_credit_persistence_or_network_dependency(self) -> None:
        violations: list[str] = []
        for path in sorted(PACKAGE.glob("*.py")):
            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text, filename=str(path))
            for name in _imported_names(tree):
                if any(
                    name == prefix or name.startswith(prefix + ".")
                    for prefix in FORBIDDEN_IMPORT_PREFIXES
                ):
                    violations.append(f"{path.name}:import:{name}")
            upper = text.upper()
            for fragment in (
                "CREATE TABLE",
                "INSERT INTO",
                "UPDATE ",
                "DELETE FROM",
                "ATTACH DATABASE",
            ):
                if fragment in upper:
                    violations.append(f"{path.name}:sql:{fragment.strip()}")
        self.assertEqual(violations, [])

    def test_pure_rule_modules_have_no_clock_random_thread_or_io(self) -> None:
        violations: list[str] = []
        for name in sorted(PURE_MODULES):
            path = PACKAGE / name
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for imported in _imported_names(tree):
                if imported in {"random", "secrets", "threading"}:
                    violations.append(f"{name}:import:{imported}")
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name) and node.func.id in {
                        "eval",
                        "exec",
                        "open",
                    }:
                        violations.append(f"{name}:{node.lineno}:call:{node.func.id}")
                    if (
                        isinstance(node.func, ast.Attribute)
                        and node.func.attr in {"now", "today", "utcnow"}
                    ):
                        violations.append(f"{name}:{node.lineno}:clock")
        self.assertEqual(violations, [])

    def test_milestone_five_artifacts_remain_absent(self) -> None:
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
        forbidden_stems = {
            "api",
            "browser",
            "chrome_extension",
            "connector",
            "dashboard",
            "extension",
            "portal",
            "server",
            "worker",
        }
        discovered = {path.stem for path in PACKAGE.rglob("*") if path.is_file()}
        self.assertFalse(discovered & forbidden_stems)

    def test_milestone_four_artifacts_remain_absent(self) -> None:
        """Preserve the Milestone 3 collected boundary selector."""

        self.test_milestone_five_artifacts_remain_absent()

    def test_no_temporary_or_backup_artifact_exists(self) -> None:
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
