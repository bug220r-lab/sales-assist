"""Integrated first-run preservation and verified two-store release backup boundaries."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from synthetic_sales_assist.application.scenarios import ScenarioApplication
from synthetic_sales_assist.campaign_replies.application import WorkspaceApplication
from synthetic_sales_assist.persistence.schema import DatabaseVerificationError
from tools import release_support as release
from tools.prepare_milestone7_demo import prepare_demo


class IntegratedReleaseDataTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="ssa-integrated-release-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.installation = self.root / "installation"
        self.installation.mkdir()
        self.metadata = {
            "schema": "synthetic-sales-assist-release-build/v1",
            "release_id": "demo-0.2.0-" + "a" * 12,
            "source_commit": "a" * 40, "source_tree": "b" * 40,
        }
        self._install_payload({
            "START_HERE.txt": b"Synthetic test installation",
            "tools/prepare_milestone7_demo.py": (
                Path(__file__).resolve().parents[1] / "tools" / "prepare_milestone7_demo.py"
            ).read_bytes(),
        })
        self.data = self.root / "data root"
        self.workspace_path = self.data / "data" / "campaign_replies.sqlite3"
        self.core_path = self.data / "data" / "synthetic_sales_assist.sqlite3"
        self.marker = self.data / "demo-release.json"

    def _install_payload(self, files: dict[str, bytes]) -> None:
        files = {**files, "release-build.json": json.dumps(self.metadata).encode("utf-8")}
        for name, content in files.items():
            target = self.installation / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        inventory = {
            "schema": "synthetic-sales-assist-release-payload/v1",
            "source_commit": self.metadata["source_commit"],
            "excluded_self": "release-payload.json",
            "files": {name: hashlib.sha256(content).hexdigest()
                      for name, content in files.items()},
        }
        (self.installation / "release-payload.json").write_text(json.dumps(inventory))

    def _draft(self) -> tuple[str, str]:
        workspace = WorkspaceApplication(self.workspace_path)
        item = workspace.get({"view": "queue"})["items"][0]
        conversation_id = item["conversation_id"]
        detail = workspace.replies.detail(conversation_id)
        text = "Synthetic operator edit retained across launches and backups."
        workspace.replies.save_draft(
            conversation_id, text, 0, detail["source_fingerprint"],
            detail["style_profile"]["version"], reviewed=False,
        )
        return conversation_id, text

    def _assert_draft(self, conversation_id: str, expected: str) -> None:
        detail = WorkspaceApplication(self.workspace_path).replies.detail(conversation_id)
        self.assertEqual(detail["local_draft"]["text"], expected)
        self.assertEqual(detail["local_draft"]["revision"], 1)

    def _mark_older(self) -> bytes:
        marker = json.loads(self.marker.read_text())
        marker["source_commit"] = "c" * 40
        self.marker.write_text(json.dumps(marker))
        return self.marker.read_bytes()

    def test_first_run_seeds_all_workspaces_and_reopen_preserves_edits(self) -> None:
        first = release.prepare(self.installation, self.data, False)
        self.assertTrue(first["fresh_seed"])
        self.assertTrue(first["campaign_fresh_seed"])
        self.assertTrue(ScenarioApplication.open(self.data).list_orders())
        workspace = WorkspaceApplication(self.workspace_path)
        self.assertTrue(workspace.campaigns.list_campaigns())
        self.assertTrue(workspace.history.candidates())
        conversation_id, text = self._draft()
        second = release.prepare(self.installation, self.data, False)
        self.assertFalse(second["fresh_seed"])
        self.assertFalse(second["campaign_fresh_seed"])
        self._assert_draft(conversation_id, text)
        self.assertEqual(json.loads(self.marker.read_text())["campaign_workspace_format"],
                         release.WORKSPACE_FORMAT)

    def test_backup_contains_edited_draft_and_binds_both_file_hashes_and_identity(self) -> None:
        release.prepare(self.installation, self.data, False)
        conversation_id, text = self._draft()
        result = release.backup_application(self.installation, self.data)
        self.assertEqual(result["status"], "BACKUP_VERIFIED")
        manifest = json.loads(Path(result["manifest_path"]).read_text())
        self.assertEqual(manifest["source_release"]["source_commit"], "a" * 40)
        self.assertEqual(manifest["created_by_release"], self.metadata)
        core = self.data / "backups" / manifest["core"]["filename"]
        companion = self.data / "backups" / "workspace" / manifest["campaign_workspace"]["filename"]
        self.assertEqual(hashlib.sha256(core.read_bytes()).hexdigest(),
                         result["core_backup_sha256"])
        self.assertEqual(hashlib.sha256(companion.read_bytes()).hexdigest(),
                         result["campaign_backup_sha256"])
        receipt = self.data / "backups" / manifest["core"]["receipt_filename"]
        self.assertEqual(hashlib.sha256(receipt.read_bytes()).hexdigest(),
                         manifest["core"]["receipt_sha256"])
        connection = sqlite3.connect(companion)
        self.addCleanup(connection.close)
        self.assertEqual(connection.execute(
            "SELECT text,revision FROM cr_local_drafts WHERE conversation_id=?",
            (conversation_id,),
        ).fetchone(), (text, 1))

    def test_failed_companion_backup_does_not_advance_upgrade_marker(self) -> None:
        release.prepare(self.installation, self.data, False)
        conversation_id, text = self._draft()
        previous = self._mark_older()
        with patch.object(release, "_backup_workspace", side_effect=OSError("EXPECTED_FAILURE")):
            with self.assertRaisesRegex(OSError, "EXPECTED_FAILURE"):
                release.prepare(self.installation, self.data, True)
        self.assertEqual(self.marker.read_bytes(), previous)
        self._assert_draft(conversation_id, text)
        self.assertTrue(list((self.data / "backups").glob("before-upgrade-*.receipt.json")))
        self.assertEqual(list((self.data / "backups" / "app-manifests").glob("*.json")), [])

    def test_upgrade_preserves_edits_and_distinguishes_source_and_target_release(self) -> None:
        release.prepare(self.installation, self.data, False)
        conversation_id, text = self._draft()
        self._mark_older()
        upgraded = release.prepare(self.installation, self.data, True)
        self.assertFalse(upgraded["campaign_fresh_seed"])
        self._assert_draft(conversation_id, text)
        manifest = json.loads(Path(upgraded["upgrade_backup_manifest"]).read_text())
        self.assertEqual(manifest["source_release"]["source_commit"], "c" * 40)
        self.assertEqual(manifest["created_by_release"]["source_commit"], "a" * 40)
        self.assertEqual(json.loads(self.marker.read_text())["source_commit"], "a" * 40)

    def test_unrelated_workspace_is_rejected_before_core_is_created_or_modified(self) -> None:
        self.workspace_path.parent.mkdir(parents=True)
        connection = sqlite3.connect(self.workspace_path)
        connection.execute("CREATE TABLE unrelated (sentinel TEXT)")
        connection.execute("INSERT INTO unrelated VALUES('synthetic sentinel')")
        connection.commit()
        connection.close()
        before = self.workspace_path.read_bytes()
        with self.assertRaisesRegex(ValueError, "WORKSPACE_FORMAT_INVALID"):
            release.prepare(self.installation, self.data, False)
        self.assertFalse(self.core_path.exists())
        self.assertEqual(self.workspace_path.read_bytes(), before)
        prepare_demo(self.data)
        core_before = self.core_path.read_bytes()
        with patch("synthetic_sales_assist.persistence.backup.create_backup") as backup:
            with self.assertRaisesRegex(ValueError, "WORKSPACE_FORMAT_INVALID"):
                release.prepare(self.installation, self.data, True)
            backup.assert_not_called()
        self.assertEqual(self.core_path.read_bytes(), core_before)
        self.assertEqual(self.workspace_path.read_bytes(), before)

    def test_incomplete_workspace_identity_cannot_be_adopted(self) -> None:
        self.workspace_path.parent.mkdir(parents=True)
        connection = sqlite3.connect(self.workspace_path)
        connection.execute("CREATE TABLE workspace_metadata (singleton INTEGER, format TEXT)")
        connection.execute("INSERT INTO workspace_metadata VALUES(1,?)",
                           (release.WORKSPACE_FORMAT,))
        connection.commit()
        connection.close()
        before = self.workspace_path.read_bytes()
        with self.assertRaisesRegex(ValueError, "WORKSPACE_FORMAT_INVALID"):
            release.prepare(self.installation, self.data, False)
        self.assertEqual(self.workspace_path.read_bytes(), before)
        self.assertFalse(self.core_path.exists())

    def test_missing_previously_initialized_workspace_fails_without_reseeding(self) -> None:
        release.prepare(self.installation, self.data, False)
        self.workspace_path.unlink()
        previous = self.marker.read_bytes()
        with self.assertRaisesRegex(ValueError, "WORKSPACE_DATABASE_MISSING"):
            release.prepare(self.installation, self.data, False)
        with self.assertRaisesRegex(ValueError, "WORKSPACE_DATABASE_MISSING"):
            release.backup_application(self.installation, self.data)
        self.assertEqual(self.marker.read_bytes(), previous)
        self.assertFalse(self.workspace_path.exists())

    def test_unrelated_core_database_is_rejected_before_workspace_seed(self) -> None:
        self.core_path.parent.mkdir(parents=True)
        connection = sqlite3.connect(self.core_path)
        connection.execute("CREATE TABLE unrelated (sentinel TEXT)")
        connection.commit()
        connection.close()
        before = self.core_path.read_bytes()
        with self.assertRaisesRegex(DatabaseVerificationError, "MIGRATION_LEDGER_UNAVAILABLE"):
            release.prepare(self.installation, self.data, True)
        self.assertEqual(self.core_path.read_bytes(), before)
        self.assertFalse(self.workspace_path.exists())
        self.assertFalse(self.marker.exists())

    def test_orphaned_identified_workspace_is_preserved_for_explicit_review(self) -> None:
        WorkspaceApplication(self.workspace_path).post({"action": "demo"})
        conversation_id, text = self._draft()
        with self.assertRaisesRegex(ValueError, "ORPHAN_WORKSPACE_REQUIRES_REVIEW"):
            release.prepare(self.installation, self.data, True)
        self.assertFalse(self.core_path.exists())
        self._assert_draft(conversation_id, text)

    def test_legacy_core_only_backup_is_explicit_and_upgrade_adds_workspace(self) -> None:
        prepare_demo(self.data)
        self.marker.write_text(json.dumps({**self.metadata, "source_commit": "c" * 40}))
        backup = release.backup_application(self.installation, self.data)
        self.assertEqual(backup["campaign_workspace_status"], "ABSENT_LEGACY_CORE_ONLY")
        self.assertIsNone(backup["campaign_backup_sha256"])
        result = release.prepare(self.installation, self.data, True)
        self.assertFalse(result["fresh_seed"])
        self.assertTrue(result["campaign_fresh_seed"])
        self.assertTrue(WorkspaceApplication(self.workspace_path).replies.list_queue()["items"])

    def test_mismatched_backup_content_never_publishes_success_manifest(self) -> None:
        release.prepare(self.installation, self.data, False)
        with patch.object(release, "_logical_digest", side_effect=["a" * 64, "b" * 64]):
            with self.assertRaisesRegex(ValueError, "WORKSPACE_BACKUP_CONTENT_MISMATCH"):
                release.backup_application(self.installation, self.data)
        self.assertEqual(list((self.data / "backups" / "app-manifests").glob("*.json")), [])

    def test_workspace_backup_never_overwrites_existing_file(self) -> None:
        release.prepare(self.installation, self.data, False)
        destination = self.root / "reserved.sqlite3"
        destination.write_bytes(b"synthetic retained backup")
        with self.assertRaises(FileExistsError):
            release._backup_workspace(self.workspace_path, destination)
        self.assertEqual(destination.read_bytes(), b"synthetic retained backup")

    def test_core_reseed_preserves_existing_campaign_draft(self) -> None:
        ScenarioApplication.open(self.data)
        WorkspaceApplication(self.workspace_path).post({"action": "demo"})
        conversation_id, text = self._draft()
        result = release.reseed(self.installation, self.data)
        self.assertEqual(result["campaign_workspace"], "PRESERVED")
        self._assert_draft(conversation_id, text)
        self.assertTrue(ScenarioApplication.open(self.data).list_orders())

    def test_remove_retains_all_embedded_python_files_until_operator_exits(self) -> None:
        self._install_payload({"python/python.exe": b"synthetic executable fixture",
                               "python/python313.zip": b"synthetic library fixture",
                               "src/owned.py": b"# synthetic removable source"})
        python = self.installation / "python" / "python.exe"
        python.write_bytes(b"locally changed synthetic fixture")
        result = release.remove_installation(self.installation)
        self.assertEqual(set(result["preserved_runtime"]),
                         {"python/python.exe", "python/python313.zip"})
        self.assertEqual(python.read_bytes(), b"locally changed synthetic fixture")
        self.assertTrue((self.installation / "python" / "python313.zip").is_file())
        self.assertFalse((self.installation / "src" / "owned.py").exists())


if __name__ == "__main__":
    unittest.main()
