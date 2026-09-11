"""Private-runtime integrity and selection without executing fixture executables."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")
IMPORT_PATHS = b"Lib\nDLLs\nLib/site-packages\n../src\n"


@unittest.skipUnless(os.name == "nt" and POWERSHELL, "Windows runtime selection")
class BundledPythonRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="synthetic-bundled-python-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "installation with spaces"
        (self.root / "scripts").mkdir(parents=True)
        shutil.copyfile(ROOT / "scripts" / "lifecycle-common.ps1",
                        self.root / "scripts" / "lifecycle-common.ps1")
        self.files = {
            "python/python.exe": b"fixture executable never executed",
            "python/python312._pth": IMPORT_PATHS,
            "python/Lib/site-packages/tzdata/__init__.py": b"__version__ = '2026.3'\n",
        }
        for name, raw in self.files.items():
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        self.manifest = {
            "schema": "synthetic-sales-assist-bundled-python/v1",
            "python_version": "3.12.14",
            "architecture": "windows-x86_64",
            "executable": "python/python.exe",
            "files": {name: hashlib.sha256(raw).hexdigest() for name, raw in self.files.items()},
        }
        self.metadata = {
            "schema": "synthetic-sales-assist-release-build/v1",
            "runtime_tier": "WINDOWS_X64_BUNDLED_CPYTHON_3_12",
            "bundled_runtime": {
                "manifest": "python-runtime.json",
                "sha256": "",
                "executable": "python/python.exe",
                "python_version": "3.12.14",
                "timezone_version": "2026.3",
            },
        }
        self.write_manifests()

    def write_manifests(self) -> None:
        raw = json.dumps(self.manifest).encode("utf-8")
        (self.root / "python-runtime.json").write_bytes(raw)
        self.metadata["bundled_runtime"]["sha256"] = hashlib.sha256(raw).hexdigest()
        (self.root / "release-build.json").write_text(json.dumps(self.metadata), encoding="utf-8")

    def select(self, explicit: str | None = None, *, prefix: str = "") -> dict[str, object]:
        environment = os.environ.copy()
        environment["SSA_TEST_INSTALLATION"] = str(self.root)
        environment["SSA_PYTHON"] = str(self.root / "missing development" / "python.exe")
        environment["SSA_TEST_EXPLICIT"] = explicit or ""
        command = r"""
            . (Join-Path $env:SSA_TEST_INSTALLATION 'scripts\lifecycle-common.ps1')
            $script:versionProbeCount = 0
            $script:dependencyProbeCount = 0
            function Invoke-SsaPythonVersionProbe {
                param($PythonPath, $AllowLogicalPathDifference)
                $script:versionProbeCount++
                return [PSCustomObject]@{ FinalPath = $PythonPath; ReportedPath = $PythonPath }
            }
            function Invoke-SsaBundledPythonProbe {
                param($PythonPath)
                $script:dependencyProbeCount++
            }
        """ + prefix + r"""
            try {
                $runtime = Select-SsaPythonRuntime -PythonPath $env:SSA_TEST_EXPLICIT `
                    -PythonPathWasBound (-not [string]::IsNullOrEmpty($env:SSA_TEST_EXPLICIT))
                @{ result = 'OK'; source = $runtime.Source; path = $runtime.Path;
                   ownership_paths = @($runtime.OwnershipPaths);
                   version_probes = $script:versionProbeCount;
                   dependency_probes = $script:dependencyProbeCount } | ConvertTo-Json -Compress
            }
            catch {
                @{ result = $_.Exception.Message; version_probes = $script:versionProbeCount;
                   dependency_probes = $script:dependencyProbeCount } | ConvertTo-Json -Compress
            }
        """
        result = subprocess.run(
            [str(POWERSHELL), "-NoProfile", "-NonInteractive", "-Command", command],
            env=environment, cwd=self.root, capture_output=True, text=True, timeout=30,
            check=False, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout.strip().splitlines()[-1])

    def assert_rejected(self, code: str, *, explicit: str | None = None) -> None:
        result = self.select(explicit)
        self.assertEqual(result["result"], code, result)
        self.assertEqual(result["version_probes"], 0, result)
        self.assertEqual(result["dependency_probes"], 0, result)

    def test_verified_bundle_wins_over_path_and_development_runtime(self) -> None:
        result = self.select()
        self.assertEqual(result["result"], "OK", result)
        self.assertEqual(result["source"], "BUNDLED")
        self.assertEqual(os.path.normcase(str(result["path"])),
                         os.path.normcase(str(self.root / "python" / "python.exe")))
        self.assertEqual(result["ownership_paths"], [result["path"]])
        self.assertEqual(result["version_probes"], 1)
        self.assertEqual(result["dependency_probes"], 1)

    def test_explicit_own_interpreter_is_allowed_but_external_override_is_rejected(self) -> None:
        result = self.select(str(self.root / "python" / "python.exe"))
        self.assertEqual(result["result"], "OK", result)
        self.assertEqual(result["source"], "BUNDLED")
        for explicit in ("python", str(self.root / "other" / "python.exe")):
            with self.subTest(explicit=explicit):
                self.assert_rejected("BUNDLED_PYTHON_OVERRIDE_PROHIBITED", explicit=explicit)

    def test_missing_required_runtime_or_manifest_never_falls_back(self) -> None:
        manifest_path = self.root / "python-runtime.json"
        manifest_path.unlink()
        self.assert_rejected("BUNDLED_PYTHON_METADATA_MISSING")
        self.write_manifests()
        (self.root / "python" / "python.exe").unlink()
        self.assert_rejected("BUNDLED_PYTHON_FILES_MISSING")

    def test_missing_release_metadata_with_bundle_never_falls_back(self) -> None:
        (self.root / "release-build.json").unlink()
        self.assert_rejected("BUNDLED_PYTHON_METADATA_MISSING")

    def test_runtime_manifest_hash_is_checked_before_executable_probe(self) -> None:
        path = self.root / "python-runtime.json"
        path.write_bytes(path.read_bytes() + b"\n")
        self.assert_rejected("BUNDLED_PYTHON_MANIFEST_MISMATCH")

    def test_modified_runtime_file_is_rejected_before_executable_probe(self) -> None:
        (self.root / "python" / "python.exe").write_bytes(b"changed fixture")
        self.assert_rejected("BUNDLED_PYTHON_FILE_MISMATCH")

    def test_unlisted_importable_file_is_rejected_before_executable_probe(self) -> None:
        (self.root / "python" / "Lib" / "sqlite3.py").write_bytes(b"unexpected fixture")
        self.assert_rejected("BUNDLED_PYTHON_UNLISTED_FILE")

    def test_import_paths_cannot_enable_site_or_load_outside_app(self) -> None:
        path = self.root / "python" / "python312._pth"
        for raw in (IMPORT_PATHS + b"import site\n", b"Lib\n../../unrelated\n"):
            with self.subTest(raw=raw):
                path.write_bytes(raw)
                self.manifest["files"]["python/python312._pth"] = hashlib.sha256(raw).hexdigest()
                self.write_manifests()
                self.assert_rejected("BUNDLED_PYTHON_IMPORT_PATH_INVALID")

    def test_manifest_paths_are_rejected_before_any_executable_probe(self) -> None:
        for name in ("python/../outside.py", "python/CON.txt", "python/file:stream",
                     "python/path./file.py", "python/file.py ", "elsewhere/file.py"):
            with self.subTest(name=name):
                self.manifest["files"][name] = "0" * 64
                self.write_manifests()
                self.assert_rejected("BUNDLED_PYTHON_MEMBER_INVALID")
                del self.manifest["files"][name]

    def test_manifest_metadata_must_match_the_package(self) -> None:
        for key, value in (("architecture", "windows-x86"), ("python_version", "3.13.0"),
                           ("executable", "python/other.exe"), ("schema", "unexpected/v1")):
            with self.subTest(key=key):
                previous = self.manifest[key]
                self.manifest[key] = value
                self.write_manifests()
                self.assert_rejected("BUNDLED_PYTHON_METADATA_INVALID")
                self.manifest[key] = previous

    def test_malformed_or_incomplete_release_metadata_is_rejected(self) -> None:
        path = self.root / "release-build.json"
        for raw in ("{", "null", "[]", "{}", json.dumps({
            "schema": "synthetic-sales-assist-release-build/v1",
            "runtime_tier": "WINDOWS_X64_BUNDLED_CPYTHON_3_12",
        })):
            with self.subTest(raw=raw):
                path.write_text(raw, encoding="utf-8")
                self.assert_rejected("BUNDLED_PYTHON_METADATA_INVALID")

    def test_removing_bundled_tier_does_not_allow_fallback_while_bundle_exists(self) -> None:
        del self.metadata["runtime_tier"]
        self.write_manifests()
        self.assert_rejected("BUNDLED_PYTHON_METADATA_INVALID")

    def test_dependency_failure_is_not_converted_to_a_fallback(self) -> None:
        result = self.select(prefix=r"""
            function Invoke-SsaBundledPythonProbe {
                param($PythonPath)
                $script:dependencyProbeCount++
                throw 'BUNDLED_PYTHON_PREFLIGHT_FAILED'
            }
        """)
        self.assertEqual(result["result"], "BUNDLED_PYTHON_PREFLIGHT_FAILED")
        self.assertEqual(result["version_probes"], 1)
        self.assertEqual(result["dependency_probes"], 1)

    def test_bundled_directory_junction_is_rejected_before_probe(self) -> None:
        target = self.root / "unrelated-runtime"
        target.mkdir()
        junction = self.root / "python" / "redirect"
        command = (
            "$ErrorActionPreference='Stop'; New-Item -ItemType Junction "
            "-Path $env:SSA_TEST_LINK -Target $env:SSA_TEST_TARGET | Out-Null"
        )
        environment = os.environ.copy()
        environment["SSA_TEST_LINK"] = str(junction)
        environment["SSA_TEST_TARGET"] = str(target)
        linked = subprocess.run(
            [str(POWERSHELL), "-NoProfile", "-Command", command], env=environment,
            capture_output=True, text=True, timeout=20, check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self.assertEqual(linked.returncode, 0, linked.stdout + linked.stderr)
        try:
            self.assert_rejected("BUNDLED_PYTHON_REPARSE_POINT")
        finally:
            junction.rmdir()

    def test_runtime_guard_failure_is_not_converted_to_a_fallback(self) -> None:
        result = self.select(prefix=r"""
            function Invoke-SsaPythonVersionProbe {
                param($PythonPath, $AllowLogicalPathDifference)
                $script:versionProbeCount++
                throw 'PYTHON_EXECUTABLE_IDENTITY_MISMATCH'
            }
        """)
        self.assertEqual(result["result"], "PYTHON_EXECUTABLE_IDENTITY_MISMATCH")
        self.assertEqual(result["version_probes"], 1)
        self.assertEqual(result["dependency_probes"], 0)

    def test_source_checkout_still_selects_path(self) -> None:
        (self.root / "release-build.json").unlink()
        (self.root / "python-runtime.json").unlink()
        for name in self.files:
            (self.root / name).unlink()
        (self.root / "python" / "Lib" / "site-packages" / "tzdata").rmdir()
        (self.root / "python" / "Lib" / "site-packages").rmdir()
        (self.root / "python" / "Lib").rmdir()
        (self.root / "python").rmdir()
        result = self.select(prefix=r"""
            function Resolve-SsaPythonCandidate {
                param($PythonPath, $Source, [switch]$RequireAbsolute)
                return [PSCustomObject]@{
                    Path = 'source-path'; Source = $Source; OwnershipPaths = @('source-path')
                }
            }
        """)
        self.assertEqual(result["result"], "OK", result)
        self.assertEqual(result["source"], "PATH")
        self.assertEqual(result["version_probes"], 0)
        self.assertEqual(result["dependency_probes"], 0)


if __name__ == "__main__":
    unittest.main()
