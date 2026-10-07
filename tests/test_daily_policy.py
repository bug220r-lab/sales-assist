"""Synthetic external-policy and owned-runtime binding regressions; no service starts."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
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
        (self.installation / 'release-build.json').write_text(json.dumps({
            'distribution_revision': 'doi-v7-daily-local-20261006',
            'doi_source_payload_sha256': 'f' * 64,
        }), encoding='utf-8')
        root_patch = patch.object(policy, 'ROOT', self.installation)
        root_patch.start()
        self.addCleanup(root_patch.stop)
        self.data=self.folder/'SYN data';self.data.mkdir()
        self.file=self.folder/'SYN approved policy.json'
        self.payload={'schema':'doi-owner-confirmations/v1','summary_text_sha256':'a'*64,'lines_text_sha256':'b'*64,'decisions':[{'order_id':'90000077','summary_ordinal':2,'record_sha256':'c'*64,'confirmed_at':'2026-10-06T10:00:00Z','evidence_reference':'SYN-EVIDENCE-APPROVED'}]}
        self.write_policy()
        self.config={'schema':'ssa-doi-private-launch/v1','confirmation_path':str(self.file),'confirmation_sha256':sha(self.file.read_bytes()),'expected_decision_count':1}
        self.save_config()
    def write_policy(self):self.file.write_text(json.dumps(self.payload),encoding='utf-8')
    def save_config(self):
        (self.data/'doi-private-launch.json').write_text(json.dumps(self.config),encoding='utf-8')
    def error(self,code):
        with self.assertRaises(policy.DailyPolicyError) as caught:policy.read_policy(self.data)
        self.assertEqual(caught.exception.code,code)
    def receipt(self,pid=12345):
        runtime=self.data/'runtime';runtime.mkdir(exist_ok=True)
        value={'pid':pid,'host':'127.0.0.1','process_start_time':'2026-10-06T12:00:00.000000Z','csrf_token':'SYN-PRIVATE-TOKEN-NOT-TO-COPY','shutdown_token':'SYN-PRIVATE-SHUTDOWN-NOT-TO-COPY'}
        (runtime/'service.json').write_text(json.dumps(value),encoding='utf-8')
    def bind(self):
        self.receipt();policy.record_binding(self.data,self.config['confirmation_sha256'],12345)
    def test_valid_policy_with_spaces_is_read_without_copying_decisions(self):
        before=self.file.read_bytes();result=policy.read_policy(self.data)
        self.assertEqual(result.confirmation_path,self.file)
        self.assertEqual(result.expected_decision_count,1)
        self.assertEqual(self.file.read_bytes(),before)
        self.assertNotIn('90000077',json.dumps(result.projection()))
    def test_missing_configuration_does_not_create_any_state(self):
        (self.data/'doi-private-launch.json').unlink();self.error('DOI_PRIVATE_CONFIGURATION_REQUIRED')
        self.assertEqual(list(self.data.iterdir()),[])
    def test_missing_policy_fails_closed(self):
        self.file.unlink();self.error('DOI_PRIVATE_POLICY_MISSING')
    def test_changed_policy_hash_fails_even_if_json_remains_valid(self):
        self.file.write_bytes(self.file.read_bytes()+b' ');self.error('DOI_PRIVATE_POLICY_HASH_MISMATCH')
    def test_empty_policy_is_not_a_required_confirmation_set(self):
        self.payload['decisions']=[];self.write_policy();self.config['confirmation_sha256']=sha(self.file.read_bytes());self.save_config()
        self.error('DOI_PRIVATE_POLICY_COUNT_MISMATCH')
    def test_unexpected_confirmation_count_fails(self):
        self.config['expected_decision_count']=2;self.save_config();self.error('DOI_PRIVATE_POLICY_COUNT_MISMATCH')
    def test_configuration_schema_and_field_types_are_closed(self):
        original=dict(self.config)
        for field,value in [('schema','wrong'),('extra','x'),('expected_decision_count',True),('expected_decision_count',0),('expected_decision_count',11),('confirmation_sha256',''),('confirmation_path',None)]:
            with self.subTest(field=field,value=value):
                self.config={**original,field:value};self.save_config();self.error('DOI_PRIVATE_CONFIGURATION_INVALID')
    def test_duplicate_configuration_keys_are_rejected(self):
        (self.data/'doi-private-launch.json').write_text('{"schema":"a","schema":"b"}',encoding='utf-8');self.error('DOI_PRIVATE_POLICY_INVALID')
    def test_malformed_configuration_is_rejected(self):
        (self.data/'doi-private-launch.json').write_text('{',encoding='utf-8');self.error('DOI_PRIVATE_POLICY_INVALID')
    def test_large_configuration_is_rejected(self):
        (self.data/'doi-private-launch.json').write_bytes(b' '*8193);self.error('DOI_PRIVATE_POLICY_INVALID')
    def test_malformed_policy_with_matching_hash_is_rejected(self):
        self.file.write_bytes(b'{');self.config['confirmation_sha256']=sha(self.file.read_bytes());self.save_config();self.error('DOI_PRIVATE_POLICY_INVALID')
    def test_invalid_utf8_policy_with_matching_hash_is_rejected(self):
        self.file.write_bytes(b'\xff');self.config['confirmation_sha256']=sha(self.file.read_bytes());self.save_config();self.error('DOI_PRIVATE_POLICY_INVALID')
    def test_duplicate_policy_keys_with_matching_hash_are_rejected(self):
        self.file.write_bytes(b'{"schema":"x","schema":"x"}');self.config['confirmation_sha256']=sha(self.file.read_bytes());self.save_config();self.error('DOI_PRIVATE_POLICY_INVALID')
    def test_large_policy_is_rejected(self):
        self.file.write_bytes(b' '*32769);self.config['confirmation_sha256']=sha(self.file.read_bytes());self.save_config();self.error('DOI_PRIVATE_POLICY_INVALID')
    def test_nonlocal_or_package_policy_paths_are_rejected(self):
        for value in ['SYN-relative.json',r'\\example.test\share\SYN.json','https' + '://example.test/SYN.json',str(self.installation/'SYN.json')]:
            with self.subTest(value=value):
                self.config['confirmation_path']=value;self.save_config();self.error('DOI_PRIVATE_POLICY_INVALID')
    def test_quoted_or_control_character_paths_are_rejected(self):
        for value in ['C:\\SYN"bad.json','C:\\SYN\nbad.json']:
            self.config['confirmation_path']=value;self.save_config();self.error('DOI_PRIVATE_CONFIGURATION_INVALID')
    def test_runtime_binding_roundtrip_contains_no_policy_or_tokens(self):
        self.bind();policy.verify_binding(self.data)
        value=(self.data/'runtime/doi-policy-binding.json').read_text(encoding='utf-8')
        for token in ['90000077','SYN-PRIVATE-TOKEN','SYN-PRIVATE-SHUTDOWN','confirmation_path','decisions']:self.assertNotIn(token,value)
    def test_missing_runtime_binding_prevents_reopen(self):
        self.receipt()
        with self.assertRaisesRegex(policy.DailyPolicyError,'DOI_POLICY_RUNTIME_BINDING_MISSING_OR_CHANGED'):policy.verify_binding(self.data)
    def test_wrong_runtime_pid_prevents_reopen(self):
        self.bind();self.receipt(54321)
        with self.assertRaisesRegex(policy.DailyPolicyError,'DOI_POLICY_RUNTIME_BINDING_MISSING_OR_CHANGED'):policy.verify_binding(self.data)
    def test_changed_valid_policy_prevents_reopen(self):
        self.bind();self.payload['decisions'][0]['record_sha256']='d'*64;self.write_policy();self.config['confirmation_sha256']=sha(self.file.read_bytes());self.save_config()
        with self.assertRaisesRegex(policy.DailyPolicyError,'DOI_POLICY_RUNTIME_BINDING_MISSING_OR_CHANGED'):policy.verify_binding(self.data)
    def test_policy_change_during_start_prevents_binding_write(self):
        self.receipt()
        with self.assertRaisesRegex(policy.DailyPolicyError,'DOI_PRIVATE_POLICY_CHANGED_DURING_START'):policy.record_binding(self.data,'e'*64,12345)
        self.assertFalse((self.data/'runtime/doi-policy-binding.json').exists())
    def test_wrong_started_pid_prevents_binding_write(self):
        self.receipt()
        with self.assertRaisesRegex(policy.DailyPolicyError,'DOI_POLICY_RUNTIME_IDENTITY_INVALID'):policy.record_binding(self.data,self.config['confirmation_sha256'],54321)
        self.assertFalse((self.data/'runtime/doi-policy-binding.json').exists())
    def test_cli_missing_policy_emits_only_a_bounded_error(self):
        self.file.unlink();out=io.StringIO();err=io.StringIO()
        with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):code=policy.main(['check','--data-dir',str(self.data)])
        self.assertEqual(code,1);self.assertEqual(out.getvalue(),'');self.assertEqual(err.getvalue(),'DOI_PRIVATE_POLICY_MISSING\n')
    def test_cli_valid_check_omits_customer_decisions(self):
        out=io.StringIO()
        with contextlib.redirect_stdout(out):code=policy.main(['check','--data-dir',str(self.data)])
        self.assertEqual(code,0);self.assertNotIn('90000077',out.getvalue());self.assertNotIn('record_sha256',out.getvalue())

    def test_changed_source_payload_prevents_reopen(self):
        self.bind()
        build = self.installation / 'release-build.json'
        value = json.loads(build.read_text(encoding='utf-8'))
        value['doi_source_payload_sha256'] = 'e' * 64
        build.write_text(json.dumps(value), encoding='utf-8')
        with self.assertRaisesRegex(policy.DailyPolicyError, 'DOI_POLICY_RUNTIME_BINDING_MISSING_OR_CHANGED'):
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
        with self.assertRaisesRegex(policy.DailyPolicyError, 'DOI_POLICY_RUNTIME_BINDING_MISSING_OR_CHANGED'):
            policy.verify_binding(self.data)


if __name__ == '__main__':
    unittest.main()
