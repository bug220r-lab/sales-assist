from __future__ import annotations

import http.client
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SOURCE = ROOT / "src"
POWERSHELL = shutil.which("pwsh") or shutil.which("powershell")
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


@unittest.skipUnless(os.name == "nt" and POWERSHELL, "Windows PowerShell lifecycle test")
class Milestone5LifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="synthetic-sales-assist-m5-lifecycle-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.env = dict(os.environ)
        self.env.pop("PYTHONPATH", None)

    def tearDown(self) -> None:
        if (self.root / "runtime" / "service.json").exists():
            self._run("stop.ps1", timeout=20)

    def _run(
        self,
        script: str,
        *arguments: str,
        timeout: int = 30,
        data_dir: Path | str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        command = self._script_command(
            script,
            *arguments,
            data_dir=data_dir,
        )
        return subprocess.run(
            command,
            cwd=SOURCE,
            env=self.env,
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
    ) -> list[str]:
        return [
            str(POWERSHELL),
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPTS / script),
            "-PythonPath",
            sys.executable,
            "-DataDir",
            str(self.root if data_dir is None else data_dir),
            *arguments,
        ]

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
        return subprocess.run(
            [
                str(POWERSHELL),
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(SCRIPTS / script),
                "-PythonPath",
                python_path,
                "-DataDir",
                str(self.root),
                *arguments,
            ],
            cwd=SOURCE,
            env=self.env,
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )

    def _wait_for_operation_lock(self, process: subprocess.Popen[str]) -> None:
        import msvcrt

        lock_path = self.root / "runtime" / "lifecycle-operation.lock"
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if process.poll() is not None:
                self.fail("lifecycle process exited before acquiring operation lock")
            if lock_path.is_file():
                try:
                    with lock_path.open("r+b", buffering=0) as stream:
                        stream.seek(0)
                        try:
                            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                        except OSError:
                            return
                        else:
                            stream.seek(0)
                            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            time.sleep(0.01)
        self.fail("lifecycle operation lock was not acquired")

    def _wait_for_service_lock(self, process: subprocess.Popen[str]) -> None:
        import msvcrt

        lock_path = self.root / "runtime" / "service.json.lock"
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if process.poll() is not None:
                self.fail("reset exited before acquiring service maintenance lease")
            if lock_path.is_file() and lock_path.stat().st_size >= 64:
                try:
                    with lock_path.open("r+b", buffering=0) as stream:
                        stream.seek(64)
                        try:
                            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                        except OSError:
                            return
                        else:
                            stream.seek(64)
                            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            time.sleep(0.01)
        self.fail("reset service maintenance lease was not acquired")

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
        result = self._run("stop.ps1")
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(receipt.is_file())

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
        first = subprocess.Popen(
            self._script_command(
                "start.ps1",
                "-Port",
                str(port),
                "-NoBrowser",
            ),
            cwd=SOURCE,
            env=self.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self._wait_for_operation_lock(first)
        second = self._run(
            "start.ps1",
            "-Port",
            str(port),
            "-NoBrowser",
            timeout=30,
        )
        self.assertNotEqual(second.returncode, 0)
        first_stdout, first_stderr = first.communicate(timeout=60)
        self.assertEqual(first.returncode, 0, first_stderr or first_stdout)
        stopped = self._run("stop.ps1", timeout=30)
        self.assertEqual(stopped.returncode, 0, stopped.stderr or stopped.stdout)

    def test_concurrent_start_and_reset_are_serialized(self) -> None:
        port = self._reserve_port()
        start = subprocess.Popen(
            self._script_command(
                "start.ps1",
                "-Port",
                str(port),
                "-NoBrowser",
            ),
            cwd=SOURCE,
            env=self.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self._wait_for_operation_lock(start)
        reset = self._run("reset-demo.ps1", "-ConfirmReset", timeout=30)
        self.assertNotEqual(reset.returncode, 0)
        start_stdout, start_stderr = start.communicate(timeout=60)
        self.assertEqual(start.returncode, 0, start_stderr or start_stdout)
        verification = self._cli("db", "verify", "--deep")
        self.assertTrue(verification["result"]["healthy"])
        stopped = self._run("stop.ps1", timeout=30)
        self.assertEqual(stopped.returncode, 0, stopped.stderr or stopped.stdout)

    def test_direct_entry_cannot_cross_reset_maintenance_lease(self) -> None:
        self._initialize()
        reset = subprocess.Popen(
            self._script_command("reset-demo.ps1", "-ConfirmReset"),
            cwd=SOURCE,
            env=self.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self._wait_for_service_lock(reset)
        receipt = self.root / "runtime" / "service.json"
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
        self.assertNotEqual(direct.returncode, 0)
        self.assertFalse(receipt.exists())
        reset_stdout, reset_stderr = reset.communicate(timeout=60)
        self.assertEqual(reset.returncode, 0, reset_stderr or reset_stdout)
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
