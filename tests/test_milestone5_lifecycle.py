from __future__ import annotations

import http.client
import json
import os
import queue
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SOURCE = ROOT / "src"
POWERSHELL = shutil.which("pwsh") or shutil.which("powershell")
WINDOWS_POWERSHELL = shutil.which("powershell")
RECEIPT_SCHEMA = "synthetic-sales-assist-runtime-receipt/v1"
API_SCHEMA = "synthetic-sales-assist-api/v1"
RECEIPT_MEMBERS = {
    "app_version",
    "build_version",
    "csrf_token",
    "database_path",
    "database_schema_version",
    "host",
    "origin",
    "pid",
    "port",
    "process_identity_token",
    "process_start_time",
    "schema_version",
    "shutdown_token",
}
STATUS_MEMBERS = {
    "app_version",
    "build_version",
    "data_dir",
    "database_path",
    "database_schema_version",
    "database_size_bytes",
    "last_health_status",
    "origin",
    "pid",
    "port",
    "safety_counters",
    "state",
}

_LIFECYCLE_BARRIER_READY = "SSA_TEST_LIFECYCLE_OPERATION_LOCK_READY"
_LIFECYCLE_BARRIER_RELEASE = "SSA_TEST_LIFECYCLE_OPERATION_LOCK_RELEASE"
_START_CLEANUP_READY = "SSA_TEST_START_CHILD_CLEANUP_READY"
_START_CLEANUP_RELEASE = "SSA_TEST_START_CHILD_CLEANUP_RELEASE"
_MAINTENANCE_BARRIER_READY = "SSA_TEST_SERVICE_MAINTENANCE_LEASE_READY"
_MAINTENANCE_BARRIER_RELEASE = "SSA_TEST_SERVICE_MAINTENANCE_LEASE_RELEASE"
_LIFECYCLE_BARRIER_COMMAND = r"""
$ErrorActionPreference = 'Stop'
if ($env:SSA_TEST_LIFECYCLE_BARRIER_TOKEN -cnotmatch '\A[0-9a-f]{64}\z') {
    throw 'SSA_TEST_LIFECYCLE_BARRIER_TOKEN_INVALID'
}
$global:SsaTestLifecycleBarrierReached = $false
function global:Push-Location {
    param([Parameter(Mandatory = $true)][string]$LiteralPath)
    $actual = [IO.Path]::GetFullPath($LiteralPath)
    $expected = [IO.Path]::GetFullPath($env:SSA_TEST_LIFECYCLE_SOURCE)
    if (
        -not $global:SsaTestLifecycleBarrierReached -and
        $actual.Equals($expected, [StringComparison]::OrdinalIgnoreCase)
    ) {
        $global:SsaTestLifecycleBarrierReached = $true
        [Console]::Out.WriteLine(
            'SSA_TEST_LIFECYCLE_OPERATION_LOCK_READY|' +
            $env:SSA_TEST_LIFECYCLE_BARRIER_TOKEN
        )
        [Console]::Out.Flush()
        $release = [Console]::In.ReadLine()
        if ($release -cne (
            'SSA_TEST_LIFECYCLE_OPERATION_LOCK_RELEASE|' +
            $env:SSA_TEST_LIFECYCLE_BARRIER_TOKEN
        )) {
            throw 'SSA_TEST_LIFECYCLE_BARRIER_RELEASE_INVALID'
        }
    }
    Microsoft.PowerShell.Management\Push-Location -LiteralPath $LiteralPath
}
if ($env:SSA_TEST_LIFECYCLE_OPERATION -ceq 'START') {
    & $env:SSA_TEST_LIFECYCLE_SCRIPT -DataDir $env:SSA_TEST_LIFECYCLE_DATA_DIR `
        -Port ([int]$env:SSA_TEST_LIFECYCLE_PORT) -NoBrowser
}
elseif ($env:SSA_TEST_LIFECYCLE_OPERATION -ceq 'RESET') {
    & $env:SSA_TEST_LIFECYCLE_SCRIPT -DataDir $env:SSA_TEST_LIFECYCLE_DATA_DIR `
        -ConfirmReset
}
else {
    throw 'SSA_TEST_LIFECYCLE_OPERATION_INVALID'
}
"""
_START_CLEANUP_BARRIER_COMMAND = r"""
$ErrorActionPreference = 'Stop'
if ($env:SSA_TEST_LIFECYCLE_BARRIER_TOKEN -cnotmatch '\A[0-9a-f]{64}\z') {
    throw 'SSA_TEST_LIFECYCLE_BARRIER_TOKEN_INVALID'
}
$global:SsaTestChildStarted = $false
function global:Start-Process {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true, Position = 0)][string]$FilePath,
        [object[]]$ArgumentList,
        [switch]$PassThru,
        [Diagnostics.ProcessWindowStyle]$WindowStyle,
        [string]$WorkingDirectory
    )
    if ($PassThru) {
        $global:SsaTestChildStarted = $true
        return Microsoft.PowerShell.Management\Start-Process @PSBoundParameters
    }
    if (-not $global:SsaTestChildStarted) {
        throw 'SSA_TEST_START_CHILD_NOT_STARTED'
    }
    [Console]::Out.WriteLine(
        'SSA_TEST_START_CHILD_CLEANUP_READY|' +
        $env:SSA_TEST_LIFECYCLE_BARRIER_TOKEN
    )
    [Console]::Out.Flush()
    $release = [Console]::In.ReadLine()
    if ($release -cne (
        'SSA_TEST_START_CHILD_CLEANUP_RELEASE|' +
        $env:SSA_TEST_LIFECYCLE_BARRIER_TOKEN
    )) {
        throw 'SSA_TEST_START_CHILD_CLEANUP_RELEASE_INVALID'
    }
    throw 'SSA_TEST_BROWSER_START_FAILED'
}
& $env:SSA_TEST_LIFECYCLE_SCRIPT -DataDir $env:SSA_TEST_LIFECYCLE_DATA_DIR `
    -Port ([int]$env:SSA_TEST_LIFECYCLE_PORT)
"""
_MAINTENANCE_BARRIER_COMMAND = r"""
$ErrorActionPreference = 'Stop'
if ($env:SSA_TEST_LIFECYCLE_BARRIER_TOKEN -cnotmatch '\A[0-9a-f]{64}\z') {
    throw 'SSA_TEST_LIFECYCLE_BARRIER_TOKEN_INVALID'
}
$global:SsaTestMaintenanceBarrierReached = $false
function global:Remove-Item {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string[]]$LiteralPath,
        [switch]$Force
    )
    if (
        -not $global:SsaTestMaintenanceBarrierReached -and
        $LiteralPath.Count -eq 1 -and
        [IO.Path]::GetFullPath($LiteralPath[0]).Equals(
            [IO.Path]::GetFullPath($env:SSA_TEST_LIFECYCLE_DATABASE),
            [StringComparison]::OrdinalIgnoreCase
        )
    ) {
        $global:SsaTestMaintenanceBarrierReached = $true
        [Console]::Out.WriteLine(
            'SSA_TEST_SERVICE_MAINTENANCE_LEASE_READY|' +
            $env:SSA_TEST_LIFECYCLE_BARRIER_TOKEN
        )
        [Console]::Out.Flush()
        $release = [Console]::In.ReadLine()
        if ($release -cne (
            'SSA_TEST_SERVICE_MAINTENANCE_LEASE_RELEASE|' +
            $env:SSA_TEST_LIFECYCLE_BARRIER_TOKEN
        )) {
            throw 'SSA_TEST_SERVICE_MAINTENANCE_RELEASE_INVALID'
        }
    }
    Microsoft.PowerShell.Management\Remove-Item @PSBoundParameters
}
& $env:SSA_TEST_LIFECYCLE_SCRIPT -DataDir $env:SSA_TEST_LIFECYCLE_DATA_DIR `
    -ConfirmReset
"""


@unittest.skipUnless(os.name == "nt" and POWERSHELL, "Windows PowerShell lifecycle test")
class Milestone5LifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="synthetic-sales-assist-m5-lifecycle-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.host_env = dict(os.environ)
        self.env = dict(os.environ)
        self.env.pop("PYTHONPATH", None)
        path_without_python = self.root / "path-without-python"
        path_without_python.mkdir()
        self.env["PATH"] = str(path_without_python)
        self.env["SSA_PYTHON"] = os.path.abspath(sys.executable)

    def tearDown(self) -> None:
        if (self.root / "runtime" / "service.json").exists():
            self._run("stop.ps1", timeout=20)

    def _run(
        self,
        script: str,
        *arguments: str,
        timeout: int = 30,
        data_dir: Path | str | None = None,
        env: dict[str, str] | None = None,
        python_path: str | None = None,
        powershell_path: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        command = self._script_command(
            script,
            *arguments,
            data_dir=data_dir,
            python_path=python_path,
            powershell_path=powershell_path,
        )
        return subprocess.run(
            command,
            cwd=SOURCE,
            env=self.env if env is None else env,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def _script_command(
        self,
        script: str,
        *arguments: str,
        data_dir: Path | str | None = None,
        python_path: str | None = None,
        powershell_path: str | None = None,
    ) -> list[str]:
        command = [
            str(POWERSHELL if powershell_path is None else powershell_path),
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPTS / script),
            "-DataDir",
            str(self.root if data_dir is None else data_dir),
        ]
        if python_path is not None:
            command.extend(("-PythonPath", python_path))
        command.extend(arguments)
        return command

    def _json(self, result: subprocess.CompletedProcess[str]) -> dict[str, object]:
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        self.assertTrue(lines, result.stderr)
        value = json.loads(lines[-1])
        self.assertIsInstance(value, dict)
        return value

    def _cli(self, *arguments: str) -> dict[str, object]:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "synthetic_sales_assist.cli",
                "--json",
                "--data-dir",
                str(self.root),
                *arguments,
            ],
            cwd=SOURCE,
            env=self.env,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        value = json.loads(result.stdout)
        self.assertTrue(value["ok"])
        return value

    def _initialize(self) -> Path:
        self._cli("db", "init")
        return self.root / "data" / "synthetic_sales_assist.sqlite3"

    def _reserve_port(self) -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            return int(listener.getsockname()[1])

    def _make_junction(self, link: Path, target: Path) -> None:
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def _run_with_python_path(
        self,
        script: str,
        python_path: str,
        *arguments: str,
    ) -> subprocess.CompletedProcess[str]:
        return self._run(
            script,
            *arguments,
            python_path=python_path,
            timeout=20,
        )

    def _run_common_command(
        self,
        command: str,
        *,
        env: dict[str, str] | None = None,
        timeout: int = 20,
    ) -> subprocess.CompletedProcess[str]:
        supplied_env = dict(self.env if env is None else env)
        supplied_env["SSA_LIFECYCLE_COMMON"] = str(SCRIPTS / "lifecycle-common.ps1")
        return subprocess.run(
            [
                str(POWERSHELL),
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                ". $env:SSA_LIFECYCLE_COMMON; " + command,
            ],
            cwd=SOURCE,
            env=supplied_env,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def _build_python_probe_stub(
        self,
        directory: Path,
        major: int,
        minor: int,
        implementation: str = "cpython",
    ) -> Path:
        if WINDOWS_POWERSHELL is None:
            self.skipTest("Windows PowerShell is required to compile a probe stub")
        directory.mkdir(parents=True, exist_ok=True)
        executable = directory / "python.exe"
        source = (
            "using System;\n"
            "using System.Diagnostics;\n"
            "public static class Program {\n"
            "  public static int Main(string[] args) {\n"
            "    string path = Process.GetCurrentProcess().MainModule.FileName;\n"
            f'    Console.WriteLine("SSA_PYTHON_PROBE_V1|{major}|{minor}|'
            f'{implementation}|" '
            "+ path + \"|\" + path);\n"
            "    return 0;\n"
            "  }\n"
            "}\n"
        )
        environment = dict(self.host_env)
        environment["SSA_STUB_OUTPUT"] = str(executable)
        environment["SSA_STUB_SOURCE"] = source
        result = subprocess.run(
            [
                str(WINDOWS_POWERSHELL),
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                "Add-Type -TypeDefinition $env:SSA_STUB_SOURCE -Language CSharp "
                "-OutputAssembly $env:SSA_STUB_OUTPUT -OutputType ConsoleApplication",
            ],
            cwd=SOURCE,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        self.assertTrue(executable.is_file())
        return executable

    def test_ssa_python_fallback_requires_an_absolute_existing_path(self) -> None:
        candidates = (
            ("python.exe", "PYTHON_PATH_ABSOLUTE_REQUIRED"),
            (str(self.root / "missing" / "python.exe"), "PYTHON_PATH_NOT_FOUND"),
        )
        for candidate, error_code in candidates:
            with self.subTest(error_code=error_code):
                environment = dict(self.env)
                environment["SSA_PYTHON"] = candidate
                result = self._run("status.ps1", env=environment)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(error_code, result.stderr)

    def test_ssa_python_rejects_wrong_name_and_non_python_executable(self) -> None:
        wrong_name = self.root / "not-python.exe"
        wrong_name.write_bytes(b"not-an-executable")
        environment = dict(self.env)
        environment["SSA_PYTHON"] = str(wrong_name)
        result = self._run("status.ps1", env=environment)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("PYTHON_EXECUTABLE_NAME_INVALID", result.stderr)

        invalid_python = self._build_python_probe_stub(
            self.root / "invalid-runtime",
            3,
            12,
            implementation="not-python",
        )
        environment["SSA_PYTHON"] = str(invalid_python)
        result = self._run("status.ps1", env=environment)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("PYTHON_IMPLEMENTATION_UNSUPPORTED", result.stderr)

    def test_ssa_python_full_probe_rejects_wrong_python_version(self) -> None:
        wrong_version = self._build_python_probe_stub(
            self.root / "python-3.11-stub",
            3,
            11,
        )
        environment = dict(self.env)
        environment["SSA_PYTHON"] = str(wrong_version)
        result = self._run("status.ps1", env=environment)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("PYTHON_VERSION_UNSUPPORTED", result.stderr)

    def test_ssa_python_rejects_unc_device_and_alternate_data_stream_paths(self) -> None:
        candidates = (
            r"\\server\share\python.exe",
            r"\\?\C:\synthetic\python.exe",
            r"C:\synthetic\python.exe:stream",
        )
        for candidate in candidates:
            with self.subTest(candidate=candidate):
                environment = dict(self.env)
                environment["SSA_PYTHON"] = candidate
                result = self._run("status.ps1", env=environment)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("PYTHON_PATH_", result.stderr)

    def test_ssa_python_rejects_an_arbitrary_reparse_runtime(self) -> None:
        target = tempfile.TemporaryDirectory(
            prefix="synthetic-sales-assist-m5-ssa-python-target-"
        )
        self.addCleanup(target.cleanup)
        target_path = Path(target.name)
        (target_path / "python.exe").write_bytes(b"not-an-executable")
        link = self.root / "arbitrary-python-runtime"
        self._make_junction(link, target_path)
        environment = dict(self.env)
        environment["SSA_PYTHON"] = str(link / "python.exe")
        result = self._run("status.ps1", env=environment)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("PYTHON_PATH_REPARSE_POINT", result.stderr)

    def test_final_path_rejection_precedes_python_version_probe(self) -> None:
        stub = self._build_python_probe_stub(self.root / "final-path-ordering", 3, 12)
        environment = dict(self.env)
        environment["SSA_TEST_LOCAL_PYTHON"] = str(stub)
        command = (
            "$script:probeCalled = $false; "
            "function Get-SsaFinalExecutablePath { "
            "throw 'PYTHON_FINAL_PATH_NETWORK_OR_DEVICE_PROHIBITED' }; "
            "function Invoke-SsaPythonVersionProbe { "
            "$script:probeCalled = $true; throw 'VERSION_PROBE_WAS_CALLED' }; "
            "$resolutionError = $null; "
            "try { [void](Resolve-SsaPythonCandidate "
            "-PythonPath $env:SSA_TEST_LOCAL_PYTHON "
            "-Source 'SSA_PYTHON_DEVELOPMENT_NONPORTABLE' -RequireAbsolute) } "
            "catch { $resolutionError = $_.Exception.Message }; "
            "if ($resolutionError -cne "
            "'PYTHON_FINAL_PATH_NETWORK_OR_DEVICE_PROHIBITED') { "
            "throw 'FINAL_PATH_REJECTION_WAS_NOT_PRESERVED' }; "
            "if ($script:probeCalled) { throw 'VERSION_PROBE_WAS_CALLED' }; "
            "'PASS'"
        )
        result = self._run_common_command(command, env=environment)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        self.assertEqual(result.stdout.strip(), "PASS")

    def test_exact_logical_codex_reparse_exemption_is_source_bound(self) -> None:
        link = self.root / "logical-codex-python"
        self._make_junction(link, Path(os.path.abspath(sys.executable)).parent)
        logical_python = link / "python.exe"
        environment = dict(self.env)
        environment["SSA_TEST_CODEX_PYTHON"] = str(logical_python)
        command = (
            "function Get-SsaVerifiedCodexPythonPath { "
            "return $env:SSA_TEST_CODEX_PYTHON }; "
            "$parameterError = $null; "
            "try { [void](Resolve-SsaPythonCandidate "
            "-PythonPath $env:SSA_TEST_CODEX_PYTHON -Source 'PARAMETER') } "
            "catch { $parameterError = $_.Exception.Message }; "
            "if ($parameterError -cne 'PYTHON_CODEX_RUNTIME_REQUIRES_SSA_PYTHON') { "
            "throw 'PARAMETER_SOURCE_WAS_NOT_REJECTED' }; "
            "$runtime = Resolve-SsaPythonCandidate "
            "-PythonPath $env:SSA_TEST_CODEX_PYTHON "
            "-Source 'SSA_PYTHON_DEVELOPMENT_NONPORTABLE' -RequireAbsolute; "
            "$runtime | ConvertTo-Json -Compress"
        )
        result = self._run_common_command(command, env=environment)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        runtime = json.loads(result.stdout.splitlines()[-1])
        self.assertEqual(runtime["Source"], "SSA_PYTHON_DEVELOPMENT_NONPORTABLE")
        self.assertTrue(runtime["IsVerifiedCodexRuntime"])
        self.assertEqual(
            os.path.normcase(runtime["RequestedPath"]),
            os.path.normcase(str(logical_python)),
        )
        self.assertEqual(
            os.path.normcase(runtime["Path"]),
            os.path.normcase(os.path.realpath(sys.executable)),
        )
        self.assertEqual(
            {os.path.normcase(path) for path in runtime["OwnershipPaths"]},
            {os.path.normcase(os.path.realpath(sys.executable))},
        )

    def test_normal_path_python_is_preferred_over_ssa_python_fallback(self) -> None:
        stub = self._build_python_probe_stub(self.root / "normal-path-python", 3, 12)
        environment = dict(self.env)
        environment["PATH"] = str(stub.parent)
        environment["SSA_PYTHON"] = str(self.root / "missing-fallback" / "python.exe")
        command = (
            "$runtime = Select-SsaPythonRuntime -PythonPath $null "
            "-PythonPathWasBound $false; $runtime | ConvertTo-Json -Compress"
        )
        result = self._run_common_command(command, env=environment)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        runtime = json.loads(result.stdout.splitlines()[-1])
        self.assertEqual(runtime["Source"], "PATH")
        self.assertFalse(runtime["IsVerifiedCodexRuntime"])
        self.assertEqual(os.path.normcase(runtime["Path"]), os.path.normcase(str(stub)))

    def test_verified_codex_ssa_python_runs_loopback_lifecycle_with_zero_counters(
        self,
    ) -> None:
        codex_python = os.path.abspath(sys.executable)
        expected_codex_python = os.path.abspath(
            Path.home()
            / ".cache"
            / "codex-runtimes"
            / "codex-primary-runtime"
            / "dependencies"
            / "python"
            / "python.exe"
        )
        if os.path.normcase(codex_python) != os.path.normcase(expected_codex_python):
            self.skipTest("the verified Codex primary runtime is not the test interpreter")
        rejected = self._run_with_python_path("status.ps1", codex_python)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("PYTHON_CODEX_RUNTIME_REQUIRES_SSA_PYTHON", rejected.stderr)

        port = self._reserve_port()
        started = self._run(
            "start.ps1",
            "-Port",
            str(port),
            "-NoBrowser",
            timeout=60,
        )
        self.assertEqual(started.returncode, 0, started.stderr or started.stdout)
        self.assertIn("DEVELOPMENT / NONPORTABLE", started.stderr)
        start_report = self._json(started)
        self.assertEqual(start_report["origin"], f"http://127.0.0.1:{port}")

        receipt = json.loads(
            (self.root / "runtime" / "service.json").read_text(encoding="utf-8")
        )
        self.assertEqual(receipt["host"], "127.0.0.1")
        self.assertEqual(receipt["origin"], f"http://127.0.0.1:{port}")

        status = self._run("status.ps1")
        self.assertEqual(status.returncode, 0, status.stderr or status.stdout)
        self.assertIn("DEVELOPMENT / NONPORTABLE", status.stderr)
        status_report = self._json(status)
        self.assertEqual(status_report["state"], "RUNNING")
        self.assertEqual(status_report["last_health_status"], "PASS")
        self.assertEqual(status_report["origin"], f"http://127.0.0.1:{port}")
        counters = status_report["safety_counters"]
        self.assertEqual(len(counters), 9)
        self.assertEqual(set(counters.values()), {0})

        stopped = self._run("stop.ps1", timeout=30)
        self.assertEqual(stopped.returncode, 0, stopped.stderr or stopped.stdout)
        self.assertIn("DEVELOPMENT / NONPORTABLE", stopped.stderr)
        self.assertEqual(self._json(stopped)["state"], "STOPPED")
        self.assertFalse((self.root / "runtime" / "service.json").exists())

    def test_windows_powershell_status_uses_codex_ssa_python_fallback(self) -> None:
        if WINDOWS_POWERSHELL is None:
            self.skipTest("Windows PowerShell 5.1 is unavailable")
        codex_python = os.path.abspath(sys.executable)
        expected_codex_python = os.path.abspath(
            Path.home()
            / ".cache"
            / "codex-runtimes"
            / "codex-primary-runtime"
            / "dependencies"
            / "python"
            / "python.exe"
        )
        if os.path.normcase(codex_python) != os.path.normcase(expected_codex_python):
            self.skipTest("the verified Codex primary runtime is not the test interpreter")
        result = self._run("status.ps1", powershell_path=WINDOWS_POWERSHELL)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        self.assertIn("DEVELOPMENT / NONPORTABLE", result.stderr)
        status = self._json(result)
        self.assertEqual(status["state"], "STOPPED")
        counters = status["safety_counters"]
        self.assertEqual(len(counters), 9)
        self.assertEqual(set(counters.values()), {0})

    def _assert_operation_lock_held(self, process: subprocess.Popen[str]) -> None:
        import msvcrt

        self.assertIsNone(process.poll(), "lifecycle holder exited after READY")
        lock_path = self.root / "runtime" / "lifecycle-operation.lock"
        self.assertTrue(lock_path.is_file())
        acquired = False
        with lock_path.open("r+b", buffering=0) as stream:
            stream.seek(0)
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                acquired = True
            except OSError:
                pass
            finally:
                if acquired:
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        self.assertFalse(acquired, "READY was emitted without the operation lock")

    def _assert_operation_lock_available(self, data_dir: Path | None = None) -> None:
        import msvcrt

        selected_root = self.root if data_dir is None else data_dir
        lock_path = selected_root / "runtime" / "lifecycle-operation.lock"
        self.assertTrue(lock_path.is_file())
        with lock_path.open("r+b", buffering=0) as stream:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)

    def _read_barrier_line(self, process: subprocess.Popen[str]) -> str:
        assert process.stdout is not None
        lines: queue.Queue[str] = queue.Queue(maxsize=1)
        threading.Thread(
            target=lambda: lines.put(process.stdout.readline()),
            daemon=True,
        ).start()
        try:
            return lines.get(timeout=30)
        except queue.Empty:
            self._abort_lifecycle_holder(process)
            self.fail("lifecycle holder did not reach the explicit lock barrier")

    def _abort_lifecycle_holder(self, process: subprocess.Popen[str]) -> None:
        failed_to_exit = False
        if process.poll() is None:
            process.kill()
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                failed_to_exit = True
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None and not stream.closed:
                stream.close()
        if failed_to_exit:
            self.fail("killed lifecycle holder did not exit")

    @contextmanager
    def _lifecycle_operation_barrier(
        self,
        operation: str,
        *,
        port: int | None = None,
    ) -> Iterator[tuple[subprocess.Popen[str], str]]:
        self.assertIn(operation, {"START", "RESET"})
        if operation == "START":
            self.assertIsNotNone(port)
        selected_root = self.root
        temporary_root = Path(tempfile.gettempdir()).resolve()
        self.assertEqual(selected_root.parent, temporary_root)
        self.assertTrue(
            selected_root.name.startswith("synthetic-sales-assist-m5-lifecycle-")
        )
        nonce = secrets.token_hex(32)
        environment = dict(self.env)
        environment.update(
            {
                "SSA_TEST_LIFECYCLE_BARRIER_TOKEN": nonce,
                "SSA_TEST_LIFECYCLE_DATA_DIR": str(selected_root),
                "SSA_TEST_LIFECYCLE_OPERATION": operation,
                "SSA_TEST_LIFECYCLE_PORT": str(0 if port is None else port),
                "SSA_TEST_LIFECYCLE_SCRIPT": str(
                    SCRIPTS
                    / ("start.ps1" if operation == "START" else "reset-demo.ps1")
                ),
                "SSA_TEST_LIFECYCLE_SOURCE": str(SOURCE),
            }
        )
        process = subprocess.Popen(
            [
                str(POWERSHELL),
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                _LIFECYCLE_BARRIER_COMMAND,
            ],
            cwd=SOURCE,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        try:
            ready = self._read_barrier_line(process).rstrip("\r\n")
            self.assertEqual(ready, f"{_LIFECYCLE_BARRIER_READY}|{nonce}")
            self._assert_operation_lock_held(process)
            yield process, nonce
        finally:
            self._abort_lifecycle_holder(process)

    def _release_lifecycle_holder(
        self,
        process: subprocess.Popen[str],
        nonce: str,
        *,
        supplied_nonce: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        release_nonce = nonce if supplied_nonce is None else supplied_nonce
        try:
            stdout, stderr = process.communicate(
                input=f"{_LIFECYCLE_BARRIER_RELEASE}|{release_nonce}\n",
                timeout=60,
            )
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate(timeout=5)
            self.fail(f"released lifecycle holder did not exit: {stderr or stdout}")
        return subprocess.CompletedProcess(
            process.args,
            process.returncode,
            stdout,
            stderr,
        )

    @contextmanager
    def _start_child_cleanup_barrier(
        self,
        port: int,
    ) -> Iterator[tuple[subprocess.Popen[str], str]]:
        nonce = secrets.token_hex(32)
        environment = dict(self.env)
        environment.update(
            {
                "SSA_TEST_LIFECYCLE_BARRIER_TOKEN": nonce,
                "SSA_TEST_LIFECYCLE_DATA_DIR": str(self.root),
                "SSA_TEST_LIFECYCLE_PORT": str(port),
                "SSA_TEST_LIFECYCLE_SCRIPT": str(SCRIPTS / "start.ps1"),
            }
        )
        process = subprocess.Popen(
            [
                str(POWERSHELL),
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                _START_CLEANUP_BARRIER_COMMAND,
            ],
            cwd=SOURCE,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        try:
            ready = self._read_barrier_line(process).rstrip("\r\n")
            self.assertEqual(ready, f"{_START_CLEANUP_READY}|{nonce}")
            self._assert_operation_lock_held(process)
            yield process, nonce
        finally:
            self._abort_lifecycle_holder(process)

    def _release_start_child_cleanup_holder(
        self,
        process: subprocess.Popen[str],
        nonce: str,
    ) -> subprocess.CompletedProcess[str]:
        try:
            stdout, stderr = process.communicate(
                input=f"{_START_CLEANUP_RELEASE}|{nonce}\n",
                timeout=60,
            )
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate(timeout=5)
            self.fail(f"start cleanup holder did not exit: {stderr or stdout}")
        return subprocess.CompletedProcess(
            process.args,
            process.returncode,
            stdout,
            stderr,
        )

    def _assert_service_maintenance_lease_held(
        self,
        process: subprocess.Popen[str],
    ) -> None:
        import msvcrt

        self.assertIsNone(process.poll(), "reset exited after maintenance READY")
        lock_path = self.root / "runtime" / "service.json.lock"
        self.assertTrue(lock_path.is_file())
        self.assertGreaterEqual(lock_path.stat().st_size, 64)
        acquired = False
        with lock_path.open("r+b", buffering=0) as stream:
            stream.seek(64)
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                acquired = True
            except OSError:
                pass
            finally:
                if acquired:
                    stream.seek(64)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        self.assertFalse(acquired, "READY was emitted without the maintenance lease")

    @contextmanager
    def _service_maintenance_barrier(
        self,
    ) -> Iterator[tuple[subprocess.Popen[str], str]]:
        nonce = secrets.token_hex(32)
        environment = dict(self.env)
        environment.update(
            {
                "SSA_TEST_LIFECYCLE_BARRIER_TOKEN": nonce,
                "SSA_TEST_LIFECYCLE_DATABASE": str(
                    self.root / "data" / "synthetic_sales_assist.sqlite3"
                ),
                "SSA_TEST_LIFECYCLE_DATA_DIR": str(self.root),
                "SSA_TEST_LIFECYCLE_SCRIPT": str(SCRIPTS / "reset-demo.ps1"),
            }
        )
        process = subprocess.Popen(
            [
                str(POWERSHELL),
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                _MAINTENANCE_BARRIER_COMMAND,
            ],
            cwd=SOURCE,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        try:
            ready = self._read_barrier_line(process).rstrip("\r\n")
            self.assertEqual(ready, f"{_MAINTENANCE_BARRIER_READY}|{nonce}")
            self._assert_service_maintenance_lease_held(process)
            yield process, nonce
        finally:
            self._abort_lifecycle_holder(process)

    def _release_service_maintenance_holder(
        self,
        process: subprocess.Popen[str],
        nonce: str,
    ) -> subprocess.CompletedProcess[str]:
        try:
            stdout, stderr = process.communicate(
                input=f"{_MAINTENANCE_BARRIER_RELEASE}|{nonce}\n",
                timeout=60,
            )
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate(timeout=5)
            self.fail(f"maintenance holder did not exit: {stderr or stdout}")
        return subprocess.CompletedProcess(
            process.args,
            process.returncode,
            stdout,
            stderr,
        )

    def _receipt(self, pid: int, *, equal_tokens: bool = False) -> dict[str, object]:
        csrf = "a" * 64
        shutdown = csrf if equal_tokens else "b" * 64
        return {
            "app_version": "0.1.0",
            "build_version": "test-build",
            "csrf_token": csrf,
            "database_path": str(
                self.root / "data" / "synthetic_sales_assist.sqlite3"
            ),
            "database_schema_version": 4,
            "host": "127.0.0.1",
            "origin": "http://127.0.0.1:8765",
            "pid": pid,
            "port": 8765,
            "process_identity_token": "c" * 64,
            "process_start_time": datetime.now(timezone.utc).isoformat(
                timespec="microseconds"
            ).replace("+00:00", "Z"),
            "schema_version": RECEIPT_SCHEMA,
            "shutdown_token": shutdown,
        }

    def _write_receipt(self, value: dict[str, object]) -> tuple[Path, Path]:
        runtime = self.root / "runtime"
        runtime.mkdir(parents=True, exist_ok=True)
        receipt = runtime / "service.json"
        receipt.write_text(
            json.dumps(value, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        lock = runtime / "service.json.lock"
        lock.write_text(str(value["process_identity_token"]), encoding="ascii")
        return receipt, lock

    def test_status_reports_stopped_without_initializing_default_storage(self) -> None:
        result = self._run("status.ps1")
        self.assertEqual(result.returncode, 0, result.stderr)
        status = self._json(result)
        self.assertEqual(set(status), STATUS_MEMBERS)
        self.assertEqual(status["state"], "STOPPED")
        self.assertEqual(status["app_version"], "0.1.0")
        self.assertEqual(status["build_version"], "synthetic-sales-assist-m5/v1")
        self.assertIsNone(status["database_schema_version"])
        self.assertEqual(status["database_size_bytes"], 0)
        self.assertIsNone(status["pid"])
        self.assertIsNone(status["origin"])
        self.assertIsNone(status["port"])
        self.assertEqual(set(status["safety_counters"].values()), {0})

    def test_status_reports_closed_unavailable_fields_for_corrupt_stopped_database(
        self,
    ) -> None:
        database = self.root / "data" / "synthetic_sales_assist.sqlite3"
        database.parent.mkdir(parents=True)
        database.write_bytes(b"not-a-sqlite-database")
        result = self._run("status.ps1")
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        status = self._json(result)
        self.assertEqual(set(status), STATUS_MEMBERS)
        self.assertEqual(status["state"], "STOPPED")
        self.assertEqual(status["last_health_status"], "NOT_RUNNING")
        self.assertIsNone(status["database_schema_version"])
        self.assertEqual(status["database_size_bytes"], len(b"not-a-sqlite-database"))
        self.assertEqual(len(status["safety_counters"]), 9)
        self.assertEqual(set(status["safety_counters"].values()), {None})

    def test_reset_without_confirmation_is_a_byte_preserving_rejection(self) -> None:
        sentinel = self.root / "unrelated.keep"
        sentinel.write_bytes(b"unchanged")
        result = self._run("reset-demo.ps1")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(sentinel.read_bytes(), b"unchanged")
        self.assertFalse((self.root / "data").exists())

    def test_confirmed_reset_backs_up_preserves_sentinel_and_deep_verifies(self) -> None:
        database = self._initialize()
        sentinel = self.root / "unrelated.keep"
        sentinel.write_bytes(b"unchanged")
        result = self._run("reset-demo.ps1", "-ConfirmReset", timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        self.assertIn("DEVELOPMENT / NONPORTABLE", result.stderr)
        report = self._json(result)
        self.assertEqual(report["state"], "RESET")
        self.assertTrue(report["verified"])
        self.assertEqual(report["database_schema_version"], 4)
        self.assertTrue(database.is_file())
        self.assertEqual(sentinel.read_bytes(), b"unchanged")
        backup = Path(str(report["backup_path"]))
        self.assertTrue(backup.is_file())
        self.assertTrue(Path(str(backup) + ".receipt.json").is_file())
        verification = self._cli("db", "verify", "--deep")
        self.assertTrue(verification["result"]["healthy"])

    def test_running_service_reset_backs_up_m5_state_then_stops_and_clears_it(
        self,
    ) -> None:
        sentinel = self.root / "unrelated.keep"
        sentinel.write_bytes(b"unchanged")
        port = self._reserve_port()
        started = self._run(
            "start.ps1",
            "-Port",
            str(port),
            "-NoBrowser",
            timeout=60,
        )
        self.assertEqual(started.returncode, 0, started.stderr or started.stdout)
        receipt_path = self.root / "runtime" / "service.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

        def request(method: str, target: str, body: bytes | None = None) -> tuple[int, bytes]:
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            headers = {"Host": f"127.0.0.1:{port}"}
            if method == "POST":
                headers.update(
                    {
                        "Content-Type": "application/json",
                        "Origin": receipt["origin"],
                        "X-SSA-CSRF-Token": receipt["csrf_token"],
                    }
                )
            try:
                connection.request(method, target, body=body, headers=headers)
                response = connection.getresponse()
                return response.status, response.read()
            finally:
                connection.close()

        instantiate_body = json.dumps(
            {
                "mode": "complete",
                "request_key": "LIFECYCLE-RESET-INSTANTIATE-1",
                "schema_version": "synthetic-sales-assist-api-request/v1",
            },
            separators=(",", ":"),
        ).encode("utf-8")
        status, raw = request(
            "POST",
            "/api/v1/scenarios/doi-overlap/instantiate",
            instantiate_body,
        )
        self.assertEqual(status, 201, raw)
        order_id = json.loads(raw)["data"]["order_id"]
        evaluate_body = json.dumps(
            {
                "request_key": "LIFECYCLE-RESET-EVALUATE-1",
                "schema_version": "synthetic-sales-assist-api-request/v1",
            },
            separators=(",", ":"),
        ).encode("utf-8")
        status, raw = request(
            "POST",
            f"/api/v1/orders/{order_id}/evaluate",
            evaluate_body,
        )
        self.assertEqual(status, 200, raw)
        status, raw = request("GET", f"/api/v1/orders/{order_id}/history")
        self.assertEqual(status, 200, raw)
        self.assertTrue(json.loads(raw)["data"]["attempt_receipts"])

        database = self.root / "data" / "synthetic_sales_assist.sqlite3"
        with closing(sqlite3.connect(database)) as connection:
            before = {
                "m5_commands": int(
                    connection.execute(
                        "SELECT COUNT(*) FROM durable_commands "
                        "WHERE natural_namespace LIKE 'application.scenario_%'"
                    ).fetchone()[0]
                ),
                "doi_evaluations": int(
                    connection.execute("SELECT COUNT(*) FROM doi_evaluations").fetchone()[0]
                ),
                "telemetry": int(
                    connection.execute("SELECT COUNT(*) FROM processing_telemetry").fetchone()[0]
                ),
            }
        self.assertTrue(all(value > 0 for value in before.values()), before)

        reset = self._run("reset-demo.ps1", "-ConfirmReset", timeout=90)
        self.assertEqual(reset.returncode, 0, reset.stderr or reset.stdout)
        report = self._json(reset)
        backup = Path(str(report["backup_path"]))
        self.assertTrue(backup.is_file())
        self.assertTrue(Path(str(backup) + ".receipt.json").is_file())
        self.assertEqual(sentinel.read_bytes(), b"unchanged")
        self.assertFalse(receipt_path.exists())
        self.assertFalse((self.root / "runtime" / "service.json.lock").exists())

        with closing(sqlite3.connect(backup)) as connection:
            self.assertGreater(
                int(
                    connection.execute(
                        "SELECT COUNT(*) FROM durable_commands "
                        "WHERE natural_namespace LIKE 'application.scenario_%'"
                    ).fetchone()[0]
                ),
                0,
            )
            self.assertGreater(
                int(connection.execute("SELECT COUNT(*) FROM doi_evaluations").fetchone()[0]),
                0,
            )
        with closing(sqlite3.connect(database)) as connection:
            after = {
                "m5_commands": int(
                    connection.execute(
                        "SELECT COUNT(*) FROM durable_commands "
                        "WHERE natural_namespace LIKE 'application.scenario_%'"
                    ).fetchone()[0]
                ),
                "doi_evaluations": int(
                    connection.execute("SELECT COUNT(*) FROM doi_evaluations").fetchone()[0]
                ),
                "telemetry": int(
                    connection.execute("SELECT COUNT(*) FROM processing_telemetry").fetchone()[0]
                ),
            }
        self.assertEqual(after, {name: 0 for name in before})

        stopped = self._run("status.ps1")
        self.assertEqual(stopped.returncode, 0, stopped.stderr or stopped.stdout)
        stopped_report = self._json(stopped)
        self.assertEqual(stopped_report["state"], "STOPPED")
        self.assertEqual(stopped_report["database_schema_version"], 4)
        self.assertEqual(stopped_report["last_health_status"], "NOT_RUNNING")

    def test_stale_receipt_is_removed_only_after_absent_pid_and_lock_acquisition(self) -> None:
        receipt, lock = self._write_receipt(self._receipt(2_147_483_000))
        result = self._run("stop.ps1")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = self._json(result)
        self.assertEqual(report["state"], "STOPPED")
        self.assertTrue(report["stale"])
        self.assertFalse(receipt.exists())
        self.assertFalse(lock.exists())

    def test_status_uses_closed_member_set_for_stale_receipt(self) -> None:
        receipt_value = self._receipt(2_147_483_000)
        self._write_receipt(receipt_value)
        result = self._run("status.ps1")
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        status = self._json(result)
        self.assertEqual(set(status), STATUS_MEMBERS)
        self.assertEqual(status["state"], "STALE")
        self.assertEqual(status["app_version"], receipt_value["app_version"])
        self.assertEqual(status["build_version"], receipt_value["build_version"])
        self.assertEqual(
            status["database_schema_version"],
            receipt_value["database_schema_version"],
        )
        self.assertEqual(status["database_size_bytes"], 0)
        self.assertEqual(status["origin"], receipt_value["origin"])
        self.assertEqual(status["pid"], receipt_value["pid"])
        self.assertEqual(status["port"], receipt_value["port"])

    def test_status_reports_running_unavailable_without_losing_closed_json(self) -> None:
        import msvcrt

        self._initialize()
        sleeper = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            cwd=SOURCE,
            env=self.env,
        )

        def cleanup_sleeper() -> None:
            if sleeper.poll() is None:
                sleeper.kill()
            sleeper.wait(timeout=5)

        self.addCleanup(cleanup_sleeper)
        value = self._receipt(sleeper.pid)
        port = self._reserve_port()
        value["port"] = port
        value["origin"] = f"http://127.0.0.1:{port}"
        _receipt, lock = self._write_receipt(value)
        with lock.open("r+b", buffering=0) as stream:
            stream.seek(64)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            try:
                result = self._run("status.ps1")
            finally:
                stream.seek(64)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        status = self._json(result)
        self.assertEqual(set(status), STATUS_MEMBERS)
        self.assertEqual(status["state"], "RUNNING")
        self.assertEqual(status["last_health_status"], "UNAVAILABLE")
        self.assertEqual(set(status["safety_counters"].values()), {0})

    def test_status_reports_live_unhealthy_service_as_fail(self) -> None:
        import msvcrt

        self._initialize()
        port = self._reserve_port()
        body = json.dumps(
            {"data": {"status": "FAIL"}, "schema_version": API_SCHEMA},
            sort_keys=True,
            separators=(",", ":"),
        )
        program = (
            "import socket,time\n"
            f"body={body.encode('utf-8')!r}\n"
            "listener=socket.socket(socket.AF_INET,socket.SOCK_STREAM)\n"
            "listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)\n"
            f"listener.bind(('127.0.0.1',{port}))\n"
            "listener.listen(1)\n"
            "print('READY',flush=True)\n"
            "connection,_=listener.accept()\n"
            "connection.recv(65536)\n"
            "head=(b'HTTP/1.1 503 Service Unavailable\\r\\n'"
            "+f'Content-Length: {len(body)}\\r\\n'.encode('ascii')"
            "+b'Content-Type: application/json\\r\\nConnection: close\\r\\n\\r\\n')\n"
            "connection.sendall(head+body)\n"
            "connection.close()\n"
            "listener.close()\n"
            "time.sleep(2)\n"
        )
        server = subprocess.Popen(
            [sys.executable, "-c", program],
            cwd=SOURCE,
            env=self.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        def cleanup_server() -> None:
            if server.poll() is None:
                server.kill()
            server.wait(timeout=5)
            if server.stdout is not None:
                server.stdout.close()
            if server.stderr is not None:
                server.stderr.close()

        self.addCleanup(cleanup_server)
        self.assertEqual(server.stdout.readline().strip(), "READY")  # type: ignore[union-attr]
        value = self._receipt(server.pid)
        value["port"] = port
        value["origin"] = f"http://127.0.0.1:{port}"
        _receipt, lock = self._write_receipt(value)
        with lock.open("r+b", buffering=0) as stream:
            stream.seek(64)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            try:
                result = self._run("status.ps1")
            finally:
                stream.seek(64)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        status = self._json(result)
        self.assertEqual(set(status), STATUS_MEMBERS)
        self.assertEqual(status["state"], "RUNNING")
        self.assertEqual(status["last_health_status"], "FAIL")

    def test_missing_receipt_cannot_hide_an_active_service_lease(self) -> None:
        import msvcrt

        database = self._initialize()
        self._cli("demo", "run", "doi-full-ds")
        with closing(sqlite3.connect(database)) as connection:
            before = tuple(
                connection.execute(
                    "SELECT evaluation_id, output_sha256 "
                    "FROM doi_evaluations ORDER BY evaluation_id"
                ).fetchall()
            )
        self.assertTrue(before)
        runtime = self.root / "runtime"
        runtime.mkdir(parents=True, exist_ok=True)
        lock_path = runtime / "service.json.lock"
        with lock_path.open("w+b", buffering=0) as stream:
            stream.write(b"a" * 65)
            stream.seek(64)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            try:
                status = self._run("status.ps1")
                self.assertNotEqual(status.returncode, 0)
                stopped = self._run("stop.ps1")
                self.assertNotEqual(stopped.returncode, 0)
                reset = self._run("reset-demo.ps1", "-ConfirmReset", timeout=30)
                self.assertNotEqual(reset.returncode, 0)
                with closing(sqlite3.connect(database)) as connection:
                    after = tuple(
                        connection.execute(
                            "SELECT evaluation_id, output_sha256 "
                            "FROM doi_evaluations ORDER BY evaluation_id"
                        ).fetchall()
                    )
                self.assertEqual(after, before)
            finally:
                stream.seek(64)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)

    def test_live_unowned_python_process_is_never_stopped(self) -> None:
        unrelated = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            cwd=ROOT,
            env=self.env,
        )

        def cleanup() -> None:
            if unrelated.poll() is None:
                unrelated.kill()
            unrelated.wait(timeout=5)

        self.addCleanup(cleanup)
        self._write_receipt(self._receipt(unrelated.pid))
        result = self._run("stop.ps1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIsNone(unrelated.poll())
        self.assertTrue((self.root / "runtime" / "service.json").is_file())

    def test_equal_csrf_and_shutdown_tokens_fail_before_process_action(self) -> None:
        receipt, _lock = self._write_receipt(
            self._receipt(2_147_483_000, equal_tokens=True)
        )
        result = self._run("stop.ps1")
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(receipt.is_file())

    def test_process_identity_token_collision_fails_before_process_action(self) -> None:
        value = self._receipt(2_147_483_000)
        value["process_identity_token"] = value["csrf_token"]
        receipt, _lock = self._write_receipt(value)
        before = receipt.read_bytes()
        result = self._run("stop.ps1")
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(receipt.is_file())
        started = self._run(
            "start.ps1",
            "-Port",
            str(self._reserve_port()),
            "-NoBrowser",
        )
        self.assertNotEqual(started.returncode, 0)
        self.assertNotIn("START_FAILURE_CLEANUP_FAILED", started.stderr)
        self.assertEqual(receipt.read_bytes(), before)

    def test_path_policy_rejects_relative_device_ads_repository_and_drive_root(self) -> None:
        candidates = (
            Path("relative-data"),
            ROOT,
            Path(r"\\server\share\synthetic"),
            Path(r"\\?\C:\synthetic"),
            Path(r"C:\synthetic:stream"),
            Path(Path.cwd().anchor),
        )
        for candidate in candidates:
            with self.subTest(candidate=str(candidate)):
                result = self._run("status.ps1", data_dir=candidate)
                self.assertNotEqual(result.returncode, 0)

    def test_python_runtime_path_rejects_network_device_ads_and_reparse_paths(self) -> None:
        candidates = (
            r"\\server\share\python.exe",
            r"\\?\C:\synthetic\python.exe",
            r"C:\synthetic\python.exe:stream",
        )
        for candidate in candidates:
            with self.subTest(candidate=candidate):
                result = self._run_with_python_path("status.ps1", candidate)
                self.assertNotEqual(result.returncode, 0)

        target = tempfile.TemporaryDirectory(
            prefix="synthetic-sales-assist-m5-python-target-"
        )
        self.addCleanup(target.cleanup)
        target_path = Path(target.name)
        (target_path / "python.exe").write_bytes(b"not-an-executable")
        link = self.root / "python-runtime"
        self._make_junction(link, target_path)
        result = self._run_with_python_path(
            "status.ps1",
            str(link / "python.exe"),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("PYTHON_PATH_REPARSE_POINT", result.stderr)

    def test_controlled_runtime_and_data_junctions_cannot_redirect_writes(self) -> None:
        runtime_target = tempfile.TemporaryDirectory(
            prefix="synthetic-sales-assist-m5-runtime-target-"
        )
        self.addCleanup(runtime_target.cleanup)
        data_target = tempfile.TemporaryDirectory(
            prefix="synthetic-sales-assist-m5-data-target-"
        )
        self.addCleanup(data_target.cleanup)
        runtime_target_path = Path(runtime_target.name)
        data_target_path = Path(data_target.name)
        runtime_sentinel = runtime_target_path / "runtime.keep"
        data_sentinel = data_target_path / "data.keep"
        runtime_sentinel.write_bytes(b"runtime-unchanged")
        data_sentinel.write_bytes(b"data-unchanged")

        runtime_link = self.root / "runtime"
        self._make_junction(runtime_link, runtime_target_path)
        start = self._run(
            "start.ps1",
            "-Port",
            str(self._reserve_port()),
            "-NoBrowser",
        )
        self.assertNotEqual(start.returncode, 0)
        self.assertEqual(runtime_sentinel.read_bytes(), b"runtime-unchanged")
        self.assertFalse((runtime_target_path / "lifecycle-operation.lock").exists())
        runtime_link.rmdir()

        data_link = self.root / "data"
        data_link.rmdir()
        self._make_junction(data_link, data_target_path)
        reset = self._run("reset-demo.ps1", "-ConfirmReset", timeout=30)
        self.assertNotEqual(reset.returncode, 0)
        self.assertEqual(data_sentinel.read_bytes(), b"data-unchanged")
        self.assertFalse((data_target_path / "synthetic_sales_assist.sqlite3").exists())

    def test_trailing_separator_data_root_is_canonical_for_all_scripts(self) -> None:
        trailing = str(self.root) + os.sep
        port = self._reserve_port()
        started = self._run(
            "start.ps1",
            "-Port",
            str(port),
            "-NoBrowser",
            data_dir=trailing,
            timeout=60,
        )
        self.assertEqual(started.returncode, 0, started.stderr or started.stdout)
        start_report = self._json(started)
        self.assertEqual(start_report["data_dir"], str(self.root))
        status = self._run("status.ps1", data_dir=trailing)
        self.assertEqual(status.returncode, 0, status.stderr or status.stdout)
        self.assertEqual(self._json(status)["data_dir"], str(self.root))
        stopped = self._run("stop.ps1", data_dir=trailing, timeout=30)
        self.assertEqual(stopped.returncode, 0, stopped.stderr or stopped.stdout)
        reset = self._run(
            "reset-demo.ps1",
            "-ConfirmReset",
            data_dir=trailing,
            timeout=60,
        )
        self.assertEqual(reset.returncode, 0, reset.stderr or reset.stdout)
        self.assertEqual(self._json(reset)["data_dir"], str(self.root))

    def test_operation_lock_blocks_start_before_database_initialization(self) -> None:
        import msvcrt

        runtime = self.root / "runtime"
        runtime.mkdir(parents=True)
        lock_path = runtime / "lifecycle-operation.lock"
        with lock_path.open("a+b", buffering=0) as stream:
            stream.write(b"0")
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            try:
                started = self._run(
                    "start.ps1",
                    "-Port",
                    str(self._reserve_port()),
                    "-NoBrowser",
                )
                self.assertNotEqual(started.returncode, 0)
                reset = self._run("reset-demo.ps1", "-ConfirmReset")
                self.assertNotEqual(reset.returncode, 0)
                self.assertFalse(
                    (self.root / "data" / "synthetic_sales_assist.sqlite3").exists()
                )
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)

    def test_concurrent_start_attempt_is_rejected_by_operation_lock(self) -> None:
        port = self._reserve_port()
        with self._lifecycle_operation_barrier("START", port=port) as (
            first,
            nonce,
        ):
            second = self._run(
                "start.ps1",
                "-Port",
                str(port),
                "-NoBrowser",
                timeout=30,
            )
            first_result = self._release_lifecycle_holder(first, nonce)
        self.assertNotEqual(second.returncode, 0)
        self.assertIn("LIFECYCLE_OPERATION_ACTIVE", second.stderr)
        self.assertEqual(
            first_result.returncode,
            0,
            first_result.stderr or first_result.stdout,
        )
        self._assert_operation_lock_available()
        stopped = self._run("stop.ps1", timeout=30)
        self.assertEqual(stopped.returncode, 0, stopped.stderr or stopped.stdout)

    def test_concurrent_start_and_reset_are_serialized(self) -> None:
        port = self._reserve_port()
        with self._lifecycle_operation_barrier("START", port=port) as (
            start,
            nonce,
        ):
            overlapping_reset = self._run(
                "reset-demo.ps1",
                "-ConfirmReset",
                timeout=30,
            )
            start_result = self._release_lifecycle_holder(start, nonce)
        self.assertNotEqual(overlapping_reset.returncode, 0)
        self.assertIn("LIFECYCLE_OPERATION_ACTIVE", overlapping_reset.stderr)
        self.assertEqual(
            start_result.returncode,
            0,
            start_result.stderr or start_result.stdout,
        )
        sequential_reset = self._run(
            "reset-demo.ps1",
            "-ConfirmReset",
            timeout=60,
        )
        self.assertEqual(
            sequential_reset.returncode,
            0,
            sequential_reset.stderr or sequential_reset.stdout,
        )
        self._assert_operation_lock_available()
        verification = self._cli("db", "verify", "--deep")
        self.assertTrue(verification["result"]["healthy"])

    def test_concurrent_reset_and_start_are_serialized(self) -> None:
        self._initialize()
        port = self._reserve_port()
        with self._lifecycle_operation_barrier("RESET") as (reset, nonce):
            overlapping_start = self._run(
                "start.ps1",
                "-Port",
                str(port),
                "-NoBrowser",
                timeout=30,
            )
            reset_result = self._release_lifecycle_holder(reset, nonce)
        self.assertNotEqual(overlapping_start.returncode, 0)
        self.assertIn("LIFECYCLE_OPERATION_ACTIVE", overlapping_start.stderr)
        self.assertEqual(
            reset_result.returncode,
            0,
            reset_result.stderr or reset_result.stdout,
        )
        self._assert_operation_lock_available()
        sequential_start = self._run(
            "start.ps1",
            "-Port",
            str(port),
            "-NoBrowser",
            timeout=60,
        )
        self.assertEqual(
            sequential_start.returncode,
            0,
            sequential_start.stderr or sequential_start.stdout,
        )
        stopped = self._run("stop.ps1", timeout=30)
        self.assertEqual(stopped.returncode, 0, stopped.stderr or stopped.stdout)

    def test_invalid_barrier_release_fails_and_unlocks_operation(self) -> None:
        port = self._reserve_port()
        with self._lifecycle_operation_barrier("START", port=port) as (
            start,
            nonce,
        ):
            wrong_nonce = ("0" if nonce[0] != "0" else "1") + nonce[1:]
            failed = self._release_lifecycle_holder(
                start,
                nonce,
                supplied_nonce=wrong_nonce,
            )
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("SSA_TEST_LIFECYCLE_BARRIER_RELEASE_INVALID", failed.stderr)
        self.assertFalse((self.root / "runtime" / "service.json").exists())
        self._assert_operation_lock_available()
        recovered = self._run(
            "start.ps1",
            "-Port",
            str(port),
            "-NoBrowser",
            timeout=60,
        )
        self.assertEqual(recovered.returncode, 0, recovered.stderr or recovered.stdout)
        stopped = self._run("stop.ps1", timeout=30)
        self.assertEqual(stopped.returncode, 0, stopped.stderr or stopped.stdout)

    def test_owner_process_crash_releases_operation_lock(self) -> None:
        port = self._reserve_port()
        with self._lifecycle_operation_barrier("START", port=port) as (start, _nonce):
            start.kill()
            stdout, stderr = start.communicate(timeout=10)
            crashed = subprocess.CompletedProcess(
                start.args,
                start.returncode,
                stdout,
                stderr,
            )
        self.assertNotEqual(crashed.returncode, 0)
        self.assertFalse((self.root / "runtime" / "service.json").exists())
        self._assert_operation_lock_available()
        reset = self._run("reset-demo.ps1", "-ConfirmReset", timeout=60)
        self.assertEqual(reset.returncode, 0, reset.stderr or reset.stdout)

    def test_inert_lifecycle_lock_file_is_reused_after_owner_exit(self) -> None:
        runtime = self.root / "runtime"
        runtime.mkdir(parents=True)
        lock_path = runtime / "lifecycle-operation.lock"
        lock_path.write_bytes(b"0")
        reset = self._run("reset-demo.ps1", "-ConfirmReset", timeout=60)
        self.assertEqual(reset.returncode, 0, reset.stderr or reset.stdout)
        self.assertTrue(lock_path.is_file())
        self._assert_operation_lock_available()

    def test_distinct_data_directories_do_not_contend(self) -> None:
        other = tempfile.TemporaryDirectory(
            prefix="synthetic-sales-assist-m5-lifecycle-distinct-"
        )
        self.addCleanup(other.cleanup)
        other_root = Path(other.name).resolve()
        with self._lifecycle_operation_barrier("RESET") as (first, nonce):
            second_result = self._run(
                "reset-demo.ps1",
                "-ConfirmReset",
                data_dir=other_root,
                timeout=60,
            )
            first_result = self._release_lifecycle_holder(first, nonce)
        self.assertEqual(
            second_result.returncode,
            0,
            second_result.stderr or second_result.stdout,
        )
        self.assertEqual(
            first_result.returncode,
            0,
            first_result.stderr or first_result.stdout,
        )
        self._assert_operation_lock_available()
        self._assert_operation_lock_available(other_root)

    def test_live_child_failure_is_cleaned_before_operation_unlock(self) -> None:
        port = self._reserve_port()
        with self._start_child_cleanup_barrier(port) as (start, nonce):
            overlapping_reset = self._run(
                "reset-demo.ps1",
                "-ConfirmReset",
                timeout=30,
            )
            failed_start = self._release_start_child_cleanup_holder(start, nonce)
        self.assertNotEqual(overlapping_reset.returncode, 0)
        self.assertIn("LIFECYCLE_OPERATION_ACTIVE", overlapping_reset.stderr)
        self.assertNotEqual(failed_start.returncode, 0)
        self.assertIn("SSA_TEST_BROWSER_START_FAILED", failed_start.stderr)
        self.assertNotIn("START_FAILURE_CLEANUP_FAILED", failed_start.stderr)
        self.assertFalse((self.root / "runtime" / "service.json").exists())
        self.assertFalse((self.root / "runtime" / "service.json.lock").exists())
        self._assert_operation_lock_available()
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(1)
            self.assertNotEqual(probe.connect_ex(("127.0.0.1", port)), 0)
        recovered = self._run(
            "start.ps1",
            "-Port",
            str(port),
            "-NoBrowser",
            timeout=60,
        )
        self.assertEqual(recovered.returncode, 0, recovered.stderr or recovered.stdout)
        stopped = self._run("stop.ps1", timeout=30)
        self.assertEqual(stopped.returncode, 0, stopped.stderr or stopped.stdout)

    def test_direct_entry_cannot_cross_reset_maintenance_lease(self) -> None:
        self._initialize()
        receipt = self.root / "runtime" / "service.json"
        with self._service_maintenance_barrier() as (reset, nonce):
            direct = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "synthetic_sales_assist.portal",
                    "--data-dir",
                    str(self.root),
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(self._reserve_port()),
                    "--runtime-receipt",
                    str(receipt),
                ],
                cwd=SOURCE,
                env=self.env,
                check=False,
                capture_output=True,
                text=True,
                timeout=20,
            )
            reset_result = self._release_service_maintenance_holder(reset, nonce)
        self.assertNotEqual(direct.returncode, 0)
        self.assertFalse(receipt.exists())
        self.assertEqual(
            reset_result.returncode,
            0,
            reset_result.stderr or reset_result.stdout,
        )
        verification = self._cli("db", "verify", "--deep")
        self.assertTrue(verification["result"]["healthy"])

    def test_start_second_start_status_and_owned_stop(self) -> None:
        port = self._reserve_port()
        started = self._run("start.ps1", "-Port", str(port), "-NoBrowser", timeout=60)
        self.assertEqual(started.returncode, 0, started.stderr or started.stdout)
        start_report = self._json(started)
        self.assertEqual(start_report["state"], "RUNNING")
        self.assertEqual(start_report["port"], port)
        self.assertEqual(start_report["database_schema_version"], 4)
        self.assertEqual(start_report["origin"], f"http://127.0.0.1:{port}")
        self.assertTrue(start_report["app_version"])
        self.assertTrue(start_report["build_version"])

        receipt_path = self.root / "runtime" / "service.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(set(receipt), RECEIPT_MEMBERS)
        self.assertEqual(receipt["schema_version"], RECEIPT_SCHEMA)
        self.assertEqual(
            len(
                {
                    receipt["csrf_token"],
                    receipt["shutdown_token"],
                    receipt["process_identity_token"],
                }
            ),
            3,
        )
        lock_path = self.root / "runtime" / "service.json.lock"
        self.assertEqual(lock_path.stat().st_size, 64)
        with lock_path.open("rb", buffering=0) as stream:
            lock_identity = stream.read(64).decode("ascii")
        self.assertEqual(lock_identity, receipt["process_identity_token"])

        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        connection.request("GET", "/health", headers={"Host": f"127.0.0.1:{port}"})
        response = connection.getresponse()
        health = json.loads(response.read())
        connection.close()
        self.assertEqual(response.status, 200)
        self.assertEqual(set(health), {"data", "schema_version"})
        self.assertEqual(health["schema_version"], API_SCHEMA)
        self.assertEqual(health["data"]["status"], "PASS")
        self.assertEqual(health["data"]["app_version"], receipt["app_version"])
        self.assertEqual(health["data"]["build_version"], receipt["build_version"])
        self.assertEqual(health["data"]["database_schema_version"], 4)

        status = self._run("status.ps1")
        self.assertEqual(status.returncode, 0, status.stderr)
        status_report = self._json(status)
        self.assertEqual(set(status_report), STATUS_MEMBERS)
        self.assertEqual(status_report["state"], "RUNNING")
        self.assertEqual(status_report["last_health_status"], "PASS")
        self.assertEqual(status_report["app_version"], receipt["app_version"])
        self.assertEqual(status_report["build_version"], receipt["build_version"])

        second = self._run("start.ps1", "-Port", str(port), "-NoBrowser")
        self.assertNotEqual(second.returncode, 0)
        self.assertIn("SERVICE_ALREADY_RUNNING", second.stderr)
        self.assertNotIn("START_FAILURE_CLEANUP_FAILED", second.stderr)
        self.assertEqual(
            receipt_path.read_bytes(),
            json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        )
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        connection.request("GET", "/health", headers={"Host": f"127.0.0.1:{port}"})
        response = connection.getresponse()
        response.read()
        connection.close()
        self.assertEqual(response.status, 200)

        stopped = self._run("stop.ps1", timeout=30)
        self.assertEqual(stopped.returncode, 0, stopped.stderr or stopped.stdout)
        self.assertEqual(self._json(stopped)["state"], "STOPPED")
        self.assertFalse((self.root / "runtime" / "service.json").exists())

    def test_occupied_port_fails_without_disturbing_listener(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            port = int(listener.getsockname()[1])
            result = self._run(
                "start.ps1",
                "-Port",
                str(port),
                "-NoBrowser",
                "-StartupTimeoutSeconds",
                "5",
                timeout=30,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(listener.getsockname()[1], port)
        self.assertFalse((self.root / "runtime" / "service.json").exists())

    def test_corrupt_and_unsupported_schema_fail_before_service_start(self) -> None:
        database = self.root / "data" / "synthetic_sales_assist.sqlite3"
        database.parent.mkdir(parents=True)
        database.write_bytes(b"not-a-sqlite-database")
        corrupt = self._run("start.ps1", "-Port", str(self._reserve_port()), "-NoBrowser")
        self.assertNotEqual(corrupt.returncode, 0)
        self.assertFalse((self.root / "runtime" / "service.json").exists())

        database.unlink()
        self._initialize()
        connection = sqlite3.connect(database)
        try:
            connection.execute(
                "INSERT INTO _schema_migrations "
                "(version, name, sha256, applied_at_utc) VALUES (?, ?, ?, ?)",
                (5, "0005_forbidden.sql", "0" * 64, "2026-08-21T00:00:00.000000Z"),
            )
            connection.commit()
        finally:
            connection.close()
        unsupported = self._run(
            "start.ps1", "-Port", str(self._reserve_port()), "-NoBrowser"
        )
        self.assertNotEqual(unsupported.returncode, 0)
        self.assertFalse((self.root / "runtime" / "service.json").exists())


if __name__ == "__main__":
    unittest.main()
