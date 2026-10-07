"""Offline private-policy preflight for the separately packaged DOI v7 launcher.

No policy contents, order identifiers or runtime tokens are emitted or copied.
The existing application's policy parser and path policy remain authoritative.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'tools'))
from doi_csv_staging.review_policy import parse_owner_confirmations
from synthetic_sales_assist.persistence.paths import validate_local_path
from release_support import assert_unlinked, atomic_json


class DailyPolicyError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class PolicySettings:
    confirmation_path: Path
    confirmation_sha256: str
    expected_decision_count: int

    def projection(self) -> dict:
        return {
            'confirmation_path': str(self.confirmation_path),
            'confirmation_sha256': self.confirmation_sha256,
            'expected_decision_count': self.expected_decision_count,
        }


def _json(path: Path, limit: int) -> dict:
    assert_unlinked(path)
    with path.open('rb') as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('LOCAL_CONFIGURATION_TOO_LARGE')

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('DUPLICATE_CONFIGURATION_KEY')
            result[key] = value
        return result

    value = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=pairs)
    if type(value) is not dict:
        raise ValueError('LOCAL_CONFIGURATION_INVALID')
    return value


def _require_daily_location(path: Path) -> None:
    """Apply setup's sync and fixed-disk rules before any filesystem probe."""
    synced_name = re.compile(r'OneDrive(?: - .+)?|Dropbox|Google Drive|iCloudDrive', re.I)
    if any(synced_name.fullmatch(part) for part in path.parts):
        raise ValueError('DAILY_PATH_SYNCHRONIZED')
    for name in ('OneDrive', 'OneDriveCommercial', 'OneDriveConsumer'):
        raw_root = os.environ.get(name, '')
        if not raw_root.strip():
            continue
        sync_root = Path(os.path.normpath(raw_root))
        if not sync_root.is_absolute():
            raise ValueError('DAILY_SYNC_ROOT_INVALID')
        # Compare complete path components; a sibling sharing a prefix is supported.
        candidate = tuple(part.casefold() for part in path.parts)
        root = tuple(part.casefold() for part in sync_root.parts)
        if candidate[:len(root)] == root:
            raise ValueError('DAILY_PATH_SYNCHRONIZED')
    if os.name == 'nt':
        import ctypes

        try:
            drive_type = ctypes.windll.kernel32.GetDriveTypeW
            drive_type.argtypes = [ctypes.c_wchar_p]
            drive_type.restype = ctypes.c_uint
            if not path.drive or drive_type(path.anchor) != 3:  # DRIVE_FIXED only.
                raise ValueError('DAILY_PATH_FIXED_DISK_REQUIRED')
        except (AttributeError, OSError, TypeError) as exc:
            raise ValueError('DAILY_PATH_DRIVE_UNAVAILABLE') from exc


def _validate_daily_path(value: Path | str) -> Path:
    """Recheck both edited config paths and resolved paths on each daily entry."""
    raw = os.fspath(value)
    path = Path(raw)
    if (not path.is_absolute() or re.search(r'(^|[\\/])\.\.?([\\/]|$)', raw)
            or any(ord(char) < 32 or char == '"' for char in raw)):
        raise ValueError('DAILY_PATH_ABSOLUTE_REQUIRED')
    if os.name == 'nt' and (re.match(r'^[A-Za-z]:[\\/]', raw) is None or ':' in raw[2:]):
        raise ValueError('DAILY_PATH_LOCAL_DRIVE_REQUIRED')
    _require_daily_location(path)
    # Check parents before their children, including broken links and cloud placeholders.
    for ancestor in (*reversed(path.parents), path):
        try:
            metadata = ancestor.lstat()
        except FileNotFoundError:
            break
        if stat.S_ISLNK(metadata.st_mode) or getattr(metadata, 'st_file_attributes', 0) & 0x400:
            raise ValueError('DAILY_PATH_REPARSE_POINT')
    resolved = validate_local_path(path, repository_root=ROOT)
    _require_daily_location(resolved)
    return resolved


def read_policy(data_dir: Path) -> PolicySettings:
    try:
        data_dir = _validate_daily_path(data_dir)
        config = _validate_daily_path(data_dir / 'doi-private-launch.json')
        if not config.is_file():
            raise DailyPolicyError('DOI_PRIVATE_CONFIGURATION_REQUIRED')
        value = _json(config, 8192)
        if (
            set(value)
            != {'schema', 'confirmation_path', 'confirmation_sha256', 'expected_decision_count'}
            or value['schema'] != 'ssa-doi-private-launch/v1'
            or type(value['confirmation_path']) is not str
            or any(ord(c) < 32 or c == '"' for c in value['confirmation_path'])
            or type(value['confirmation_sha256']) is not str
            or re.fullmatch('[a-f0-9]{64}', value['confirmation_sha256']) is None
            or type(value['expected_decision_count']) is not int
            or not 1 <= value['expected_decision_count'] <= 10
        ):
            raise DailyPolicyError('DOI_PRIVATE_CONFIGURATION_INVALID')
        policy_path = _validate_daily_path(value['confirmation_path'])
        assert_unlinked(policy_path)
        if not policy_path.is_file():
            raise DailyPolicyError('DOI_PRIVATE_POLICY_MISSING')
        with policy_path.open('rb') as stream:
            raw = stream.read(32769)
        if len(raw) > 32768:
            raise DailyPolicyError('DOI_PRIVATE_POLICY_INVALID')
        if hashlib.sha256(raw).hexdigest() != value['confirmation_sha256']:
            raise DailyPolicyError('DOI_PRIVATE_POLICY_HASH_MISMATCH')
        policy = parse_owner_confirmations(raw.decode('utf-8-sig'))
        if len(policy.decisions) != value['expected_decision_count']:
            raise DailyPolicyError('DOI_PRIVATE_POLICY_COUNT_MISMATCH')
        return PolicySettings(policy_path, value['confirmation_sha256'], len(policy.decisions))
    except DailyPolicyError:
        raise
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        raise DailyPolicyError('DOI_PRIVATE_POLICY_INVALID') from None


def _binding(data_dir: Path, policy: PolicySettings) -> dict:
    receipt = _json(data_dir / 'runtime/service.json', 32768)
    build = _json(ROOT / 'release-build.json', 32768)
    if (
        type(receipt.get('pid')) is not int
        or receipt['pid'] <= 0
        or receipt.get('host') != '127.0.0.1'
        or type(receipt.get('process_start_time')) is not str
        or re.fullmatch(r'\d{4}-\d{2}-\d{2}T[0-9:.]+Z', receipt['process_start_time']) is None
        or build.get('distribution_revision') != 'doi-v7-daily-local-20261006'
        or re.fullmatch('[a-f0-9]{64}', str(build.get('doi_source_payload_sha256'))) is None
    ):
        raise DailyPolicyError('DOI_POLICY_RUNTIME_IDENTITY_INVALID')
    return {
        'schema': 'ssa-doi-policy-runtime-binding/v1',
        'policy_sha256': policy.confirmation_sha256,
        'decision_count': policy.expected_decision_count,
        'pid': receipt['pid'],
        'process_start_time': receipt['process_start_time'],
        'source_payload_sha256': build['doi_source_payload_sha256'],
    }


def record_binding(data_dir: Path, expected_sha256: str, expected_pid: int) -> None:
    policy = read_policy(data_dir)
    if policy.confirmation_sha256 != expected_sha256:
        raise DailyPolicyError('DOI_PRIVATE_POLICY_CHANGED_DURING_START')
    value = _binding(data_dir, policy)
    if value['pid'] != expected_pid:
        raise DailyPolicyError('DOI_POLICY_RUNTIME_IDENTITY_INVALID')
    atomic_json(data_dir / 'runtime/doi-policy-binding.json', value)


def verify_binding(data_dir: Path) -> None:
    policy = read_policy(data_dir)
    try:
        actual = _json(data_dir / 'runtime/doi-policy-binding.json', 4096)
        if actual != _binding(data_dir, policy):
            raise ValueError('BINDING_MISMATCH')
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        raise DailyPolicyError('DOI_POLICY_RUNTIME_BINDING_MISSING_OR_CHANGED') from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('check', 'record', 'verify-running'))
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--expected-sha256')
    parser.add_argument('--expected-pid', type=int)
    args = parser.parse_args(argv)
    try:
        if args.action == 'check':
            print(json.dumps(read_policy(args.data_dir).projection()))
        elif args.action == 'record':
            if args.expected_sha256 is None or args.expected_pid is None:
                raise DailyPolicyError('DOI_POLICY_START_IDENTITY_REQUIRED')
            record_binding(args.data_dir, args.expected_sha256, args.expected_pid)
            print('{"status":"DOI_POLICY_BOUND_TO_OWNED_RUNTIME"}')
        else:
            verify_binding(args.data_dir)
            print('{"status":"DOI_POLICY_RUNTIME_BINDING_VERIFIED"}')
    except DailyPolicyError as exc:
        print(exc.code, file=sys.stderr)
        return 1
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        print('DOI_PRIVATE_POLICY_INVALID', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
