"""Offline source packaging retains DOI safeguards without private launch state."""

from __future__ import annotations

import io
import json
import unittest
import zipfile
from pathlib import Path, PurePosixPath
from unittest.mock import patch

from tests.test_m8_release import COMMIT, ROOT, STAMP, TREE, candidate_files
from tools.build_demo_release import build_payloads, canonical, digest
from tools.build_windows_app import APP_GUIDES, build_application_payloads
from tools.review_package_payload import REQUIRED_MIGRATIONS, validate_migration_payload


class DailyDOIPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.files = candidate_files()
        cls.artifacts, cls.metadata = build_payloads(cls.files, COMMIT, TREE, STAMP)

    @staticmethod
    def members(raw: bytes) -> dict[str, bytes]:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            return {name: archive.read(name) for name in archive.namelist()}

    def test_daily_source_identity_is_deterministic_and_generated(self) -> None:
        again = build_payloads(dict(reversed(list(self.files.items()))), COMMIT, TREE, STAMP)
        self.assertEqual(again, (self.artifacts, self.metadata))
        self.assertRegex(self.metadata["doi_source_payload_sha256"], r"^[a-f0-9]{64}$")
        self.assertIs(self.metadata["daily_launch_requires_private_policy"], True)
        self.assertEqual(self.metadata["distribution_revision"], "doi-v7-daily-local-20261006")
        self.assertNotIn("release-build.json", self.files)
        runtime_name = next(name for name in self.artifacts if "windows-demo" in name)
        runtime = self.members(self.artifacts[runtime_name])
        self.assertEqual(json.loads(runtime["release-build.json"]), self.metadata)
        inventory = json.loads(runtime["release-payload.json"])["files"]
        self.assertEqual(inventory["release-build.json"], digest(runtime["release-build.json"]))

    def test_every_reviewed_source_resource_changes_private_policy_binding(self) -> None:
        # Stub compression only; execute the actual builder for every one-file mutation.
        names = [name for name in self.files if name.startswith(
            ("src/", "specs/", "migrations/", "scripts/")
        ) or name in {"pyproject.toml", "tools/daily_policy.py"}]
        self.assertIn("scripts/setup-daily-private.ps1", names)
        self.assertIn("src/doi_csv_staging/review_policy.py", names)
        original = self.metadata["doi_source_payload_sha256"]
        with patch("tools.build_demo_release.zip_bytes", return_value=b"synthetic-archive"):
            for name in names:
                with self.subTest(source=name):
                    changed = dict(self.files)
                    changed[name] += b"\n"
                    _, metadata = build_payloads(changed, COMMIT, TREE, STAMP)
                    self.assertNotEqual(metadata["doi_source_payload_sha256"], original)

    def test_daily_payload_includes_setup_helper_guides_and_unchanged_migrations(self) -> None:
        runtime_name = next(name for name in self.artifacts if "windows-demo" in name)
        runtime = self.members(self.artifacts[runtime_name])
        self.assertEqual(runtime["tools/daily_policy.py"], self.files["tools/daily_policy.py"])
        self.assertEqual(
            runtime["scripts/setup-daily-private.ps1"].replace(b"\r\n", b"\n"),
            self.files["scripts/setup-daily-private.ps1"].replace(b"\r\n", b"\n"),
        )
        for name in ("DAILY_README.md", "PRIVATE_CONFIGURATION.md"):
            self.assertEqual(runtime[name], self.files[f"docs/doi-v7/{name}"])
            self.assertEqual(runtime[f"docs/doi-v7/{name}"], runtime[name])
        validate_migration_payload(runtime)
        self.assertEqual({name for name in runtime if name.startswith("migrations/")},
                         set(REQUIRED_MIGRATIONS))

    def test_synthetic_assembly_never_generates_private_configuration_or_receipts(self) -> None:
        forbidden_names = {
            "doi-private-launch.json", "owner-confirmations.private.json",
            "service.json", "doi-policy-binding.json", "service-owner-claim.json",
        }
        for artifact, raw in self.artifacts.items():
            with self.subTest(artifact=artifact):
                members = self.members(raw)
                self.assertFalse(forbidden_names & {PurePosixPath(name).name for name in members})
                self.assertFalse(any(name.startswith(("runtime/", "data/", "captures/"))
                                     for name in members))

    def test_windows_assembly_retains_daily_policy_contract_without_runtime_downloads(self) -> None:
        files = dict(self.files)
        files.update({f"docs/windows-app/{name}": (ROOT / "docs/windows-app" / name).read_bytes()
                      for name in APP_GUIDES})
        synthetic_runtime = {"python/python.exe": b"synthetic-not-an-executable"}
        manifest = canonical({
            "schema": "synthetic-sales-assist-bundled-python/v1",
            "python_version": "3.12.14", "architecture": "windows-x86_64",
            "executable": "python/python.exe",
            "files": {name: digest(raw) for name, raw in synthetic_runtime.items()},
        })
        synthetic_runtime["python-runtime.json"] = manifest
        bundle = (synthetic_runtime, {"manifest": "python-runtime.json",
                  "sha256": digest(manifest), "executable": "python/python.exe",
                  "python_version": "3.12.14", "timezone_version": "2026.3"})
        with patch("tools.bundled_python.bundled_runtime", return_value=bundle):
            artifacts, metadata = build_application_payloads(
                files, COMMIT, TREE, STAMP, Path("SYN-runtime.tar.gz"), Path("SYN-tz.whl"),
            )
        self.assertEqual(metadata["doi_source_payload_sha256"],
                         self.metadata["doi_source_payload_sha256"])
        self.assertIs(metadata["daily_launch_requires_private_policy"], True)
        self.assertEqual(metadata["workflow_scope"],
                         "LOCALHOST_SYNTHETIC_CORE_WITH_LOCAL_DOI_REVIEW")
        self.assertIn("doi_csv_review", metadata["application_features"])
        name = next(name for name in artifacts if name.endswith("-windows-x64.zip"))
        runtime = self.members(artifacts[name])
        self.assertEqual(json.loads(runtime["release-build.json"]), metadata)
        self.assertIn("tools/daily_policy.py", runtime)
        self.assertIn("scripts/setup-daily-private.ps1", runtime)
        validate_migration_payload(runtime)


if __name__ == "__main__":
    unittest.main()
