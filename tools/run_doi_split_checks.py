"""Explicit synthetic test aggregation with read-only/local-loopback boundaries."""

import sys

sys.dont_write_bytecode = True
import json
import os
import socket
import unittest
from pathlib import Path

WORKTREE = Path(__file__).resolve().parents[1]
sys.path[:0] = [
    str(WORKTREE),
    str(WORKTREE / 'src'),
    str(WORKTREE / 'tests'),
    str(WORKTREE / 'tools'),
]
violations = []
registered_listeners = []


def live_test_port(port):
    for listener in registered_listeners:
        try:
            address = listener.getsockname()
            if (
                listener.fileno() >= 0
                and address[0] == '127.0.0.1'
                and address[1] != 0
                and address[1] == port
            ):
                return True
        except OSError:
            continue
    return False


def guard(event, args):
    blocked = False
    if event == 'open':
        mode = args[1] if len(args) > 1 else None
        flags = args[2] if len(args) > 2 else 0
        blocked = (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (
            isinstance(flags, int)
            and bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
        )
    elif event in {
        'os.remove',
        'os.rename',
        'os.rmdir',
        'os.mkdir',
        'os.chmod',
        'os.utime',
        'os.chown',
        'os.link',
        'os.symlink',
        'os.truncate',
        'shutil.copyfile',
        'shutil.copymode',
        'shutil.copystat',
        'shutil.move',
        'shutil.rmtree',
        'subprocess.Popen',
        'os.system',
        'sqlite3.connect',
        'ctypes.dlopen',
    }:
        blocked = True
    elif event == 'socket.bind':
        address = args[1]
        blocked = not (isinstance(address, tuple) and address[0] == '127.0.0.1' and address[1] == 0)
        if not blocked:
            registered_listeners.append(args[0])
    elif event in {'socket.connect', 'socket.getaddrinfo'}:
        address = args[1] if event == 'socket.connect' else (args[0], args[1])
        blocked = not (
            isinstance(address, tuple) and address[0] == '127.0.0.1' and live_test_port(address[1])
        )
    if blocked:
        violations.append(event)
        raise RuntimeError('DOI_UI_TEST_BOUNDARY_REJECTED:' + event)


# Load stdlib modules needed by bounded HTTP tests before audit installation;
# neither loading them nor installing the audit hook opens a network socket.
import http.client
import threading
import synthetic_sales_assist.portal.server

sys.addaudithook(guard)
modules = (
    'test_csv_staging_independent',
    'test_legacy_doi_boundary',
    'test_doi_csv_review_ui',
    'test_doi_parser_corrections',
    'test_doi_triage',
    'test_doi_split_review',
    'test_review_package_payload',
    'test_doi_ownership_review',
    'test_doi_owner_confirmations',
)
suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(name) for name in modules)
result = unittest.TextTestRunner(verbosity=1).run(suite)
print(
    json.dumps(
        {
            'test_methods': result.testsRun,
            'legacy_fixture_cases': 9,
            'boundary_violations': violations,
            'success': result.wasSuccessful() and not violations,
            'browser_interaction_tested': False,
        },
        sort_keys=True,
    )
)
raise SystemExit(0 if result.wasSuccessful() and not violations else 1)
