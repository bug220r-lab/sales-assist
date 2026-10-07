"""Synthetic external-policy and owned-runtime binding regressions; no service starts."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tools import daily_policy as policy


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


class PrivatePolicyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='ssa-daily-policy-')
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.installation = self.folder / 'SYN installation'
        self.installation.mkdir()
        (self.installation / 'release-build.json').write_text(
            json.dumps(
                {
                    'distribution_revision': 'doi-v7-daily-local-20261006',
                    'doi_source_payload_sha256': 'f' * 64,
                }
            ),
            encoding='utf-8',
        )
        root_patch = patch.object(policy, 'ROOT', self.installation)
        root_patch.start()
        self.addCleanup(root_patch.stop)
        self.data = self.folder / 'SYN data'
        self.data.mkdir()
        self.file = self.folder / 'SYN approved policy.json'
        self.payload = {
            'schema': 'doi-owner-confirmations/v1',
            'summary_text_sha256': 'a' * 64,
            'lines_text_sha256': 'b' * 64,
            'decisions': [
                {
                    'order_id': '90000077',
                    'summary_ordinal': 2,
                    'record_sha256': 'c' * 64,
                    'confirmed_at': '2026-10-06T10:00:00Z',
                    'evidence_reference': 'SYN-EVIDENCE-APPROVED',
                }
            ],
        }
        self.write_policy()
        self.config = {
            'schema': 'ssa-doi-private-launch/v1',
            'confirmation_path': str(self.file),
            'confirmation_sha256': sha(self.file.read_bytes()),
            'expected_decision_count': 1,
        }
        self.save_config()

    def write_policy(self):
        self.file.write_text(json.dumps(self.payload), encoding='utf-8')

    def save_config(self):
        (self.data / 'doi-private-launch.json').write_text(
            json.dumps(self.config), encoding='utf-8'
        )

    def error(self, code):
        with self.assertRaises(policy.DailyPolicyError) as caught:
            policy.read_policy(self.data)
        self.assertEqual(caught.exception.code, code)

    def receipt(self, pid=12345):
        runtime = self.data / 'runtime'
        runtime.mkdir(exist_ok=True)
        value = {
            'pid': pid,
            'host': '127.0.0.1',
            'process_start_time': '2026-10-06T12:00:00.000000Z',
            'csrf_token': 'SYN-PRIVATE-TOKEN-NOT-TO-COPY',
            'shutdown_token': 'SYN-PRIVATE-SHUTDOWN-NOT-TO-COPY',
        }
        (runtime / 'service.json').write_text(json.dumps(value), encoding='utf-8')

    def bind(self):
        self.receipt()
        policy.record_binding(self.data, self.config['confirmation_sha256'], 12345)

    def test_valid_policy_with_spaces_is_read_without_copying_decisions(self):
        before = self.file.read_bytes()
        result = policy.read_policy(self.data)
        self.assertEqual(result.confirmation_path, self.file)
        self.assertEqual(result.expected_decision_count, 1)
        self.assertEqual(self.file.read_bytes(), before)
        self.assertNotIn('90000077', json.dumps(result.projection()))

    def relocate_policy(self, *parts):
        raw = self.file.read_bytes()
        self.file = self.folder.joinpath(*parts, 'SYN policy.json')
        self.file.parent.mkdir(parents=True, exist_ok=True)
        self.file.write_bytes(raw)
        self.config['confirmation_path'] = str(self.file)
        self.save_config()

    def assert_policy_rejected_before_open(self):
        original_open = Path.open

        def guarded_open(path, *args, **kwargs):
            self.assertNotEqual(path, self.file, 'Unsupported policy must not be opened')
            return original_open(path, *args, **kwargs)

        with patch.object(Path, 'open', guarded_open):
            self.error('DOI_PRIVATE_POLICY_INVALID')

    def test_edited_config_rejects_standard_sync_folders_before_policy_open(self):
        for name in ('OneDrive', 'oNeDrIvE - SYN Org', 'Dropbox', 'Google Drive', 'iCloudDrive'):
            with self.subTest(name=name):
                self.relocate_policy(name)
                self.assert_policy_rejected_before_open()

    def test_edited_config_rejects_each_declared_sync_root_and_descendants(self):
        self.relocate_policy('SYN custom sync', 'nested')
        for name in ('OneDrive', 'OneDriveCommercial', 'OneDriveConsumer'):
            for root in (
                self.file.parent,
                self.file.parent.parent,
                self.file.parent / 'SYN unused' / '..',
            ):
                with self.subTest(name=name, root_depth=len(root.parts)):
                    with patch.dict(os.environ, {name: str(root).upper() + os.sep}):
                        self.assert_policy_rejected_before_open()

    def test_sync_root_changes_revalidate_check_record_and_reopen(self):
        self.bind()
        binding = self.data / 'runtime/doi-policy-binding.json'
        before = binding.read_bytes()
        with patch.dict(os.environ, {'OneDrive': str(self.folder)}):
            for action in (
                lambda: policy.read_policy(self.data),
                lambda: policy.record_binding(self.data, self.config['confirmation_sha256'], 12345),
                lambda: policy.verify_binding(self.data),
            ):
                with self.assertRaisesRegex(policy.DailyPolicyError, 'DOI_PRIVATE_POLICY_INVALID'):
                    action()
        self.assertEqual(binding.read_bytes(), before)

    def test_sync_named_data_directory_is_rejected_before_config_access(self):
        with patch.object(Path, 'open', side_effect=AssertionError('No configuration read')):
            with self.assertRaisesRegex(policy.DailyPolicyError, 'DOI_PRIVATE_POLICY_INVALID'):
                policy.read_policy(self.folder / 'Dropbox' / 'SYN data')

    def test_similarly_named_ordinary_paths_and_sync_root_siblings_remain_supported(self):
        for name in ('OneDriveBackup', 'DropboxArchive', 'Google Drive Notes', 'SYN local space'):
            with self.subTest(name=name):
                self.relocate_policy(name)
                with patch.dict(os.environ, {'OneDrive': str(self.file.parent) + '-sync'}):
                    self.assertEqual(policy.read_policy(self.data).confirmation_path, self.file)
        self.relocate_policy('SYN sync-sibling')
        with patch.dict(os.environ, {'OneDrive': str(self.folder / 'SYN sync')}):
            self.assertEqual(policy.read_policy(self.data).confirmation_path, self.file)

    def test_invalid_declared_sync_root_fails_closed(self):
        with patch.dict(os.environ, {'OneDrive': 'SYN-relative-root'}):
            self.assert_policy_rejected_before_open()

    @unittest.skipUnless(os.name == 'nt', 'Windows drive API')
    def test_edited_config_rejects_every_nonfixed_drive_before_filesystem_probe(self):
        import ctypes

        self.file = Path('Z:/SYN unsupported/SYN policy.json')
        self.config['confirmation_path'] = str(self.file)
        self.save_config()
        original_lstat = Path.lstat

        def guarded_lstat(path, *args, **kwargs):
            self.assertNotEqual(path.drive.upper(), 'Z:', 'Unsupported drive must not be probed')
            return original_lstat(path, *args, **kwargs)

        for drive_type in (0, 1, 2, 4, 5, 6, 99):
            with self.subTest(drive_type=drive_type):
                def get_drive_type(root):
                    return drive_type if root.upper().startswith('Z:') else 3

                with patch.object(ctypes.windll.kernel32, 'GetDriveTypeW',
                                  side_effect=get_drive_type):
                    with patch.object(Path, 'lstat', guarded_lstat):
                        self.assert_policy_rejected_before_open()

    @unittest.skipUnless(os.name == 'nt', 'Windows drive API')
    def test_nonfixed_data_drive_and_drive_api_failure_refuse_config_access(self):
        import ctypes

        for result in (0, 1, 2, 4, 5, 6):
            with self.subTest(result=result):
                with patch.object(ctypes.windll.kernel32, 'GetDriveTypeW', return_value=result):
                    with patch.object(Path, 'open', side_effect=AssertionError('No config read')):
                        self.error('DOI_PRIVATE_POLICY_INVALID')
        for error in (OSError('SYN failure'), AttributeError('SYN unavailable')):
            with patch.object(ctypes.windll.kernel32, 'GetDriveTypeW', side_effect=error):
                self.error('DOI_PRIVATE_POLICY_INVALID')

    def test_edited_config_rejects_reparse_ancestor_before_inspecting_children(self):
        ancestor = self.folder / 'SYN reparse'
        self.file = ancestor / 'SYN child' / 'SYN policy.json'
        self.config['confirmation_path'] = str(self.file)
        self.save_config()
        original_lstat = Path.lstat

        def guarded_lstat(path, *args, **kwargs):
            if path == ancestor:
                return SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
            self.assertFalse(path.is_relative_to(ancestor), 'Never traverse a reparse ancestor')
            return original_lstat(path, *args, **kwargs)

        with patch.object(Path, 'lstat', guarded_lstat):
            self.assert_policy_rejected_before_open()

    def test_reparse_config_and_policy_leaves_are_rejected(self):
        original_lstat = Path.lstat
        for target in (self.data / 'doi-private-launch.json', self.file):
            with self.subTest(kind=target.name):
                def guarded_lstat(path, *args, **kwargs):
                    if path == target:
                        return SimpleNamespace(st_mode=stat.S_IFREG, st_file_attributes=0x400)
                    return original_lstat(path, *args, **kwargs)

                with patch.object(Path, 'lstat', guarded_lstat):
                    self.assert_policy_rejected_before_open()

    def test_resolved_policy_location_is_rechecked(self):
        original = policy.validate_local_path

        def resolved_path(path, **kwargs):
            if path == self.file:
                return self.folder / 'OneDrive' / self.file.name
            return original(path, **kwargs)

        with patch.object(policy, 'validate_local_path', side_effect=resolved_path):
            self.assert_policy_rejected_before_open()

    def test_edited_path_error_is_bounded_without_emitting_location(self):
        self.relocate_policy('Dropbox')
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = policy.main(['check', '--data-dir', str(self.data)])
        self.assertEqual(code, 1)
        self.assertEqual(out.getvalue(), '')
        self.assertEqual(err.getvalue(), 'DOI_PRIVATE_POLICY_INVALID\n')

    def test_missing_configuration_does_not_create_any_state(self):
        (self.data / 'doi-private-launch.json').unlink()
        self.error('DOI_PRIVATE_CONFIGURATION_REQUIRED')
        self.assertEqual(list(self.data.iterdir()), [])

    def test_missing_policy_fails_closed(self):
        self.file.unlink()
        self.error('DOI_PRIVATE_POLICY_MISSING')

    def test_changed_policy_hash_fails_even_if_json_remains_valid(self):
        self.file.write_bytes(self.file.read_bytes() + b' ')
        self.error('DOI_PRIVATE_POLICY_HASH_MISMATCH')

    def test_empty_policy_is_not_a_required_confirmation_set(self):
        self.payload['decisions'] = []
        self.write_policy()
        self.config['confirmation_sha256'] = sha(self.file.read_bytes())
        self.save_config()
        self.error('DOI_PRIVATE_POLICY_COUNT_MISMATCH')

    def test_unexpected_confirmation_count_fails(self):
        self.config['expected_decision_count'] = 2
        self.save_config()
        self.error('DOI_PRIVATE_POLICY_COUNT_MISMATCH')

    def test_configuration_schema_and_field_types_are_closed(self):
        original = dict(self.config)
        for field, value in [
            ('schema', 'wrong'),
            ('extra', 'x'),
            ('expected_decision_count', True),
            ('expected_decision_count', 0),
            ('expected_decision_count', 11),
            ('confirmation_sha256', ''),
            ('confirmation_path', None),
        ]:
            with self.subTest(field=field, value=value):
                self.config = {**original, field: value}
                self.save_config()
                self.error('DOI_PRIVATE_CONFIGURATION_INVALID')

    def test_duplicate_configuration_keys_are_rejected(self):
        (self.data / 'doi-private-launch.json').write_text(
            '{"schema":"a","schema":"b"}', encoding='utf-8'
        )
        self.error('DOI_PRIVATE_POLICY_INVALID')

    def test_malformed_configuration_is_rejected(self):
        (self.data / 'doi-private-launch.json').write_text('{', encoding='utf-8')
        self.error('DOI_PRIVATE_POLICY_INVALID')

    def test_large_configuration_is_rejected(self):
        (self.data / 'doi-private-launch.json').write_bytes(b' ' * 8193)
        self.error('DOI_PRIVATE_POLICY_INVALID')

    def test_malformed_policy_with_matching_hash_is_rejected(self):
        self.file.write_bytes(b'{')
        self.config['confirmation_sha256'] = sha(self.file.read_bytes())
        self.save_config()
        self.error('DOI_PRIVATE_POLICY_INVALID')

    def test_invalid_utf8_policy_with_matching_hash_is_rejected(self):
        self.file.write_bytes(b'\xff')
        self.config['confirmation_sha256'] = sha(self.file.read_bytes())
        self.save_config()
        self.error('DOI_PRIVATE_POLICY_INVALID')

    def test_duplicate_policy_keys_with_matching_hash_are_rejected(self):
        self.file.write_bytes(b'{"schema":"x","schema":"x"}')
        self.config['confirmation_sha256'] = sha(self.file.read_bytes())
        self.save_config()
        self.error('DOI_PRIVATE_POLICY_INVALID')

    def test_large_policy_is_rejected(self):
        self.file.write_bytes(b' ' * 32769)
        self.config['confirmation_sha256'] = sha(self.file.read_bytes())
        self.save_config()
        self.error('DOI_PRIVATE_POLICY_INVALID')

    def test_nonlocal_or_package_policy_paths_are_rejected(self):
        for value in [
            'SYN-relative.json',
            r'\\example.test\share\SYN.json',
            'https' + '://example.test/SYN.json',
            str(self.installation / 'SYN.json'),
        ]:
            with self.subTest(value=value):
                self.config['confirmation_path'] = value
                self.save_config()
                self.error('DOI_PRIVATE_POLICY_INVALID')

    def test_quoted_or_control_character_paths_are_rejected(self):
        for value in ['C:\\SYN"bad.json', 'C:\\SYN\nbad.json']:
            self.config['confirmation_path'] = value
            self.save_config()
            self.error('DOI_PRIVATE_CONFIGURATION_INVALID')

    def test_runtime_binding_roundtrip_contains_no_policy_or_tokens(self):
        self.bind()
        policy.verify_binding(self.data)
        value = (self.data / 'runtime/doi-policy-binding.json').read_text(encoding='utf-8')
        for token in [
            '90000077',
            'SYN-PRIVATE-TOKEN',
            'SYN-PRIVATE-SHUTDOWN',
            'confirmation_path',
            'decisions',
        ]:
            self.assertNotIn(token, value)

    def test_missing_runtime_binding_prevents_reopen(self):
        self.receipt()
        with self.assertRaisesRegex(
            policy.DailyPolicyError, 'DOI_POLICY_RUNTIME_BINDING_MISSING_OR_CHANGED'
        ):
            policy.verify_binding(self.data)

    def test_wrong_runtime_pid_prevents_reopen(self):
        self.bind()
        self.receipt(54321)
        with self.assertRaisesRegex(
            policy.DailyPolicyError, 'DOI_POLICY_RUNTIME_BINDING_MISSING_OR_CHANGED'
        ):
            policy.verify_binding(self.data)

    def test_changed_valid_policy_prevents_reopen(self):
        self.bind()
        self.payload['decisions'][0]['record_sha256'] = 'd' * 64
        self.write_policy()
        self.config['confirmation_sha256'] = sha(self.file.read_bytes())
        self.save_config()
        with self.assertRaisesRegex(
            policy.DailyPolicyError, 'DOI_POLICY_RUNTIME_BINDING_MISSING_OR_CHANGED'
        ):
            policy.verify_binding(self.data)

    def test_policy_change_during_start_prevents_binding_write(self):
        self.receipt()
        with self.assertRaisesRegex(
            policy.DailyPolicyError, 'DOI_PRIVATE_POLICY_CHANGED_DURING_START'
        ):
            policy.record_binding(self.data, 'e' * 64, 12345)
        self.assertFalse((self.data / 'runtime/doi-policy-binding.json').exists())

    def test_wrong_started_pid_prevents_binding_write(self):
        self.receipt()
        with self.assertRaisesRegex(policy.DailyPolicyError, 'DOI_POLICY_RUNTIME_IDENTITY_INVALID'):
            policy.record_binding(self.data, self.config['confirmation_sha256'], 54321)
        self.assertFalse((self.data / 'runtime/doi-policy-binding.json').exists())

    def test_cli_missing_policy_emits_only_a_bounded_error(self):
        self.file.unlink()
        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = policy.main(['check', '--data-dir', str(self.data)])
        self.assertEqual(code, 1)
        self.assertEqual(out.getvalue(), '')
        self.assertEqual(err.getvalue(), 'DOI_PRIVATE_POLICY_MISSING\n')

    def test_cli_valid_check_omits_customer_decisions(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = policy.main(['check', '--data-dir', str(self.data)])
        self.assertEqual(code, 0)
        self.assertNotIn('90000077', out.getvalue())
        self.assertNotIn('record_sha256', out.getvalue())

    def test_changed_source_payload_prevents_reopen(self):
        self.bind()
        build = self.installation / 'release-build.json'
        value = json.loads(build.read_text(encoding='utf-8'))
        value['doi_source_payload_sha256'] = 'e' * 64
        build.write_text(json.dumps(value), encoding='utf-8')
        with self.assertRaisesRegex(
            policy.DailyPolicyError, 'DOI_POLICY_RUNTIME_BINDING_MISSING_OR_CHANGED'
        ):
            policy.verify_binding(self.data)

    def test_invalid_distribution_identity_prevents_binding(self):
        self.receipt()
        build = self.installation / 'release-build.json'
        value = json.loads(build.read_text(encoding='utf-8'))
        value['distribution_revision'] = 'SYN-unreviewed-distribution'
        build.write_text(json.dumps(value), encoding='utf-8')
        with self.assertRaisesRegex(policy.DailyPolicyError, 'DOI_POLICY_RUNTIME_IDENTITY_INVALID'):
            policy.record_binding(self.data, self.config['confirmation_sha256'], 12345)

    def test_changed_process_start_time_prevents_reopen(self):
        self.bind()
        receipt = self.data / 'runtime/service.json'
        value = json.loads(receipt.read_text(encoding='utf-8'))
        value['process_start_time'] = '2026-10-06T12:01:00.000000Z'
        receipt.write_text(json.dumps(value), encoding='utf-8')
        with self.assertRaisesRegex(
            policy.DailyPolicyError, 'DOI_POLICY_RUNTIME_BINDING_MISSING_OR_CHANGED'
        ):
            policy.verify_binding(self.data)


if __name__ == '__main__':
    unittest.main()
