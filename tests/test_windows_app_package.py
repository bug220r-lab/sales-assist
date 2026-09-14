"""Portable package assembly preserves provenance and the existing release contracts."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from tests.test_m8_release import COMMIT, ROOT, STAMP, TREE, candidate_files
from tools.build_demo_release import LAUNCHERS, canonical, digest
from tools.build_windows_app import (
    APP_GUIDES, RECIPE_FILES, build_application_payloads, verify_build_recipe,
)
from tools.release_support import extract_archive, verify_installation


class WindowsApplicationPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.files = candidate_files()
        cls.files.update({
            f"docs/windows-app/{name}": (ROOT / "docs" / "windows-app" / name).read_bytes()
            for name in APP_GUIDES
        })

    def bundle(self) -> tuple[dict[str, bytes], dict[str, object]]:
        members = {"python/python.exe": b"synthetic-test-not-an-executable"}
        manifest = canonical({
            "schema": "synthetic-sales-assist-bundled-python/v1",
            "python_version": "3.12.14", "architecture": "windows-x86_64",
            "executable": "python/python.exe",
            "files": {name: digest(raw) for name, raw in members.items()},
        })
        members["python-runtime.json"] = manifest
        return members, {
            "manifest": "python-runtime.json", "sha256": digest(manifest),
            "executable": "python/python.exe", "python_version": "3.12.14",
            "timezone_version": "2026.3",
        }

    def payloads(self, files: dict[str, bytes] | None = None):
        with patch("tools.bundled_python.bundled_runtime", return_value=self.bundle()):
            return build_application_payloads(
                files or self.files, COMMIT, TREE, STAMP, Path("python.tar.gz"), Path("tz.whl"),
            )

    def test_deterministic_identity_inventory_and_launchers(self) -> None:
        artifacts, metadata = self.payloads()
        again = self.payloads(dict(reversed(list(self.files.items()))))
        self.assertEqual((artifacts, metadata), again)
        self.assertEqual(metadata["source_commit"], COMMIT)
        self.assertEqual(metadata["source_tree"], TREE)
        self.assertEqual(metadata["runtime_tier"], "WINDOWS_X64_BUNDLED_CPYTHON_3_12")
        self.assertEqual(metadata["codex_fallback"], "NONE")
        self.assertIn("campaigns", metadata["application_features"])
        name = next(name for name in artifacts if name.endswith("-windows-x64.zip"))
        with zipfile.ZipFile(io.BytesIO(artifacts[name])) as archive:
            for launcher in LAUNCHERS:
                raw = archive.read(launcher)
                self.assertNotIn(b"-DevelopmentRuntime", raw)
                if launcher == "START.cmd":
                    self.assertIn(b'if not "%SSA_RESULT%"=="0"', raw)
                else:
                    self.assertIn(b'if not "%SSA_NONINTERACTIVE%"=="1" pause', raw)
                    self.assertNotIn(b'if not "%SSA_RESULT%"=="0"', raw)
            self.assertEqual(archive.read("START_HERE.txt"),
                             self.files["docs/windows-app/START_HERE.txt"])
            self.assertEqual(json.loads(archive.read("release-build.json")), metadata)
            inventory = json.loads(archive.read("release-payload.json"))["files"]
            self.assertIn("python/python.exe", inventory)
            self.assertIn("python-runtime.json", inventory)
            self.assertNotIn("release-payload.json", inventory)

    def test_extracted_payload_verifies_and_detects_runtime_tampering(self) -> None:
        artifacts, _ = self.payloads()
        name = next(name for name in artifacts if name.endswith("-windows-x64.zip"))
        with tempfile.TemporaryDirectory(prefix="synthetic-windows-app-package-") as temporary:
            root = Path(temporary)
            archive = root / "app.zip"
            archive.write_bytes(artifacts[name])
            installation = root / "app with spaces"
            extract_archive(archive, installation)
            self.assertEqual(verify_installation(installation)["status"], "PASS")
            (installation / "python" / "python.exe").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "RELEASE_PAYLOAD_MISMATCH"):
                verify_installation(installation)

    def test_runtime_cannot_overwrite_application_members(self) -> None:
        members, metadata = self.bundle()
        members["START.cmd"] = b"changed"
        with patch("tools.bundled_python.bundled_runtime", return_value=(members, metadata)):
            with self.assertRaisesRegex(ValueError, "BUNDLED_RUNTIME_MEMBER_COLLISION"):
                build_application_payloads(
                    self.files, COMMIT, TREE, STAMP, Path("runtime.tar.gz"), Path("tz.whl"),
                )

    def test_unexpected_launcher_template_fails_before_publication(self) -> None:
        files = dict(self.files)
        files["START.cmd"] = files["START.cmd"].replace(b" -DevelopmentRuntime", b"")
        with self.assertRaisesRegex(ValueError, "PORTABLE_LAUNCHER_TEMPLATE_INVALID"):
            self.payloads(files)

    def test_executed_recipe_must_match_requested_source_snapshot(self) -> None:
        files = {name: (ROOT / name).read_bytes() for name in RECIPE_FILES}
        verify_build_recipe(files)
        files["tools/windows_runtime_lock.json"] += b"\n"
        with self.assertRaisesRegex(ValueError, "BUILD_RECIPE_DOES_NOT_MATCH_SOURCE_COMMIT"):
            verify_build_recipe(files)
        del files["tools/windows_runtime_lock.json"]
        with self.assertRaisesRegex(ValueError, "BUILD_RECIPE_DOES_NOT_MATCH_SOURCE_COMMIT"):
            verify_build_recipe(files)


if __name__ == "__main__":
    unittest.main()
