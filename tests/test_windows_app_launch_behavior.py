"""One-click dispatcher behavior with owned, disposable synthetic app instances."""

from __future__ import annotations

import errno
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.test_m8_release import COMMIT, STAMP, TREE, candidate_files
from tools.build_demo_release import build_payloads
from tools.release_support import extract_archive


POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")


@unittest.skipUnless(os.name == "nt" and POWERSHELL, "Windows application launch behavior")
class WindowsAppLaunchBehaviorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        artifacts, _ = build_payloads(candidate_files(), COMMIT, TREE, STAMP)
        cls.archive_bytes = next(raw for name, raw in artifacts.items() if "windows-demo" in name)

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="synthetic-app-launch-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        archive = self.root / "application.zip"
        archive.write_bytes(self.archive_bytes)
        self.installation = self.root / "application with spaces"
        extract_archive(archive, self.installation)
        self.data = self.root / "owned synthetic data"
        self.environment = os.environ.copy()
        self.environment["SSA_NONINTERACTIVE"] = "1"
        self.environment["SSA_PYTHON"] = os.path.abspath(sys.executable)
        self.environment["LOCALAPPDATA"] = str(self.root / "isolated settings")
        self.environment["PYTHONPATH"] = str(self.root / "unrelated import path")
        self.environment["PYTHONHOME"] = str(self.root / "unrelated python home")
        self.addCleanup(self.stop_owned_instance)

    def stop_owned_instance(self) -> None:
        if (self.data / "runtime" / "service.json").exists():
            self.command("STOP", f'-DataDir "{self.data}"')

    def command(self, action: str, arguments: str = "", *, success: bool = True
                ) -> subprocess.CompletedProcess[str]:
        launcher = self.installation / (action + ".cmd")
        line = f'"{os.environ["COMSPEC"]}" /d /s /c ""{launcher}" {arguments}"'
        result = subprocess.run(
            line, env=self.environment, cwd=self.root, capture_output=True, text=True,
            timeout=90, check=False, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def receipt(self) -> dict[str, object]:
        return json.loads((self.data / "runtime" / "service.json").read_text(encoding="utf-8"))

    @staticmethod
    def unused_port() -> int:
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            return reservation.getsockname()[1]

    def start_explicit(self) -> dict[str, object]:
        port = self.unused_port()
        self.command("START", f'-NoBrowser -DataDir "{self.data}" -Port {port}')
        return self.receipt()

    def test_repeat_start_reopens_same_process_and_direct_start_still_rejects(self) -> None:
        original = self.start_explicit()
        for arguments in ("-NoBrowser", f'-NoBrowser -Port {original["port"]}'):
            with self.subTest(arguments=arguments):
                reopened = self.command("START", arguments)
                records = [json.loads(line) for line in reopened.stdout.splitlines()
                           if line.startswith("{")]
                result = next(value for value in records if value.get("state") == "REOPENED")
                self.assertEqual(result["pid"], original["pid"])
                self.assertEqual(result["origin"], original["origin"])
                self.assertEqual(self.receipt(), original)
        direct = subprocess.run(
            [str(POWERSHELL), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
             str(self.installation / "scripts" / "start.ps1"), "-DataDir", str(self.data),
             "-Port", str(original["port"]), "-NoBrowser"],
            env=self.environment, cwd=self.root, capture_output=True, text=True,
            timeout=45, check=False, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self.assertNotEqual(direct.returncode, 0)
        self.assertIn("SERVICE_ALREADY_RUNNING", direct.stdout + direct.stderr)
        self.assertEqual(self.receipt(), original)

    def test_running_port_or_release_mismatch_preserves_owned_process(self) -> None:
        original = self.start_explicit()
        other_port = 1024 if original["port"] != 1024 else 1025
        rejected = self.command("START", f"-NoBrowser -Port {other_port}", success=False)
        self.assertIn("DEMO_RUNNING_PORT_MISMATCH", rejected.stdout + rejected.stderr)
        marker = self.data / "demo-release.json"
        original_marker = marker.read_bytes()
        try:
            changed = json.loads(original_marker)
            changed["source_commit"] = "c" * 40
            marker.write_text(json.dumps(changed), encoding="utf-8")
            rejected = self.command("START", "-NoBrowser", success=False)
            self.assertIn("DEMO_RUNNING_RELEASE_MISMATCH", rejected.stdout + rejected.stderr)
            marker.unlink()
            rejected = self.command("START", "-NoBrowser", success=False)
            self.assertIn("DEMO_RUNNING_RELEASE_MARKER_MISSING", rejected.stdout + rejected.stderr)
        finally:
            marker.write_bytes(original_marker)
        self.assertEqual(self.receipt(), original)
        self.assertIn('"state":"RUNNING"', self.command("STATUS").stdout)

    def test_busy_default_port_selects_another_port_without_touching_listener(self) -> None:
        blocker = socket.socket()
        blocker_was_bound = False
        try:
            try:
                blocker.bind(("127.0.0.1", 8765))
                blocker.listen(1)
                blocker_was_bound = True
            except OSError as error:
                # A pre-existing occupant is only detected by bind; it is never
                # connected to, inspected or stopped by this test.
                if error.errno != errno.EADDRINUSE and error.winerror != 10048:
                    raise
            self.command("START", f'-NoBrowser -DataDir "{self.data}"')
            actual = self.receipt()
            self.assertNotEqual(actual["port"], 8765)
            actual_port = actual["port"]
            self.assertEqual(actual["origin"], f"http://127.0.0.1:{actual_port}")
            self.assertIn('"state":"RUNNING"', self.command("STATUS").stdout)
            if blocker_was_bound:
                self.assertEqual(blocker.getsockname(), ("127.0.0.1", 8765))
        finally:
            blocker.close()

    def test_explicit_occupied_port_fails_without_fallback_or_stopping_listener(self) -> None:
        with socket.socket() as blocker:
            blocker.bind(("127.0.0.1", 0))
            blocker.listen(1)
            port = blocker.getsockname()[1]
            self.command("START", f'-NoBrowser -DataDir "{self.data}" -Port {port}',
                         success=False)
            self.assertFalse((self.data / "runtime" / "service.json").exists())
            self.assertEqual(blocker.getsockname(), ("127.0.0.1", port))


if __name__ == "__main__":
    unittest.main()
