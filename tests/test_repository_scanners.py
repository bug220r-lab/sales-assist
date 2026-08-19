from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from synthetic_sales_assist.safety.repository import (  # noqa: E402
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


if __name__ == "__main__":
    unittest.main()
