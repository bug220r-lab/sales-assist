"""Offline PowerShell parsing, real argv construction and synthetic setup behavior.

The setup harness substitutes only the external Python command. It never launches
an application, reads an owner policy, contacts an API or changes execution policy.
PowerShell's Bypass argument is scoped to the test child process.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from synthetic_sales_assist.safety.repository import scan_prohibited_repository_content

ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")

STATIC_CHECK = r'''
$ErrorActionPreference = 'Stop'
$PackageRoot = $env:SSA_TEST_REPOSITORY
. (Join-Path $PackageRoot 'scripts\lifecycle-common.ps1')
$checks = 0
function Check([bool]$condition, [string]$label) {
    if (-not $condition) { throw ('LAUNCHER_STATIC_CHECK_FAILED:' + $label) }
    $script:checks++
}
$asts = @{}
foreach ($file in Get-ChildItem -LiteralPath (Join-Path $PackageRoot 'scripts') -Filter '*.ps1') {
    $tokens = $null; $errors = $null
    $ast = [Management.Automation.Language.Parser]::ParseFile($file.FullName, [ref]$tokens, [ref]$errors)
    Check ($errors.Count -eq 0) ('parse ' + $file.Name)
    $asts[$file.Name] = $ast
}
$start = [IO.File]::ReadAllText((Join-Path $PackageRoot 'scripts\start.ps1'))
$demo = [IO.File]::ReadAllText((Join-Path $PackageRoot 'scripts\demo.ps1'))
Check ($start.IndexOf('$dailyPolicySupport check') -lt $start.IndexOf('Initialize-SsaDirectories')) 'policy before directories'
Check ($start.IndexOf('$dailyPolicySupport check') -lt $start.IndexOf('$child = Start-Process')) 'policy before launch'
Check ($start.Contains('--doi-owner-confirmations ')) 'required policy argument'
Check ($start.Contains('-WindowStyle Hidden')) 'hidden background service'
Check ($start.Contains('--host 127.0.0.1')) 'loopback binding'
Check ($start.IndexOf('$dailyPolicySupport record') -gt $start.IndexOf('PROCESS_OWNERSHIP_MISMATCH')) 'binding after ownership'
Check ($demo.IndexOf('$dailyPolicySupport check') -lt $demo.IndexOf('$statusLines =')) 'preflight before reopen'
Check ($demo.IndexOf('$dailyPolicySupport verify-running') -lt $demo.IndexOf('Start-Process -FilePath')) 'binding before browser'
Check ($demo.Contains('[Net.Sockets.SocketError]::AddressAlreadyInUse')) 'safe occupied-port fallback'
Check ($demo.Contains('if ($portWasBound -and $Port -ne [int]$currentStatus.port)')) 'explicit port mismatch'
Check ($demo.Contains('distribution_revision')) 'distribution identity'
Check ($demo.Contains('/doi-csv-review')) 'daily landing route'
Check ($demo.Contains('[int]$Port = 8905')) 'daily default candidate'
foreach ($name in @('START','STATUS','STOP')) {
    $cmd = [IO.File]::ReadAllText((Join-Path $PackageRoot ($name + '.cmd')))
    Check ($cmd.Contains('"%~dp0scripts\demo.ps1"')) ($name + ' quoted self-relative script')
}
$assignment = $asts['start.ps1'].Find({param($node)
    $node -is [Management.Automation.Language.AssignmentStatementAst] -and
    $node.Left.Extent.Text -ceq '$argumentLine'
}, $true)
Check ($null -ne $assignment) 'argument construction found'
$cases = @()
foreach ($suffix in @('SYN normal','SYN folder with spaces','SYN ampersand & folder','SYN apostrophe''s folder')) {
    $root = Join-Path $env:TEMP $suffix
    $Port = 8905
    $paths = [pscustomobject]@{Receipt = (Join-Path $root 'runtime\service.json')}
    $doiPolicy = [pscustomobject]@{confirmation_path = (Join-Path $root 'SYN approved policy.json')}
    $line = & ([scriptblock]::Create($assignment.Right.Extent.Text))
    $cases += @{command_line = ('python.exe ' + $line); expected = @(
        'python.exe','-B','-s','-E','-m','synthetic_sales_assist.portal','--data-dir',$root,
        '--host','127.0.0.1','--port','8905','--runtime-receipt',$paths.Receipt,
        '--doi-owner-confirmations',$doiPolicy.confirmation_path)}
}
$rejected = $false
try { [void](ConvertTo-SsaQuotedProcessArgument 'SYN"bad') } catch { $rejected = $true }
Check $rejected 'embedded quote rejected'
@{checks = $checks; cases = $cases} | ConvertTo-Json -Depth 8 -Compress
'''

SETUP_HARNESS = r'''
$ErrorActionPreference = 'Stop'
function Join-Path {
    param([string]$Path, [string]$ChildPath)
    if ($ChildPath -ceq 'python\python.exe') { return $env:SSA_TEST_HELPER }
    return Microsoft.PowerShell.Management\Join-Path -Path $Path -ChildPath $ChildPath
}
function Get-FileHash {
    param([string]$LiteralPath, [string]$Algorithm)
    if ($env:SSA_TEST_DENY_PROBES -ceq '1') { throw 'TEST_HASH_MUST_NOT_RUN' }
    $hash = [Security.Cryptography.SHA256]::Create()
    $stream = [IO.File]::OpenRead($LiteralPath)
    try { return @{Hash = [BitConverter]::ToString($hash.ComputeHash($stream)).Replace('-', '')} }
    finally { $stream.Dispose(); $hash.Dispose() }
}
function Test-Path {
    param([string]$LiteralPath, [string]$PathType)
    if ($env:SSA_TEST_DENY_PROBES -ceq '1') { throw 'TEST_FILE_PROBE_MUST_NOT_RUN' }
    if ($PathType) {
        return Microsoft.PowerShell.Management\Test-Path -LiteralPath $LiteralPath -PathType $PathType
    }
    return Microsoft.PowerShell.Management\Test-Path -LiteralPath $LiteralPath
}
try {
    & $env:SSA_TEST_SETUP -PackageRoot $env:SSA_TEST_PACKAGE `
        -ConfirmationPath $env:SSA_TEST_POLICY -ApprovedSha256 $env:SSA_TEST_HASH `
        -ExpectedDecisionCount ([int]$env:SSA_TEST_COUNT)
    exit 0
} catch {
    Write-Output $_.Exception.Message
    exit 1
}
'''

PYTHON_STUB = r'''
$action = $args[3]
[IO.File]::AppendAllText($env:SSA_TEST_CALLS, $action + "`n")
$global:LASTEXITCODE = 0
if ($action -ceq $env:SSA_TEST_FAIL_ACTION) { $global:LASTEXITCODE = 1; return }
if ($action -ceq 'data-root') {
    @{data_dir = $env:SSA_TEST_DATA} | ConvertTo-Json -Compress
} elseif ($action -ceq 'check') {
    '{"status":"SYN_POLICY_CHECK_PASSED"}'
} elseif ($action -cne 'verify') { throw 'UNEXPECTED_STUB_ACTION' }
'''


class DailySetupScannerTests(unittest.TestCase):
    def test_setup_reparse_walk_starts_at_drive_root_and_checks_each_child_in_order(self):
        content = (ROOT / "scripts/setup-daily-private.ps1").read_text(encoding="utf-8")
        anchor = content.index("$candidate = [IO.Path]::GetPathRoot($resolved)")
        loop = content.index("foreach ($part in $parts)", anchor)
        append = content.index("[IO.Path]::Combine($candidate, $part)", loop)
        inspect = content.index("[IO.File]::GetAttributes($candidate)", append)
        reject = content.index("DAILY_SETUP_REPARSE_POINT_PROHIBITED", inspect)
        self.assertLess(anchor, loop)
        self.assertLess(loop, append)
        self.assertLess(append, inspect)
        self.assertLess(inspect, reject)
        self.assertNotIn("GetDirectoryName($candidate)", content)

    def test_only_marked_exact_setup_script_is_allowed(self):
        with tempfile.TemporaryDirectory(prefix="ssa-setup-scanner-") as folder:
            root = Path(folder)
            script = root / "scripts/setup-daily-private.ps1"
            script.parent.mkdir()
            content = (ROOT / "scripts/setup-daily-private.ps1").read_text(encoding="utf-8")
            script.write_text(content, encoding="utf-8")
            self.assertEqual(scan_prohibited_repository_content(root), ())
            script.write_text(content.replace("SYNTHETIC-SALES-ASSIST-AUTHORED-M8", ""),
                              encoding="utf-8")
            self.assertIn("unapproved_lifecycle_script", {
                finding.category for finding in scan_prohibited_repository_content(root)})
            script.unlink()
            (script.parent / "unreviewed-setup.ps1").write_text(content, encoding="utf-8")
            self.assertIn("unapproved_lifecycle_script", {
                finding.category for finding in scan_prohibited_repository_content(root)})


@unittest.skipUnless(os.name == "nt" and POWERSHELL, "Windows PowerShell offline checks")
class DailyLauncherTests(unittest.TestCase):
    def run_powershell(self, source, environment):
        return subprocess.run(
            [str(POWERSHELL), "-NoLogo", "-NoProfile", "-NonInteractive",
             "-ExecutionPolicy", "Bypass", "-Command", source],
            env=environment, capture_output=True, text=True, timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW, check=False,
        )

    def test_launcher_parse_ordering_and_windows_argv(self):
        environment = {**os.environ, "SSA_TEST_REPOSITORY": str(ROOT)}
        result = self.run_powershell(STATIC_CHECK, environment)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertGreaterEqual(report["checks"], 24)
        self.assertEqual(len(report["cases"]), 4)
        parse = ctypes.windll.shell32.CommandLineToArgvW
        parse.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)]
        parse.restype = ctypes.POINTER(ctypes.c_wchar_p)
        free = ctypes.windll.kernel32.LocalFree
        free.argtypes = [ctypes.c_void_p]
        free.restype = ctypes.c_void_p
        for case in report["cases"]:
            count = ctypes.c_int()
            arguments = parse(case["command_line"], ctypes.byref(count))
            self.assertTrue(arguments)
            try:
                self.assertEqual([arguments[i] for i in range(count.value)], case["expected"])
            finally:
                free(arguments)

    def setup_case(self, *, existing=False, receipt=False, hash_mismatch=False,
                   count=1, fail_action="", package_override=None, policy_override=None,
                   deny_probes=False, data_override=None, junction_component=None):
        temporary = tempfile.TemporaryDirectory(prefix="ssa-daily-setup-")
        self.addCleanup(temporary.cleanup)
        folder = Path(temporary.name)
        package = folder / "SYN package"
        package.mkdir()
        data = folder / "SYN data"
        data.mkdir()
        policy = folder / "SYN approved policy.json"
        policy_bytes = b'{"synthetic-fixture":"setup preserves bytes"}'
        policy.write_bytes(policy_bytes)
        config = data / "doi-private-launch.json"
        if existing:
            config.write_text("SYN-existing-do-not-overwrite", encoding="utf-8")
        if receipt:
            (data / "runtime").mkdir()
            (data / "runtime/service.json").write_text("{}", encoding="utf-8")
        helper = folder / "SYN-python-stub.ps1"
        helper.write_text(PYTHON_STUB, encoding="utf-8")
        calls = folder / "SYN-calls.txt"
        if junction_component:
            target = folder / "SYN junction target"
            target.mkdir()
            junction = (data if junction_component == "runtime" else package) / junction_component
            junction_environment = {**os.environ, "SSA_TEST_LINK": str(junction),
                                    "SSA_TEST_TARGET": str(target)}
            created = self.run_powershell(
                "New-Item -ItemType Junction -Path $env:SSA_TEST_LINK "
                "-Target $env:SSA_TEST_TARGET | Out-Null", junction_environment)
            self.assertEqual(created.returncode, 0, created.stdout + created.stderr)
        environment = {
            **os.environ, "SSA_TEST_SETUP": str(ROOT / "scripts/setup-daily-private.ps1"),
            "SSA_TEST_PACKAGE": package_override or str(package),
            "SSA_TEST_POLICY": policy_override or str(policy),
            "SSA_TEST_HASH": "a" * 64 if hash_mismatch else hashlib.sha256(policy_bytes).hexdigest(),
            "SSA_TEST_COUNT": str(count), "SSA_TEST_HELPER": str(helper),
            "SSA_TEST_DATA": data_override or str(data), "SSA_TEST_CALLS": str(calls),
            "SSA_TEST_FAIL_ACTION": fail_action,
            "SSA_TEST_DENY_PROBES": "1" if deny_probes else "0",
        }
        result = self.run_powershell(SETUP_HARNESS, environment)
        self.assertEqual(policy.read_bytes(), policy_bytes)
        commands = calls.read_text(encoding="utf-8").splitlines() if calls.exists() else []
        return result, config, commands, environment

    def test_generic_recipe_creates_only_supplied_path_hash_count(self):
        result, config, commands, environment = self.setup_case()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(commands, ["verify", "data-root", "check"])
        self.assertEqual(json.loads(config.read_text(encoding="utf-8")), {
            "schema": "ssa-doi-private-launch/v1",
            "confirmation_path": environment["SSA_TEST_POLICY"],
            "confirmation_sha256": environment["SSA_TEST_HASH"],
            "expected_decision_count": 1,
        })

    def test_generic_recipe_never_overwrites_existing_configuration(self):
        result, config, commands, _ = self.setup_case(existing=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(config.read_text(encoding="utf-8"), "SYN-existing-do-not-overwrite")
        self.assertEqual(commands, ["verify", "data-root"])

    def test_generic_recipe_refuses_existing_runtime_receipt(self):
        result, config, commands, _ = self.setup_case(receipt=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(config.exists())
        self.assertEqual(commands, ["verify", "data-root"])

    def test_generic_recipe_rejects_changed_approval_hash_before_package_commands(self):
        result, config, commands, _ = self.setup_case(hash_mismatch=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(config.exists())
        self.assertEqual(commands, [])

    def test_generic_recipe_fails_closed_on_package_or_data_root_errors(self):
        for action in ("verify", "data-root"):
            with self.subTest(action=action):
                result, config, _, _ = self.setup_case(fail_action=action)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(config.exists())

    def test_generic_recipe_reports_policy_check_failure_without_launching(self):
        result, config, commands, _ = self.setup_case(fail_action="check")
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(config.exists())
        self.assertIn("START remains blocked", result.stdout)
        self.assertEqual(commands, ["verify", "data-root", "check"])

    def test_generic_recipe_rejects_out_of_range_confirmation_counts(self):
        for count in (0, 11):
            with self.subTest(count=count):
                result, config, commands, _ = self.setup_case(count=count)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(config.exists())
                self.assertEqual(commands, [])

    def test_unsafe_package_and_policy_paths_fail_before_probes_or_commands(self):
        invalid = [
            r"\\example.invalid\share\SYN", r"\\?\C:\SYN", "SYN-relative",
            "https" + "://example.invalid/SYN", r"C:relative", r"C:\SYN\..\escape",
            r"C:\OneDrive\SYN", r"C:\Dropbox\SYN", 'C:\\SYN"quoted',
        ]
        for value in invalid:
            for parameter in ("package_override", "policy_override"):
                with self.subTest(value=value, parameter=parameter):
                    result, config, commands, _ = self.setup_case(
                        **{parameter: value}, deny_probes=True)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("DAILY_SETUP_", result.stdout)
                    self.assertNotIn("TEST_HASH_MUST_NOT_RUN", result.stdout)
                    self.assertNotIn("TEST_FILE_PROBE_MUST_NOT_RUN", result.stdout)
                    self.assertFalse(config.exists())
                    self.assertEqual(commands, [])

    def test_selected_data_root_is_revalidated_before_configuration_write(self):
        for value in (r"\\example.invalid\share\SYN", r"C:\OneDrive\SYN"):
            with self.subTest(value=value):
                result, config, commands, _ = self.setup_case(data_override=value)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("DAILY_SETUP_", result.stdout)
                self.assertFalse(config.exists())
                self.assertEqual(commands, ["verify", "data-root"])

    def test_reparse_package_support_directory_is_rejected_before_probes(self):
        result, config, commands, _ = self.setup_case(
            junction_component="tools", deny_probes=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DAILY_SETUP_REPARSE_POINT_PROHIBITED", result.stdout)
        self.assertNotIn("TEST_FILE_PROBE_MUST_NOT_RUN", result.stdout)
        self.assertFalse(config.exists())
        self.assertEqual(commands, [])

    def test_reparse_runtime_directory_is_rejected_before_receipt_probe(self):
        result, config, commands, _ = self.setup_case(junction_component="runtime")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DAILY_SETUP_REPARSE_POINT_PROHIBITED", result.stdout)
        self.assertFalse(config.exists())
        self.assertEqual(commands, ["verify", "data-root"])


if __name__ == "__main__":
    unittest.main()
