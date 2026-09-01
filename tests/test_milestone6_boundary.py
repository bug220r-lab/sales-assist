from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import types
import unittest
import zipfile
from collections import Counter
from io import BytesIO
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "chrome_extension"
EXPECTED_EXTENSION_FILES = {
    "README.md",
    "content/content_script.js",
    "manifest.json",
    "package_inventory.json",
    "service_worker.js",
    "shared/canonical.js",
    "shared/contracts.js",
    "shared/extraction.js",
    "shared/origin.js",
    "side_panel/index.html",
    "side_panel/panel.css",
    "side_panel/panel.js",
}
EXPECTED_MANIFEST_RESOURCES = {
    "content/content_script.js",
    "service_worker.js",
    "shared/canonical.js",
    "shared/contracts.js",
    "shared/extraction.js",
    "shared/origin.js",
    "side_panel/index.html",
}


class Milestone6BoundaryTests(unittest.TestCase):
    @staticmethod
    def _packager() -> types.ModuleType:
        path = ROOT / "tools" / "package_milestone6_extension.py"
        name = "_synthetic_sales_assist_m6_packager_test"
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise AssertionError("packager module could not be loaded")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module

    def test_extension_file_inventory_is_exact(self) -> None:
        discovered = {
            path.relative_to(EXTENSION).as_posix()
            for path in EXTENSION.rglob("*")
            if path.is_file()
        }
        self.assertEqual(discovered, EXPECTED_EXTENSION_FILES)
        directories = {
            path.relative_to(EXTENSION).as_posix()
            for path in EXTENSION.iterdir()
            if path.is_dir()
        }
        self.assertEqual(directories, {"content", "shared", "side_panel"})

    def test_exactly_one_manifest_exists_at_the_authorized_m6_path(self) -> None:
        manifests = {
            path.relative_to(ROOT).as_posix()
            for path in ROOT.rglob("manifest.json")
            if ".git" not in path.parts and "__pycache__" not in path.parts
        }
        self.assertEqual(manifests, {"chrome_extension/manifest.json"})

    def test_manifest_resources_are_closed_and_repository_owned(self) -> None:
        manifest = json.loads((EXTENSION / "manifest.json").read_text(encoding="utf-8"))
        resources = {
            manifest["background"]["service_worker"],
            manifest["side_panel"]["default_path"],
            *manifest["content_scripts"][0]["js"],
        }
        self.assertEqual(resources, EXPECTED_MANIFEST_RESOURCES)
        for resource in resources:
            with self.subTest(resource=resource):
                path = EXTENSION / resource
                self.assertTrue(path.is_file())
                self.assertFalse(path.is_symlink())
                self.assertTrue(path.resolve().is_relative_to(EXTENSION.resolve()))

    def test_no_custom_icon_is_explicit_and_no_icon_asset_is_packaged(self) -> None:
        manifest = json.loads((EXTENSION / "manifest.json").read_text(encoding="utf-8"))
        self.assertNotIn("icons", manifest)
        self.assertNotIn("action", manifest)
        self.assertFalse((EXTENSION / "assets").exists())
        image_suffixes = {
            ".bmp",
            ".gif",
            ".ico",
            ".jpeg",
            ".jpg",
            ".png",
            ".svg",
            ".webp",
        }
        self.assertFalse(
            any(
                path.suffix.casefold() in image_suffixes
                for path in EXTENSION.rglob("*")
                if path.is_file()
            )
        )
        readme = (EXTENSION / "README.md").read_text(encoding="utf-8")
        self.assertIn("intentionally declares no custom icon", readme)
        self.assertIn("generated locally or repository-owned", readme)

    def test_checked_in_package_inventory_is_exact_and_hash_bound(self) -> None:
        inventory_path = EXTENSION / "package_inventory.json"
        raw_inventory = inventory_path.read_bytes()

        def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
            value: dict[str, object] = {}
            for key, member in pairs:
                if key in value:
                    raise ValueError("duplicate package inventory member")
                value[key] = member
            return value

        inventory = json.loads(
            raw_inventory.decode("utf-8"), object_pairs_hook=reject_duplicates
        )
        canonical_inventory = (
            json.dumps(
                inventory,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
            + b"\n"
        )
        self.assertEqual(raw_inventory, canonical_inventory)
        self.assertEqual(
            set(inventory),
            {
                "author_marker",
                "extension_version",
                "files",
                "inventory_excludes",
                "schema_version",
            },
        )
        self.assertEqual(
            inventory["schema_version"],
            "synthetic-sales-assist-extension-package-inventory/v1",
        )
        self.assertEqual(
            inventory["author_marker"], "SYNTHETIC-SALES-ASSIST-AUTHORED-M6"
        )
        self.assertEqual(inventory["extension_version"], "0.1.1")
        self.assertEqual(inventory["inventory_excludes"], ["package_inventory.json"])
        expected_paths = sorted(
            EXPECTED_EXTENSION_FILES - {"package_inventory.json"}, key=str.casefold
        )
        records = inventory["files"]
        self.assertEqual([record["path"] for record in records], expected_paths)
        for record in records:
            with self.subTest(path=record["path"]):
                self.assertEqual(set(record), {"path", "sha256", "size"})
                raw = (EXTENSION / record["path"]).read_bytes()
                self.assertEqual(record["size"], len(raw))
                self.assertEqual(record["sha256"], hashlib.sha256(raw).hexdigest())

    def test_extension_is_outside_business_packages_and_schema_is_unchanged(self) -> None:
        package = ROOT / "src" / "synthetic_sales_assist"
        self.assertFalse((package / "chrome_extension").exists())
        self.assertFalse((package / "extension").exists())
        self.assertEqual(
            {path.name for path in (ROOT / "migrations").iterdir() if path.is_file()},
            {
                "0001_foundation.sql",
                "0002_shared_persistence.sql",
                "0003_sales_credit_persistence.sql",
                "0004_doi_persistence.sql",
            },
        )

    def test_packager_has_no_network_install_or_repository_write_capability(self) -> None:
        path = ROOT / "tools" / "package_milestone6_extension.py"
        self.assertTrue(path.is_file())
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported: set[str] = set()
        calls: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    calls.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    calls.add(node.func.attr)
        self.assertFalse(
            imported
            & {
                "ftplib",
                "http.client",
                "requests",
                "socket",
                "subprocess",
                "urllib.request",
            }
        )
        self.assertFalse(calls & {"system", "popen", "run", "Popen", "urlopen"})
        source = path.read_text(encoding="utf-8").lower()
        self.assertNotIn("pip install", source)
        self.assertNotIn("npm install", source)
        self.assertNotIn("git ", source)

    def test_packager_uses_one_immutable_snapshot_and_duplicate_safe_json(self) -> None:
        source = (ROOT / "tools" / "package_milestone6_extension.py").read_text(
            encoding="utf-8"
        )
        required = (
            "class SnapshotFile:",
            "def _snapshot_files() -> tuple[SnapshotFile, ...]:",
            "object_pairs_hook=reject_duplicates",
            "def _manifest_from_snapshot(snapshot:",
            "def build_inventory(",
            "def check_package(",
            "def _zip_bytes(snapshot:",
            "snapshot = _snapshot_files()",
            "raw = _zip_bytes(snapshot)",
        )
        for fragment in required:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, source)

    def test_packager_cli_modes_are_required_and_mutually_exclusive(self) -> None:
        tool = ROOT / "tools" / "package_milestone6_extension.py"
        with tempfile.TemporaryDirectory(
            prefix="synthetic-sales-assist-m6-package-cli-"
        ) as output_directory:
            invalid_argv = (
                (),
                ("--check", "--print-inventory"),
                ("--check", "--output-dir", output_directory),
                ("--print-inventory", "--output-dir", output_directory),
            )
            for argv in invalid_argv:
                with self.subTest(argv=argv):
                    completed = subprocess.run(
                        [sys.executable, str(tool), *argv],
                        cwd=ROOT,
                        check=False,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=20,
                    )
                    self.assertEqual(completed.returncode, 2)
                    self.assertNotIn("PASS", completed.stdout)
                    self.assertNotIn("PASS", completed.stderr)

    def test_packager_lstats_unresolved_extension_root_before_resolve(self) -> None:
        source = (ROOT / "tools" / "package_milestone6_extension.py").read_text(
            encoding="utf-8"
        )
        lstat = "unresolved_root.stat(follow_symlinks=False)"
        resolved = "root = unresolved_root.resolve(strict=True)"
        self.assertIn(lstat, source)
        self.assertIn(resolved, source)
        self.assertLess(source.index(lstat), source.index(resolved))
        snapshot = source[
            source.index("def _snapshot_files()") :
            source.index("def _snapshot_member(")
        ]
        self.assertIn("files = _source_files()", snapshot)
        self.assertNotIn("_extension_root().resolve", snapshot)

    def test_packager_rejects_symlinked_extension_root_when_supported(self) -> None:
        packager = self._packager()
        with tempfile.TemporaryDirectory(
            prefix="synthetic-sales-assist-m6-package-root-"
        ) as directory:
            temporary = Path(directory)
            real_root = temporary / "real-extension"
            linked_root = temporary / "linked-extension"
            real_root.mkdir()
            try:
                linked_root.symlink_to(real_root, target_is_directory=True)
            except OSError as error:
                self.skipTest(f"directory symlink unavailable: {type(error).__name__}")
            with (
                mock.patch.object(
                    packager,
                    "_extension_root",
                    return_value=linked_root,
                ),
                self.assertRaisesRegex(
                    packager.PackageError,
                    "PACKAGE_ROOT_REPARSE_OR_NONDIRECTORY_PROHIBITED",
                ),
            ):
                packager._source_files()

    def test_packager_rejects_reparse_root_before_resolving(self) -> None:
        packager = self._packager()
        unresolved = mock.Mock()
        unresolved.stat.return_value = types.SimpleNamespace(
            st_file_attributes=getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400),
            st_mode=stat.S_IFDIR,
        )
        unresolved.is_symlink.return_value = False
        with (
            mock.patch.object(
                packager,
                "_extension_root",
                return_value=unresolved,
            ),
            self.assertRaisesRegex(
                packager.PackageError,
                "PACKAGE_ROOT_REPARSE_OR_NONDIRECTORY_PROHIBITED",
            ),
        ):
            packager._source_files()
        unresolved.resolve.assert_not_called()

    def test_packager_detects_descriptor_snapshot_change(self) -> None:
        packager = self._packager()
        with tempfile.TemporaryDirectory(
            prefix="synthetic-sales-assist-m6-package-source-"
        ) as directory:
            root = Path(directory).resolve()
            source = root / "manifest.json"
            source.write_bytes(b"stable source")
            real_fstat = os.fstat
            call_count = 0

            def changed_second_fstat(descriptor: int) -> object:
                nonlocal call_count
                value = real_fstat(descriptor)
                call_count += 1
                if call_count != 2:
                    return value
                return types.SimpleNamespace(
                    st_dev=value.st_dev,
                    st_ino=value.st_ino,
                    st_mode=value.st_mode,
                    st_nlink=value.st_nlink,
                    st_size=value.st_size + 1,
                    st_mtime_ns=value.st_mtime_ns,
                    st_file_attributes=getattr(value, "st_file_attributes", 0),
                )

            with (
                mock.patch.object(packager, "_repo_root", return_value=root),
                mock.patch.object(packager.os, "fstat", side_effect=changed_second_fstat),
                self.assertRaisesRegex(
                    packager.PackageError,
                    "PACKAGE_SOURCE_CHANGED_DURING_SNAPSHOT",
                ),
            ):
                packager._read_verified_source(source, root)

    def test_packager_rejects_hardlinked_output_and_uses_owned_atomic_temp(self) -> None:
        packager = self._packager()
        with tempfile.TemporaryDirectory(
            prefix="synthetic-sales-assist-m6-package-output-"
        ) as directory:
            root = Path(directory).resolve()
            target = root / "extension.zip"
            alias = root / "extension-alias.zip"
            target.write_bytes(b"preexisting")
            os.link(target, alias)
            with self.assertRaisesRegex(
                packager.PackageError, "PACKAGE_OUTPUT_TARGET_INVALID"
            ):
                packager._atomic_write(target, b"replacement")
            self.assertEqual(target.read_bytes(), b"preexisting")
            self.assertEqual(alias.read_bytes(), b"preexisting")

            alias.unlink()
            target.unlink()
            packager._atomic_write(target, b"first")
            packager._atomic_write(target, b"second")
            self.assertEqual(target.read_bytes(), b"second")
            self.assertEqual(
                tuple(root.glob(".extension.zip.tmp-*")),
                (),
            )

    def test_actual_package_path_is_deterministic_across_two_output_directories(self) -> None:
        packager = self._packager()
        with (
            tempfile.TemporaryDirectory(
                prefix="synthetic-sales-assist-m6-package-first-"
            ) as first_directory,
            tempfile.TemporaryDirectory(
                prefix="synthetic-sales-assist-m6-package-second-"
            ) as second_directory,
        ):
            first = packager.package(Path(first_directory))
            second = packager.package(Path(second_directory))
            first_package, first_digest, first_inventory, first_checksum = first
            second_package, second_digest, second_inventory, second_checksum = second
            package_name = "synthetic-sales-assist-m6-extension-0.1.1.zip"
            self.assertEqual(first_package.name, package_name)
            self.assertEqual(second_package.name, package_name)
            first_raw = first_package.read_bytes()
            second_raw = second_package.read_bytes()
            self.assertEqual(first_raw, second_raw)
            self.assertEqual(first_digest, second_digest)
            self.assertEqual(first_digest, hashlib.sha256(first_raw).hexdigest())
            generation_name = (
                "synthetic-sales-assist-m6-extension-0.1.1-" + first_digest
            )
            self.assertEqual(first_package.parent.name, generation_name)
            self.assertEqual(second_package.parent.name, generation_name)
            self.assertEqual(first_inventory.read_bytes(), second_inventory.read_bytes())
            self.assertEqual(first_checksum.read_bytes(), second_checksum.read_bytes())
            self.assertEqual(
                first_checksum.read_bytes(),
                f"{first_digest}  {package_name}\n".encode("ascii"),
            )

            external_inventory = json.loads(first_inventory.read_text(encoding="utf-8"))
            expected_records = []
            for relative in sorted(EXPECTED_EXTENSION_FILES, key=str.casefold):
                raw = (EXTENSION / relative).read_bytes()
                expected_records.append(
                    {
                        "path": relative,
                        "sha256": hashlib.sha256(raw).hexdigest(),
                        "size": len(raw),
                    }
                )
            self.assertEqual(
                external_inventory,
                {
                    "archive": package_name,
                    "archive_sha256": first_digest,
                    "archive_size": len(first_raw),
                    "author_marker": "SYNTHETIC-SALES-ASSIST-AUTHORED-M6",
                    "extension_version": "0.1.1",
                    "files": expected_records,
                    "schema_version": "synthetic-sales-assist-extension-package/v1",
                },
            )
            canonical_inventory = (
                json.dumps(
                    external_inventory,
                    allow_nan=False,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                )
                + "\n"
            ).encode("utf-8")
            self.assertEqual(first_inventory.read_bytes(), canonical_inventory)

            with zipfile.ZipFile(BytesIO(first_raw), mode="r") as archive:
                self.assertEqual(
                    archive.namelist(),
                    sorted(EXPECTED_EXTENSION_FILES, key=str.casefold),
                )
                for member in archive.infolist():
                    with self.subTest(member=member.filename):
                        self.assertEqual(member.date_time, (1980, 1, 1, 0, 0, 0))
                        self.assertEqual(member.create_system, 3)
                        self.assertEqual(member.external_attr >> 16, 0o100644)
                        self.assertEqual(
                            archive.read(member),
                            (EXTENSION / member.filename).read_bytes(),
                        )

    def test_failed_new_package_generation_preserves_prior_complete_generation(self) -> None:
        packager = self._packager()
        with tempfile.TemporaryDirectory(
            prefix="synthetic-sales-assist-m6-package-transaction-"
        ) as output_directory:
            output = Path(output_directory)
            first_package, _digest, first_inventory, first_checksum = packager.package(
                output
            )
            first_generation = first_package.parent
            prior = {
                path.name: path.read_bytes()
                for path in (first_package, first_inventory, first_checksum)
            }
            original_zip_bytes = packager._zip_bytes
            original_atomic_write = packager._atomic_write
            writes = 0

            def changed_zip_bytes(snapshot: object) -> bytes:
                return original_zip_bytes(snapshot) + b"transaction-failure-canary"

            def fail_second_stage_write(path: Path, raw: bytes) -> None:
                nonlocal writes
                writes += 1
                if writes == 2:
                    raise OSError("intentional package publication canary")
                original_atomic_write(path, raw)

            with (
                mock.patch.object(
                    packager, "_zip_bytes", side_effect=changed_zip_bytes
                ),
                mock.patch.object(
                    packager, "_atomic_write", side_effect=fail_second_stage_write
                ),
                self.assertRaisesRegex(OSError, "intentional package publication canary"),
            ):
                packager.package(output)

            self.assertEqual(
                {
                    path.name: path.read_bytes()
                    for path in first_generation.iterdir()
                    if path.is_file()
                },
                prior,
            )
            self.assertEqual(
                [path.name for path in output.iterdir()],
                [first_generation.name],
            )

    def test_browser_evidence_is_hash_bound_and_manual_scope_is_honest(self) -> None:
        evidence = (
            ROOT / "docs" / "acceptance" / "milestone6-browser-evidence.md"
        ).read_text(encoding="utf-8")
        rows = re.findall(
            r"^([a-z][a-z0-9_]*)=([0-9a-f]{64})$", evidence, re.MULTILINE
        )
        expected_components = {
            "baseline_evidence_bundle",
            "baseline_extension_package",
            "browser_user_agent",
            "canonical_source",
            "content_controller",
            "content_observations",
            "content_script_source",
            "contracts_source",
            "evaluating_observations",
            "extension_package",
            "extraction_source",
            "grammar_controller",
            "grammar_observations",
            "live_order",
            "manifest_source",
            "network_observations",
            "origin_source",
            "package_inventory_source",
            "panel_controller",
            "panel_observations",
            "panel_script_source",
            "renderer_source",
            "result_displays",
            "safety_counters",
            "service_worker_source",
        }
        counts = Counter(name for name, _digest in rows)
        self.assertEqual(set(counts), expected_components)
        self.assertEqual(len(rows), len(expected_components))
        self.assertTrue(all(count == 1 for count in counts.values()))
        components = dict(rows)
        preimage = json.dumps(
            components,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        aggregate = hashlib.sha256(preimage).hexdigest()
        aggregate_claims = re.findall(
            r"The final evidence-bundle SHA-256 is:\s*```text\s*"
            r"([0-9a-f]{64})\s*```",
            evidence,
        )
        self.assertEqual(aggregate_claims, [aggregate])
        historical_hashes = {
            "canonical_source": "3937612403f1e021d877fab047ecd44524c27ce854fd7354a6398599e1e7a8d7",
            "content_script_source": (
                "5d5240e74b2d0bc85a36c0b18a2d99ca4f6bc1064942543a783296af80f349d1"
            ),
            "contracts_source": "50f445072a954d4d87845409bf43adec07df2f49c9bdcc3e5fba35c65581f101",
            "extension_package": "acb0ff977e24d69a7d4fab0d1426ef5eba30c0d8ec9b86a1ab744a6b9319210d",
            "extraction_source": "f4dde4464a764a4bfedb20a4c091033e6af228bcde16ae08ac8ab8d9e85f2e9c",
            "manifest_source": "81e29390b08d19db4a29934be0f1b983fba0fa9808d0eabc3c34ff1e26ede53f",
            "origin_source": "44188f68a56e9c9498fc808d14a3a2216c38f3defcac7ef92cff9a9d87da081b",
            "package_inventory_source": (
                "366bc639e2be6c9be2ff349ce0995d76a4e574af101ef28b00c4aa7b376ce65a"
            ),
            "panel_script_source": (
                "ed3312cf24615634e04415eccf19bd3a375e8904886d3c71adaa646dce6ded36"
            ),
            "renderer_source": "b6e70ad5f2eadb451ed2a3597807a8c0646bbfe2914ca6d8d13c06c22db8f8a1",
            "service_worker_source": (
                "4d7f471720d6a1d22e67ab6e944abe6ab6138f4c52f06004f37497a84d1ae7b0"
            ),
        }
        for component, digest in historical_hashes.items():
            with self.subTest(component=component):
                self.assertEqual(components[component], digest)
        packager = self._packager()
        snapshot = packager._snapshot_files()
        self.assertNotEqual(
            components["extension_package"],
            hashlib.sha256(packager._zip_bytes(snapshot)).hexdigest(),
        )
        header_package_claims = re.findall(
            r"Final deterministic package SHA-256: `([0-9a-f]{64})`",
            evidence,
        )
        narrative_package_claims = re.findall(
            r"All final browser observations below are bound to package "
            r"`([0-9a-f]{64})`\.",
            evidence,
        )
        self.assertEqual(header_package_claims, [components["extension_package"]])
        self.assertEqual(narrative_package_claims, [components["extension_package"]])
        self.assertIn("Chrome/151.0.0.0", evidence)
        self.assertIn("operator-recorded", evidence)
        self.assertIn("M6_AUTOMATED_BROWSER_EVIDENCE = PASS", evidence)
        self.assertIn("M6_MANUAL_ACCEPTANCE = PENDING", evidence)
        self.assertNotIn("jlewi", evidence.lower())
        self.assertNotIn("C:\\Users\\", evidence)

        manual = (ROOT / "docs" / "milestone6-manual-acceptance.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("milestone6-browser-evidence.md", manual)
        self.assertIn("M6_MANUAL_ACCEPTANCE = PENDING", manual)

    def test_milestone7_dashboard_control_center_and_connector_artifacts_are_absent(
        self,
    ) -> None:
        forbidden = {
            "connector",
            "connectors",
            "control-center",
            "control_center",
            "dashboard",
            "milestone7",
        }
        violations = [
            path.relative_to(ROOT).as_posix()
            for base in (ROOT / "src", EXTENSION)
            for path in base.rglob("*")
            if path.name.lower() in forbidden
        ]
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
