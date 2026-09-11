"""Process receipt timestamps must identify Windows creation, never import timing."""

from __future__ import annotations

import os
import shutil
import subprocess
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from synthetic_sales_assist.portal import lifecycle


POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")


@unittest.skipUnless(os.name == "nt" and POWERSHELL, "Windows process creation identity")
class WindowsProcessIdentityTests(unittest.TestCase):
    def test_receipt_creation_matches_os_even_when_module_import_time_is_different(self) -> None:
        environment = os.environ.copy()
        environment["SSA_TEST_PROCESS_ID"] = str(os.getpid())
        # PowerShell's .NET Process.StartTime is independent of Python's ctypes call.
        query = subprocess.run(
            [str(POWERSHELL), "-NoProfile", "-NonInteractive", "-Command",
             "([DateTimeOffset](Get-Process -Id $env:SSA_TEST_PROCESS_ID).StartTime)"
             ".ToUnixTimeMilliseconds()"],
            env=environment, capture_output=True, text=True, timeout=15, check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self.assertEqual(query.returncode, 0, query.stdout + query.stderr)
        expected_milliseconds = int(query.stdout.strip())
        unrelated_import_time = datetime(2000, 1, 1, tzinfo=timezone.utc)
        with patch.object(lifecycle, "_MODULE_STARTED_AT", unrelated_import_time):
            actual = datetime.fromisoformat(lifecycle.process_start_time().replace("Z", "+00:00"))
        self.assertLess(abs(actual.timestamp() * 1000 - expected_milliseconds), 1)

    def test_failed_windows_native_call_never_falls_back_to_import_time(self) -> None:
        native = Mock()
        native.GetCurrentProcess.return_value = -1
        native.GetProcessTimes.return_value = 0
        with patch("ctypes.WinDLL", return_value=native):
            with self.assertRaisesRegex(lifecycle.PortalLifecycleError,
                                        "PROCESS_START_TIME_UNAVAILABLE"):
                lifecycle.process_start_time()

    def test_windows_native_exception_fails_closed(self) -> None:
        with patch("ctypes.WinDLL", side_effect=OSError("synthetic native failure")):
            with self.assertRaisesRegex(lifecycle.PortalLifecycleError,
                                        "PROCESS_START_TIME_UNAVAILABLE"):
                lifecycle.process_start_time()


class NonWindowsProcessIdentityTests(unittest.TestCase):
    def test_non_windows_test_fallback_remains_deterministic(self) -> None:
        started = datetime(2000, 1, 1, tzinfo=timezone.utc)
        with patch.object(lifecycle.os, "name", "posix"), \
                patch.object(lifecycle, "_MODULE_STARTED_AT", started):
            self.assertEqual(lifecycle.process_start_time(), "2000-01-01T00:00:00Z")


if __name__ == "__main__":
    unittest.main()
