from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from synthetic_sales_assist.safety.repository import (  # noqa: E402
    AUTHORED_M5_MARKER,
    scan_prohibited_repository_content,
    scan_secret_material,
)


class RepositoryScannerTests(unittest.TestCase):
    def test_candidate_repository_is_free_of_secret_material(self) -> None:
        self.assertEqual(scan_secret_material(ROOT), ())

    def test_candidate_repository_has_no_prohibited_content(self) -> None:
        self.assertEqual(scan_prohibited_repository_content(ROOT), ())

    def test_secret_canaries_are_detected_without_returning_material(self) -> None:
        private_marker = "-" * 5 + "BEGIN " + "PRIVATE" + " KEY" + "-" * 5
        access_key = "A" + "KIA" + "A1B2C3D4E5F6G7H8"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "fixture.txt").write_text(
                private_marker + "\n" + access_key + "\n", encoding="utf-8"
            )
            findings = scan_secret_material(root)
        self.assertEqual({item.category for item in findings}, {"cloud_access_key", "private_key"})
        rendered = repr(findings)
        self.assertNotIn(access_key, rendered)
        self.assertNotIn(private_marker, rendered)

    def test_sha256_digest_is_not_misclassified_as_a_secret(self) -> None:
        digest = "a" * 64
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "hash.txt").write_text(digest + "\n", encoding="utf-8")
            self.assertEqual(scan_secret_material(root), ())

    def test_external_url_canary_is_detected(self) -> None:
        external = "ht" + "tps://" + "outside" + ".invalid/path"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src").mkdir()
            (root / "src" / "fixture.py").write_text(repr(external), encoding="utf-8")
            findings = scan_prohibited_repository_content(root)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].category, "non_localhost_url")
        self.assertNotIn(external, repr(findings))

    def test_only_marked_bounded_portal_assets_are_admitted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            portal = root / "src" / "synthetic_sales_assist" / "portal" / "static"
            portal.mkdir(parents=True)
            (portal / "portal.html").write_text(
                f"<!-- {AUTHORED_M5_MARKER} -->\n<" + "html lang=\"en\"></html>\n",
                encoding="utf-8",
            )
            (portal / "portal.js").write_text(
                f"// {AUTHORED_M5_MARKER}\n'use strict';\n",
                encoding="utf-8",
            )
            self.assertEqual(scan_prohibited_repository_content(root), ())

            (portal / "unmarked.html").write_text(
                "<" + "html lang=\"en\"></html>\n",
                encoding="utf-8",
            )
            findings = scan_prohibited_repository_content(root)
        self.assertIn("unapproved_portal_asset", {item.category for item in findings})

    def test_lifecycle_scripts_are_exactly_allowlisted_and_scanned(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scripts = root / "scripts"
            scripts.mkdir()
            (scripts / "start.ps1").write_text(
                f"# {AUTHORED_M5_MARKER}\n$origin = 'http://127.0.0.1:8765'\n",
                encoding="utf-8",
            )
            self.assertEqual(scan_prohibited_repository_content(root), ())
            (scripts / "unexpected.ps1").write_text(
                f"# {AUTHORED_M5_MARKER}\n",
                encoding="utf-8",
            )
            findings = scan_prohibited_repository_content(root)
        self.assertEqual(
            {item.category for item in findings},
            {"unapproved_lifecycle_script"},
        )

    def test_extension_dashboard_connector_and_source_map_paths_stay_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "src"
            (source / "dashboard").mkdir(parents=True)
            (source / "connector").mkdir()
            (source / "dashboard" / "view.py").write_text("VALUE = 1\n", encoding="utf-8")
            (source / "connector" / "adapter.py").write_text("VALUE = 1\n", encoding="utf-8")
            (source / "manifest.json").write_text("{}\n", encoding="utf-8")
            (source / "portal.map").write_text("{}\n", encoding="utf-8")
            portal = source / "synthetic_sales_assist" / "portal"
            portal.mkdir(parents=True)
            (portal / "marked.pem").write_text(
                f"{AUTHORED_M5_MARKER}\nnot-a-permitted-asset\n",
                encoding="utf-8",
            )
            (source / "extension").mkdir()
            (source / "extension" / "entry.py").write_text("VALUE = 1\n", encoding="utf-8")
            (source / "milestone6").mkdir()
            (source / "milestone6" / "entry.py").write_text("VALUE = 1\n", encoding="utf-8")
            findings = scan_prohibited_repository_content(root)
        self.assertEqual(
            {item.category for item in findings},
            {
                "extension_manifest",
                "prohibited_artifact_type",
                "prohibited_capability_path",
            },
        )


if __name__ == "__main__":
    unittest.main()
