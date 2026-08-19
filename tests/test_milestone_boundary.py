from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "synthetic_sales_assist"
FORBIDDEN_FEATURE_NAMES = {
    "chrome_extension",
    "dashboard",
    "doi",
    "extension",
    "portal",
    "rules_engine",
    "sales_credit",
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
    def test_future_feature_modules_are_absent(self) -> None:
        discovered = {path.stem for path in PACKAGE.rglob("*.py")}
        discovered.update(path.name for path in PACKAGE.iterdir() if path.is_dir())
        self.assertFalse(discovered & FORBIDDEN_FEATURE_NAMES)

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


if __name__ == "__main__":
    unittest.main()
