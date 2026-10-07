"""Run two selected test modules with a CPython audit guard, not a full sandbox."""

from __future__ import annotations

import io
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest


INTENDED_TEST_FILES = (
    "test_csv_staging_independent.py",
    "test_legacy_doi_boundary.py",
)


def make_audit_guard(blocked_events: list[str]):
    """Reject common audited side effects; native/un-audited calls are out of scope."""

    def reject_side_effects(event: str, args: tuple[object, ...]) -> None:
        forbidden = event in {
            "socket.connect", "socket.bind", "socket.getaddrinfo", "sqlite3.connect",
            "subprocess.Popen", "os.system", "os.exec", "os.spawn",
            "os.remove", "os.rename", "os.rmdir", "os.mkdir", "os.truncate",
            "os.link", "os.symlink", "os.chmod", "os.chown", "os.utime",
            "os.setxattr", "os.removexattr", "shutil.copyfile", "shutil.copymode",
            "shutil.copystat", "shutil.rmtree", "tempfile.mkstemp", "tempfile.mkdtemp",
        }
        if event == "open":
            mode = args[1] if len(args) > 1 else None
            flags = args[2] if len(args) > 2 else 0
            forbidden = (
                isinstance(mode, str) and any(char in mode for char in "wax+")
            ) or (
                isinstance(flags, int)
                and bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            )
        if forbidden:
            blocked_events.append(event)
            raise RuntimeError("STAGING_CHECK_SIDE_EFFECT_BLOCKED")

    return reject_side_effects


def load_test_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("CHECKS_MODULE_LOAD_FAILED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_intended_suite(root: Path) -> unittest.TestSuite:
    suite = unittest.TestSuite()
    for index, filename in enumerate(INTENDED_TEST_FILES):
        module = load_test_module(root / "tests" / filename, f"_doi_selected_tests_{index}")
        suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
    return suite


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    sys.path[:0] = [str(root), str(root / "src")]
    blocked_events: list[str] = []
    sys.addaudithook(make_audit_guard(blocked_events))
    stream = io.StringIO()
    suite = load_intended_suite(root)
    result = unittest.TextTestRunner(stream=stream, verbosity=1).run(suite)
    report = {
        "schema": "doi-csv-staging-checks/v1",
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
        "success": result.wasSuccessful() and not blocked_events,
        "side_effect_attempts": len(blocked_events),
        "blocked_event_names": sorted(set(blocked_events)),
        "fixture_scope": "GENERATED_FICTIONAL_ONLY",
        "real_rows_evaluated": 0,
        "test_module_files": list(INTENDED_TEST_FILES),
        "guard_scope": "COMMON_CPYTHON_AUDIT_EVENTS_NOT_A_COMPLETE_SANDBOX",
    }
    print(json.dumps(report, sort_keys=True))
    if not result.wasSuccessful():
        print(stream.getvalue())
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
