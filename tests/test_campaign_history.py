"""Offline archive integrity, attribution and meaningful corpus-preparation boundaries."""

from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

from synthetic_sales_assist.campaign_replies.history import (
    HistoryError,
    HistoryService,
    validate_export_schema,
)
from synthetic_sales_assist.campaign_replies.history_fixtures import SIGNATURE, demo_history_export
from synthetic_sales_assist.campaign_replies.store import Store

def _single(body: str = 'Perfect, thanks! Send that over when you get a chance.') -> dict[str, Any]:
    package = demo_history_export()
    message = copy.deepcopy(package['files']['sent-emails-00001.json']['messages'][5])
    message['body_text'] = body
    message['body_html'] = ''
    package['files'] = {'sent-emails-00001.json': {
        **package['files']['sent-emails-00001.json'], 'messages': [message],
    }}
    package['report'].update(exported_messages=1, published_messages=1, bounced_attempts=0)
    return package


class CampaignHistoryTests(unittest.TestCase):

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory(prefix='ssa-history-')
        self.addCleanup(self.directory.cleanup)
        self.service = HistoryService(Store(Path(self.directory.name) / 'history.sqlite3'))

    def test_reference_templates_and_ui_assets_work_without_original_handoff(self) -> None:
        source = Path(__file__).resolve().parents[1] / 'src'
        isolated = Path(self.directory.name) / 'standalone-src'
        shutil.copytree(source, isolated, ignore=shutil.ignore_patterns('__pycache__'))
        environment = os.environ.copy()
        environment.update(PYTHONPATH=str(isolated), PYTHONDONTWRITEBYTECODE='1')
        script = '''
import json
import os
from importlib.resources import files
from pathlib import Path
from synthetic_sales_assist.campaign_replies import history

assert Path(history.__file__).is_relative_to(Path(os.environ['PYTHONPATH']))
signatures, references = history._reference_rules()
assert len(references) == 6
assert any(item['name'] == 'JL SIG' for item in references)
assert 'Get The Right Tool For The Job Here!' in signatures
portal = files('synthetic_sales_assist').joinpath('portal')
assert portal.joinpath('campaign_workspace.js').read_bytes()
assert portal.joinpath('campaign_workspace.css').read_bytes()
print(json.dumps({'references': len(references), 'isolated': True}))
'''
        result = subprocess.run(
            [sys.executable, '-c', script], cwd=self.directory.name, env=environment,
            check=False, text=True, capture_output=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {'references': 6, 'isolated': True})

    def test_changed_target_author_rejected_without_reinterpreting_prior_variants(self) -> None:
        package = demo_history_export()
        self.service.import_export(**package)
        summary = self.service.summary()
        candidates = self.service.candidates()
        package['report']['user_id'] = 'SYN-REP-OTHER'
        for chunk in package['files'].values():
            chunk['user_id'] = 'SYN-REP-OTHER'
        with self.assertRaisesRegex(HistoryError, '^HISTORY_WRITER_SCOPE_CONFLICT$'):
            self.service.import_export(**package)
        self.assertEqual(self.service.summary(), summary)
        self.assertEqual(self.service.candidates(), candidates)
        with self.service.store.read() as connection:
            self.assertEqual(
                connection.execute('SELECT COUNT(*) FROM cr_history_files').fetchone()[0], 2,
            )
        # A matching new author's records cannot silently join this writer's corpus either.
        for chunk in package['files'].values():
            for message in chunk['messages']:
                message['author_user_id'] = 'SYN-REP-OTHER'
        with self.assertRaisesRegex(HistoryError, '^HISTORY_WRITER_SCOPE_CONFLICT$'):
            self.service.import_export(**package)
        self.assertEqual(self.service.summary(), summary)

    def test_generated_examples_five_candidates_raw_retention_and_reimport(self) -> None:
        service = self.service
        package = demo_history_export()
        result = service.import_export(**package)
        assert result['counts'] == {
            'included': 5, 'held': 0, 'excluded': 5, 'unique_threads': 10,
            'raw_variants': 10, 'imports': 1,
        }
        assert result['duplicate_records'] == 1
        by_id = {item['thread_id']: item for item in service.candidates()['items']}
        assert 'part number' in by_id['SYN-INTERACTION-HISTORY-002']['candidate_text']
        custom = by_id['SYN-INTERACTION-HISTORY-005']
        assert custom['candidate_text'] == (
            'The photo is a little blurry. Could you send another picture of the connector?'
        )
        assert SIGNATURE not in custom['candidate_text']
        assert SIGNATURE in custom['raw_variants'][0]['body_text']
        assert len(by_id['SYN-INTERACTION-HISTORY-006']['provenance']) == 2
        assert by_id['SYN-INTERACTION-HISTORY-007']['status'] == 'excluded'
        assert 'bounced' in by_id['SYN-INTERACTION-HISTORY-008']['reasons']
        assert 'account_attributed_api_source' in by_id['SYN-INTERACTION-HISTORY-010']['reasons']
        again = service.import_export(**package)
        assert again['idempotent'] is True
        assert again['counts'] == result['counts']
        reopened = HistoryService(service.store)
        assert reopened.candidates() == service.candidates()

    def test_raw_file_bytes_and_attachment_metadata_remain_available(self) -> None:
        service = self.service
        package = demo_history_export()
        original = json.dumps(package['files']['sent-emails-00001.json'], indent=4)
        package['files']['sent-emails-00001.json'] = original
        result = service.import_export(**package)
        with service.store.read() as db:
            assert db.execute(
                'SELECT raw_json FROM cr_history_files WHERE import_id=? AND filename=?',
                (result['import_id'], 'sent-emails-00001.json'),
            ).fetchone()[0] == original
        forward = service.candidates()['items'][6]
        assert forward['raw_variants'][0]['attachments'][0]['filename'] == 'synthetic-label.png'

    def test_conflicting_id_quarantines_both_copies_1(self) -> None:
        service = self.service
        across_imports = False
        package = _single()
        if across_imports:
            service.import_export(**package)
            package['files']['sent-emails-00001.json']['messages'][0]['body_text'] = (
                'A different synthetic message with the same thread identity.'
            )
        else:
            other = copy.deepcopy(package['files']['sent-emails-00001.json']['messages'][0])
            other['body_text'] = (
                'A different synthetic message with the same thread identity.'
            )
            package['files']['sent-emails-00001.json']['messages'].append(other)
        result = service.import_export(**package)
        assert result['counts']['held'] == 1
        item = service.candidates()['items'][0]
        assert item['reasons'] == ['conflicting_thread_id']
        assert len(item['raw_variants']) == 2
        assert item['candidate_text'] == ''

    def test_conflicting_id_quarantines_both_copies_2(self) -> None:
        service = self.service
        across_imports = True
        package = _single()
        if across_imports:
            service.import_export(**package)
            package['files']['sent-emails-00001.json']['messages'][0]['body_text'] = (
                'A different synthetic message with the same thread identity.'
            )
        else:
            other = copy.deepcopy(package['files']['sent-emails-00001.json']['messages'][0])
            other['body_text'] = (
                'A different synthetic message with the same thread identity.'
            )
            package['files']['sent-emails-00001.json']['messages'].append(other)
        result = service.import_export(**package)
        assert result['counts']['held'] == 1
        item = service.candidates()['items'][0]
        assert item['reasons'] == ['conflicting_thread_id']
        assert len(item['raw_variants']) == 2
        assert item['candidate_text'] == ''

    def test_record_author_is_checked_independently_of_report(self) -> None:
        service = self.service
        package = _single()
        package['files']['sent-emails-00001.json']['messages'][0]['author_user_id'] = (
            'SYN-REP-OTHER'
        )
        result = service.import_export(**package)
        assert result['counts']['held'] == 1
        assert service.candidates()['items'][0]['reasons'] == ['wrong_author']

    def test_schema_and_synthetic_gate_are_separate(self) -> None:
        service = self.service
        package = _single()
        package['report'].pop('synthetic_fixture')
        validate_export_schema(package['report'], package['files'])
        with self.assertRaisesRegex(HistoryError, 'requires_generated_synthetic_profile'):
            service.import_export(**package)
        assert service.summary()['counts']['unique_threads'] == 0

    def test_marker_cannot_bypass_synthetic_firewall_1(self) -> None:
        service = self.service
        field = 'author_user_id'
        value = '123456'
        package = _single()
        package['files']['sent-emails-00001.json']['messages'][0][field] = value
        with self.assertRaises(ValueError):
            service.import_export(**package)
        assert service.summary()['counts']['imports'] == 0

    def test_marker_cannot_bypass_synthetic_firewall_2(self) -> None:
        service = self.service
        field = 'conversation_id'
        value = '123456'
        package = _single()
        package['files']['sent-emails-00001.json']['messages'][0][field] = value
        with self.assertRaises(ValueError):
            service.import_export(**package)
        assert service.summary()['counts']['imports'] == 0

    def test_marker_cannot_bypass_synthetic_firewall_3(self) -> None:
        service = self.service
        field = 'body_text'
        value = 'Please contact synthetic' + '@' + 'outside.invalid'
        package = _single()
        package['files']['sent-emails-00001.json']['messages'][0][field] = value
        with self.assertRaises(ValueError):
            service.import_export(**package)
        assert service.summary()['counts']['imports'] == 0

    def test_marker_cannot_bypass_synthetic_firewall_4(self) -> None:
        service = self.service
        field = 'body_html'
        value = '<p><a href="' + 'https' + '://outside.com">Synthetic link</a></p>'
        package = _single()
        package['files']['sent-emails-00001.json']['messages'][0][field] = value
        with self.assertRaises(ValueError):
            service.import_export(**package)
        assert service.summary()['counts']['imports'] == 0

    def test_marker_cannot_bypass_synthetic_firewall_5(self) -> None:
        service = self.service
        field = 'body_text'
        value = '<script>synthetic script</script>'
        package = _single()
        package['files']['sent-emails-00001.json']['messages'][0][field] = value
        with self.assertRaises(ValueError):
            service.import_export(**package)
        assert service.summary()['counts']['imports'] == 0

    def test_failed_import_preserves_prior_archive_1(self) -> None:
        service = self.service
        mutation = 'missing_chunk'
        service.import_export(**demo_history_export())
        before = service.candidates()
        summary = service.summary()
        package = demo_history_export()
        if mutation == 'missing_chunk':
            del package['files']['sent-emails-00001.json']
        elif mutation == 'truncated':
            package['files']['sent-emails-00001.json']['messages'].pop()
        elif mutation == 'malformed':
            package['files']['sent-emails-00001.json'] = '{"messages": ['
        elif mutation == 'invalid_record':
            package['files']['sent-emails-00001.json']['messages'].append(17)
        elif mutation == 'duplicate_key':
            package['files']['sent-emails-00001.json'] = '{"messages": [], "messages": []}'
        elif mutation == 'unsafe_path':
            package['files']['../sent-emails-00001.json'] = package['files'].pop(
                'sent-emails-00001.json'
            )
        else:
            package['files']['sent-emails-00001.json']['messages'][0]['sent_at_utc'] = 'tomorrow'
        with self.assertRaises(HistoryError):
            service.import_export(**package)
        assert service.candidates() == before
        assert service.summary() == summary

    def test_failed_import_preserves_prior_archive_2(self) -> None:
        service = self.service
        mutation = 'truncated'
        service.import_export(**demo_history_export())
        before = service.candidates()
        summary = service.summary()
        package = demo_history_export()
        if mutation == 'missing_chunk':
            del package['files']['sent-emails-00001.json']
        elif mutation == 'truncated':
            package['files']['sent-emails-00001.json']['messages'].pop()
        elif mutation == 'malformed':
            package['files']['sent-emails-00001.json'] = '{"messages": ['
        elif mutation == 'invalid_record':
            package['files']['sent-emails-00001.json']['messages'].append(17)
        elif mutation == 'duplicate_key':
            package['files']['sent-emails-00001.json'] = '{"messages": [], "messages": []}'
        elif mutation == 'unsafe_path':
            package['files']['../sent-emails-00001.json'] = package['files'].pop(
                'sent-emails-00001.json'
            )
        else:
            package['files']['sent-emails-00001.json']['messages'][0]['sent_at_utc'] = 'tomorrow'
        with self.assertRaises(HistoryError):
            service.import_export(**package)
        assert service.candidates() == before
        assert service.summary() == summary

    def test_failed_import_preserves_prior_archive_3(self) -> None:
        service = self.service
        mutation = 'malformed'
        service.import_export(**demo_history_export())
        before = service.candidates()
        summary = service.summary()
        package = demo_history_export()
        if mutation == 'missing_chunk':
            del package['files']['sent-emails-00001.json']
        elif mutation == 'truncated':
            package['files']['sent-emails-00001.json']['messages'].pop()
        elif mutation == 'malformed':
            package['files']['sent-emails-00001.json'] = '{"messages": ['
        elif mutation == 'invalid_record':
            package['files']['sent-emails-00001.json']['messages'].append(17)
        elif mutation == 'duplicate_key':
            package['files']['sent-emails-00001.json'] = '{"messages": [], "messages": []}'
        elif mutation == 'unsafe_path':
            package['files']['../sent-emails-00001.json'] = package['files'].pop(
                'sent-emails-00001.json'
            )
        else:
            package['files']['sent-emails-00001.json']['messages'][0]['sent_at_utc'] = 'tomorrow'
        with self.assertRaises(HistoryError):
            service.import_export(**package)
        assert service.candidates() == before
        assert service.summary() == summary

    def test_failed_import_preserves_prior_archive_4(self) -> None:
        service = self.service
        mutation = 'invalid_record'
        service.import_export(**demo_history_export())
        before = service.candidates()
        summary = service.summary()
        package = demo_history_export()
        if mutation == 'missing_chunk':
            del package['files']['sent-emails-00001.json']
        elif mutation == 'truncated':
            package['files']['sent-emails-00001.json']['messages'].pop()
        elif mutation == 'malformed':
            package['files']['sent-emails-00001.json'] = '{"messages": ['
        elif mutation == 'invalid_record':
            package['files']['sent-emails-00001.json']['messages'].append(17)
        elif mutation == 'duplicate_key':
            package['files']['sent-emails-00001.json'] = '{"messages": [], "messages": []}'
        elif mutation == 'unsafe_path':
            package['files']['../sent-emails-00001.json'] = package['files'].pop(
                'sent-emails-00001.json'
            )
        else:
            package['files']['sent-emails-00001.json']['messages'][0]['sent_at_utc'] = 'tomorrow'
        with self.assertRaises(HistoryError):
            service.import_export(**package)
        assert service.candidates() == before
        assert service.summary() == summary

    def test_failed_import_preserves_prior_archive_5(self) -> None:
        service = self.service
        mutation = 'duplicate_key'
        service.import_export(**demo_history_export())
        before = service.candidates()
        summary = service.summary()
        package = demo_history_export()
        if mutation == 'missing_chunk':
            del package['files']['sent-emails-00001.json']
        elif mutation == 'truncated':
            package['files']['sent-emails-00001.json']['messages'].pop()
        elif mutation == 'malformed':
            package['files']['sent-emails-00001.json'] = '{"messages": ['
        elif mutation == 'invalid_record':
            package['files']['sent-emails-00001.json']['messages'].append(17)
        elif mutation == 'duplicate_key':
            package['files']['sent-emails-00001.json'] = '{"messages": [], "messages": []}'
        elif mutation == 'unsafe_path':
            package['files']['../sent-emails-00001.json'] = package['files'].pop(
                'sent-emails-00001.json'
            )
        else:
            package['files']['sent-emails-00001.json']['messages'][0]['sent_at_utc'] = 'tomorrow'
        with self.assertRaises(HistoryError):
            service.import_export(**package)
        assert service.candidates() == before
        assert service.summary() == summary

    def test_failed_import_preserves_prior_archive_6(self) -> None:
        service = self.service
        mutation = 'unsafe_path'
        service.import_export(**demo_history_export())
        before = service.candidates()
        summary = service.summary()
        package = demo_history_export()
        if mutation == 'missing_chunk':
            del package['files']['sent-emails-00001.json']
        elif mutation == 'truncated':
            package['files']['sent-emails-00001.json']['messages'].pop()
        elif mutation == 'malformed':
            package['files']['sent-emails-00001.json'] = '{"messages": ['
        elif mutation == 'invalid_record':
            package['files']['sent-emails-00001.json']['messages'].append(17)
        elif mutation == 'duplicate_key':
            package['files']['sent-emails-00001.json'] = '{"messages": [], "messages": []}'
        elif mutation == 'unsafe_path':
            package['files']['../sent-emails-00001.json'] = package['files'].pop(
                'sent-emails-00001.json'
            )
        else:
            package['files']['sent-emails-00001.json']['messages'][0]['sent_at_utc'] = 'tomorrow'
        with self.assertRaises(HistoryError):
            service.import_export(**package)
        assert service.candidates() == before
        assert service.summary() == summary

    def test_failed_import_preserves_prior_archive_7(self) -> None:
        service = self.service
        mutation = 'bad_timestamp'
        service.import_export(**demo_history_export())
        before = service.candidates()
        summary = service.summary()
        package = demo_history_export()
        if mutation == 'missing_chunk':
            del package['files']['sent-emails-00001.json']
        elif mutation == 'truncated':
            package['files']['sent-emails-00001.json']['messages'].pop()
        elif mutation == 'malformed':
            package['files']['sent-emails-00001.json'] = '{"messages": ['
        elif mutation == 'invalid_record':
            package['files']['sent-emails-00001.json']['messages'].append(17)
        elif mutation == 'duplicate_key':
            package['files']['sent-emails-00001.json'] = '{"messages": [], "messages": []}'
        elif mutation == 'unsafe_path':
            package['files']['../sent-emails-00001.json'] = package['files'].pop(
                'sent-emails-00001.json'
            )
        else:
            package['files']['sent-emails-00001.json']['messages'][0]['sent_at_utc'] = 'tomorrow'
        with self.assertRaises(HistoryError):
            service.import_export(**package)
        assert service.candidates() == before
        assert service.summary() == summary

    def test_partial_and_older_imports_preserve_coverage_and_never_claim_exhaustive(self) -> None:
        service = self.service
        service.import_export(**demo_history_export())
        package = _single()
        package['report'].update(
            run_completed=False, coverage_status='interrupted',
            error='synthetic interrupted test', complete_all_sent_history=True,
            created_at_utc='2026-09-10T14:00:00Z', history_through_utc='2026-09-10T13:00:00Z',
        )
        package['files']['sent-emails-00001.json']['history_through_utc'] = '2026-09-10T13:00:00Z'
        result = service.import_export(**package)
        assert result['complete_all_sent_history'] is False
        assert result['counts']['unique_threads'] == 10
        older = result['coverage'][1]
        assert older['partial'] is True
        assert older['older_than_latest'] is True
        assert older['report']['complete_all_sent_history'] is True

    def test_quote_and_signature_stripping_preserves_short_prose(self) -> None:
        service = self.service
        package = _single(
            'Yes, that works.\n\n' + SIGNATURE + '\n\nOn yesterday wrote:\nQuoted text'
        )
        service.import_export(**package)
        item = service.candidates()['items'][0]
        assert item['candidate_text'] == 'Yes, that works.'
        assert item['status'] == 'included'
        assert {part['reason'] for part in item['suppressed']} == {'quoted_text', 'signature'}

    def test_greeting_and_closing_alone_do_not_match_template(self) -> None:
        service = self.service
        package = _single('Hello,\n\nYes, that works.\n\nThanks,')
        service.import_export(**package)
        item = service.candidates()['items'][0]
        assert item['candidate_text'] == 'Yes, that works.'
        assert item['status'] == 'included'
        assert 'repeated_template' not in {part['reason'] for part in item['suppressed']}

    def test_near_template_match_is_held_without_erasing_rewrite(self) -> None:
        service = self.service
        package = demo_history_export()
        message = package['files']['sent-emails-00001.json']['messages'][9]
        message['body_text'] = 'Here is the saved cart for your fictional project:'
        message['body_html'] = ''
        service.import_export(**package)
        item = service.candidates()['items'][9]
        assert item['status'] == 'held'
        assert item['candidate_text'] == message['body_text']
        assert 'near_template_match_requires_review' in item['reasons']

    def test_html_quote_only_is_excluded_with_raw_preserved(self) -> None:
        service = self.service
        package = _single('')
        message = package['files']['sent-emails-00001.json']['messages'][0]
        message['body_html'] = '<blockquote>Fabricated quoted customer content.</blockquote>'
        service.import_export(**package)
        item = service.candidates()['items'][0]
        assert item['status'] == 'excluded'
        assert item['candidate_text'] == ''
        assert '<blockquote>' in item['raw_variants'][0]['body_html']

    def test_pagination_bounded(self) -> None:
        service = self.service
        service.import_export(**demo_history_export())
        assert len(service.candidates(offset=2, limit=3)['items']) == 3
        with self.assertRaises(HistoryError):
            service.candidates(limit=201)

    def test_transaction_failure_rolls_back_all_archive_tables(self) -> None:
        service = self.service
        service.import_export(**_single())
        before = service.candidates()
        summary = service.summary()

        def fail(_db: Any) -> None:
            raise RuntimeError('synthetic injected preparation failure')
        service._prepare = fail
        with self.assertRaisesRegex(RuntimeError, 'injected'):
            service.import_export(**demo_history_export())
        assert service.candidates() == before
        assert service.summary() == summary
