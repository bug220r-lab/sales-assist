"""Offline deterministic packaging and conservative local-installation regressions."""

from __future__ import annotations

import io
import json
import os
import socket
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from tests.daily_launch_fixtures import configure_synthetic_daily_policy
from synthetic_sales_assist.application.scenarios import ScenarioApplication
from synthetic_sales_assist.safety.repository import scan_prohibited_repository_content
from tools.build_demo_release import (
    LAUNCHERS,
    RUNTIME_FILES,
    RUNTIME_PREFIXES,
    build_payloads,
    digest,
    safe_member,
    zip_bytes,
)
from tools.release_support import (
    assert_unlinked,
    configured_data_root,
    extract_archive,
    prepare,
    remove_installation,
    verify_installation,
)


ROOT = Path(__file__).resolve().parents[1]
COMMIT = "a" * 40
TREE = "b" * 40
STAMP = 1788591709


def candidate_files() -> dict[str, bytes]:
    paths = {ROOT / name for name in RUNTIME_FILES}
    for prefix in RUNTIME_PREFIXES:
        paths.update(path for path in (ROOT / prefix).rglob("*")
                     if path.is_file() and "__pycache__" not in path.parts
                     and path.suffix != ".pyc")
    return {path.relative_to(ROOT).as_posix(): path.read_bytes() for path in paths}


class ReleasePackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.files = candidate_files()
        cls.artifacts, cls.metadata = build_payloads(cls.files, COMMIT, TREE, STAMP)
        cls.runtime_name = next(name for name in cls.artifacts if "windows-demo" in name)

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="synthetic-sales-assist-m8-package-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def install(self, name: str = "isolated demo with spaces") -> Path:
        archive = self.root / (name + ".zip")
        archive.write_bytes(self.artifacts[self.runtime_name])
        destination = self.root / name
        extract_archive(archive, destination)
        return destination

    def test_repeat_builds_have_identical_bytes_and_non_circular_provenance(self) -> None:
        again, metadata = build_payloads(dict(reversed(list(self.files.items()))), COMMIT,
                                        TREE, STAMP)
        self.assertEqual(again, self.artifacts)
        self.assertEqual(metadata, self.metadata)
        installation = self.install()
        inventory = json.loads((installation / "release-payload.json").read_text())
        self.assertNotIn("release-payload.json", inventory["files"])
        self.assertEqual(inventory["source_commit"], COMMIT)
        self.assertEqual(verify_installation(installation)["status"], "PASS")
        self.assertTrue(all((installation / name).is_file() for name in LAUNCHERS))

    def test_extension_is_the_exact_current_published_package(self) -> None:
        from tools.package_milestone6_extension import SnapshotFile, _zip_bytes, check_package

        ordered = sorted(self.files.items(), key=lambda item: item[0].lower())
        snapshot = tuple(SnapshotFile(name.removeprefix("chrome_extension/"), raw)
                         for name, raw in ordered
                         if name.startswith("chrome_extension/"))
        check_package(snapshot)
        name = next(name for name in self.artifacts if "extension" in name)
        self.assertEqual(self.artifacts[name], _zip_bytes(snapshot))

    def test_unsafe_paths_collisions_and_links_are_rejected_before_extraction(self) -> None:
        with patch.object(Path, "exists", side_effect=AssertionError("filesystem probe")):
            with self.assertRaisesRegex(ValueError, "LOCAL_PATH_REQUIRED"):
                assert_unlinked(Path("\\\\forbidden.invalid\\share\\synthetic-install"))
        for name in ("../escape", "/absolute", "C:/device", "a\\b", "a//b", "a/../b",
                     "a:stream", "CON.txt", "folder./file", "trailing "):
            with self.subTest(name=name), self.assertRaises(ValueError):
                safe_member(name)
        with self.assertRaises(ValueError):
            zip_bytes({"A.txt": b"a", "a.txt": b"b"}, STAMP)
        archive = self.root / "link.zip"
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as output:
            info = zipfile.ZipInfo("link")
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            output.writestr(info, "../outside")
        archive.write_bytes(buffer.getvalue())
        with self.assertRaises(ValueError):
            extract_archive(archive, self.root / "rejected")
        self.assertFalse((self.root / "rejected").exists())

    def test_verification_detects_changed_bytes_and_removal_preserves_unknown_files(self) -> None:
        installation = self.install()
        original = installation / "START_HERE.txt"
        original.write_text("locally amended fictional demo guide", encoding="utf-8")
        sentinel = installation / "keep-me.txt"
        sentinel.write_text("operator sentinel", encoding="utf-8")
        unrelated = self.root / "backups" / "keep.txt"
        unrelated.parent.mkdir()
        unrelated.write_text("preserve", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "PAYLOAD_MISMATCH"):
            verify_installation(installation)
        result = remove_installation(installation)
        self.assertEqual(result["preserved_modified"], ["START_HERE.txt"])
        self.assertTrue(sentinel.exists())
        self.assertTrue(original.exists())
        self.assertTrue(unrelated.exists())
        self.assertFalse((installation / "src" / "synthetic_sales_assist" / "__init__.py").exists())

    def test_new_install_seeds_once_and_upgrade_requires_verified_backup(self) -> None:
        installation = self.install()
        data = self.root / "demo-data"
        first = prepare(installation, data, False)
        self.assertTrue(first["fresh_seed"])
        database = data / "data" / "synthetic_sales_assist.sqlite3"
        application = ScenarioApplication.open(data)
        before = tuple(item.order_id for item in application.list_orders())
        self.assertFalse(prepare(installation, data, False)["fresh_seed"])
        marker = data / "demo-release.json"
        metadata = json.loads(marker.read_text())
        metadata["source_commit"] = "c" * 40
        marker.write_text(json.dumps(metadata), encoding="utf-8")
        before_bytes = digest(database.read_bytes())
        with self.assertRaisesRegex(ValueError, "EXPLICIT_UPGRADE"):
            prepare(installation, data, False)
        with patch("synthetic_sales_assist.persistence.backup.create_backup",
                   side_effect=RuntimeError("EXPECTED_BACKUP_FAILURE")):
            with self.assertRaisesRegex(RuntimeError, "EXPECTED_BACKUP_FAILURE"):
                prepare(installation, data, True)
        self.assertEqual(digest(database.read_bytes()), before_bytes)
        self.assertEqual(json.loads(marker.read_text())["source_commit"], "c" * 40)
        upgraded = prepare(installation, data, True)
        self.assertRegex(str(upgraded["upgrade_backup_sha256"]), "^[0-9a-f]{64}$")
        self.assertEqual(tuple(item.order_id for item in application.list_orders()), before)
        self.assertTrue(list((data / "backups").glob("before-upgrade-*.sqlite3")))

    def test_extracted_code_imports_from_package_without_development_pythonpath(self) -> None:
        installation = self.install()
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        result = subprocess.run(
            [sys.executable, "-c", "import synthetic_sales_assist as s; print(s.__file__)"],
            cwd=installation / "src", env=environment, capture_output=True, text=True,
            timeout=15, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(Path(result.stdout.strip()).is_relative_to(installation))

    def test_isolated_package_initializes_without_development_modules(self) -> None:
        installation = self.install()
        result = subprocess.run(
            [sys.executable, "-I", str(installation / "tools" / "release_support.py"),
             "prepare", "--install-root", str(installation), "--data-dir",
             str(self.root / "standalone data")],
            cwd=self.root, capture_output=True, text=True, timeout=30, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_metadata_links_fail_before_seed_and_configuration_retains_selected_root(self) -> None:
        installation = self.install()
        data = self.root / "linked-data"
        data.mkdir()
        sentinel = self.root / "sentinel.txt"
        sentinel.write_text("must remain unchanged", encoding="utf-8")
        os.link(sentinel, data / "demo-routes.json")
        with self.assertRaisesRegex(ValueError, "HARD_LINK"):
            prepare(installation, data, False)
        self.assertEqual(sentinel.read_text(), "must remain unchanged")
        self.assertFalse((data / "data" / "synthetic_sales_assist.sqlite3").exists())
        selected = self.root / "prior isolated demo"
        with patch.dict(os.environ, {"LOCALAPPDATA": str(self.root / "appdata")}):
            configured_data_root(installation, selected)
            self.assertEqual(configured_data_root(installation)["data_dir"], str(selected))

    @unittest.skipUnless(os.name == "nt", "Windows batch launcher integration")
    def test_two_copies_of_same_release_keep_independent_data_roots(self) -> None:
        first = self.install("first copy")
        second = self.install("second copy")
        with patch.dict(os.environ, {"LOCALAPPDATA": str(self.root / "appdata")}):
            self.assertNotEqual(configured_data_root(first), configured_data_root(second))
            configured_data_root(first, self.root / "first data")
            configured_data_root(second, self.root / "second data")
            self.assertEqual(configured_data_root(first)["data_dir"],
                             str(self.root / "first data"))
            self.assertEqual(configured_data_root(second)["data_dir"],
                             str(self.root / "second data"))

    @unittest.skipUnless(os.name == "nt", "Windows batch launcher integration")
    def test_actual_batch_launch_backup_upgrade_reset_and_conservative_remove(self) -> None:
        from tests.test_milestone5_lifecycle import POWERSHELL

        installation = self.install("batch launch with spaces")
        data = self.root / "owned isolated data"
        configure_synthetic_daily_policy(data)
        environment = os.environ.copy()
        environment["SSA_NONINTERACTIVE"] = "1"
        environment["SSA_PYTHON"] = os.path.abspath(sys.executable)
        environment["LOCALAPPDATA"] = str(self.root / "isolated appdata")
        environment["PYTHONPATH"] = str(self.root / "unrelated source")
        environment["PYTHONHOME"] = str(self.root / "stale python home")
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]

        def command(action: str, arguments: str = "") -> subprocess.CompletedProcess[str]:
            launcher = installation / (action + ".cmd")
            line = f'"{os.environ["COMSPEC"]}" /d /s /c ""{launcher}" {arguments}"'
            result = subprocess.run(
                line, env=environment, cwd=self.root, capture_output=True, text=True,
                timeout=60, check=False, creationflags=subprocess.CREATE_NO_WINDOW,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return result

        try:
            command("START", f'-NoBrowser -DataDir "{data}" -Port {port}')
            status = command("STATUS").stdout
            self.assertIn('"state":"RUNNING"', status)
            self.assertIn(str(data).replace("\\", "\\\\"), status)
            command("BACKUP")
            self.assertTrue(list((data / "backups").glob("demo-backup-*.sqlite3")))
            command("STOP")
            marker = data / "demo-release.json"
            previous = json.loads(marker.read_text())
            previous["source_commit"] = "c" * 40
            marker.write_text(json.dumps(previous), encoding="utf-8")
            command("UPGRADE", f'-NoBrowser -DataDir "{data}" -Port {port}')
            self.assertIn('"state":"RUNNING"', command("STATUS").stdout)
            self.assertTrue(list((data / "backups").glob("before-upgrade-*.sqlite3")))
            command("RESET", "-Confirmed")
            self.assertTrue(list((data / "backups").glob("pre-reset-*.sqlite3")))
            command("START", f"-NoBrowser -Port {port}")
            (installation / "keep-me.txt").write_text("preserve", encoding="utf-8")
            (installation / "START_HERE.txt").write_text("edited guide", encoding="utf-8")
            command("REMOVE", "-Confirmed")
            self.assertTrue((installation / "REMOVE.cmd").is_file())
            self.assertTrue((installation / "keep-me.txt").exists())
            self.assertTrue((installation / "START_HERE.txt").exists())
            self.assertTrue((data / "data" / "synthetic_sales_assist.sqlite3").exists())
            self.assertFalse((data / "runtime" / "service.json").exists())
        finally:
            if (data / "runtime" / "service.json").exists():
                cleanup = subprocess.run(
                    [str(POWERSHELL), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                     str(ROOT / "scripts" / "stop.ps1"), "-DataDir", str(data)],
                    env=environment, capture_output=True, text=True, timeout=30, check=False,
                )
                self.assertEqual(cleanup.returncode, 0, cleanup.stdout + cleanup.stderr)

    def test_launchers_have_narrow_scanner_admission_and_remote_text_still_fails(self) -> None:
        target = self.root / "scanner"
        target.mkdir()
        (target / "START.cmd").write_bytes((ROOT / "START.cmd").read_bytes())
        self.assertEqual(scan_prohibited_repository_content(target), ())
        (target / "unexpected.cmd").write_text(
            "rem SYNTHETIC-SALES-ASSIST-AUTHORED-M8\n", encoding="utf-8",
        )
        self.assertIn("unapproved_demo_launcher",
                      {item.category for item in scan_prohibited_repository_content(target)})
        (target / "START.cmd").write_text(
            "rem SYNTHETIC-SALES-ASSIST-AUTHORED-M8\nrem " + "https:" + "//unsafe.example.test",
            encoding="utf-8",
        )
        self.assertIn("non_localhost_url",
                      {item.category for item in scan_prohibited_repository_content(target)})
