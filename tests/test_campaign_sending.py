"""Synthetic campaign protocol tests; these never execute the reference sender."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import tempfile
import unittest
from synthetic_sales_assist.campaign_replies.campaign_fixtures import demo_manifest
from synthetic_sales_assist.campaign_replies.campaigns import (
    CampaignError, CampaignService, SimulationTransport, encoded, sha
)
from synthetic_sales_assist.campaign_replies.store import Store

def prepare(service: CampaignService, count: int=1) -> tuple[str, str]:
    manifest = demo_manifest(count)
    service.prepare_audience(manifest)
    return (manifest['campaign_id'], manifest['records'][0]['queue_key'])

def accepted(service: CampaignService) -> tuple[str, str]:
    cid, key = prepare(service)
    service.launch(cid)
    service.step(cid)
    return (cid, key)

def edit_file(bundle: dict, path: str, callback) -> None:
    value = json.loads(bundle['files'][path])
    callback(value)
    bundle['files'][path] = encoded(value)
    bundle['hashes'][path] = sha(bundle['files'][path])

def remove_file(bundle: dict, path: str, *, coherent_fixture: bool = False) -> None:
    bundle['files'].pop(path)
    bundle['hashes'].pop(path)
    if coherent_fixture:
        _, key, name = path.split('/')
        kind = name.removesuffix('.json')
        audit = json.loads(bundle['files']['audit.json'])
        audit['events'] = [event for event in audit['events']
                           if (event['queue_key'], event['kind']) != (key, kind)]
        bundle['files']['audit.json'] = encoded(audit)
        bundle['hashes']['audit.json'] = sha(bundle['files']['audit.json'])

class CampaignSendingTests(unittest.TestCase):

    def test_transfer_cannot_change_ledger_while_local_writer_has_admission(self):
        service = self.fresh_service()
        cid, _ = prepare(service)
        bundle = service.export_send_state(cid)

        def during_history():
            with self.assertRaisesRegex(CampaignError, 'PAUSE_LOCAL_WRITER'):
                service.import_send_state(bundle)

        service.transport.on_history = during_history
        service.launch(cid)
        self.assertEqual(service.step(cid)['counts']['accepted'], 1)
        self.assertEqual(len(service.transport.posts), 1)

    def test_fresh_transfer_rejects_audit_backed_missing_attempt_files(self):
        service = self.fresh_service()
        cid, key = accepted(service)
        for kind in ('intent', 'receipt', 'observation', 'all'):
            with self.subTest(kind=kind):
                bundle = service.export_send_state(cid)
                paths = [path for path in bundle['files'] if path.startswith('records/')]
                if kind != 'all':
                    paths = [f'records/{key}/{kind}.json']
                for path in paths:
                    remove_file(bundle, path)
                target = self.fresh_service()
                with self.assertRaisesRegex(CampaignError, 'AUDIT_REQUIRES_MISSING'):
                    target.import_send_state(bundle)
                self.assertEqual(target.list_campaigns(), [])
                self.assertEqual(target.transport.posts, [])

    def test_fresh_transfer_rejects_missing_history_hold(self):
        service = self.fresh_service()
        cid, key = prepare(service)
        email = service.detail(cid)['records'][0]['email']
        service.transport.histories[email] = 'found'
        service.launch(cid)
        service.step(cid)
        bundle = service.export_send_state(cid)
        remove_file(bundle, f'records/{key}/hold.json')
        target = self.fresh_service()
        with self.assertRaisesRegex(CampaignError, 'AUDIT_REQUIRES_HISTORY_HOLD'):
            target.import_send_state(bundle)
        self.assertEqual(target.list_campaigns(), [])

    def test_latest_failed_verification_stays_review_required_after_transfer(self):
        service = self.fresh_service()
        cid, key = accepted(service)
        record = service.detail(cid)['records'][0]
        observation = service.transport.observe(record, record['receipt'])
        observation['to'] = None
        with self.assertRaises(CampaignError):
            service.reconcile(cid, key, observation)
        target = self.fresh_service()
        result = target.import_send_state(service.export_send_state(cid))
        self.assertEqual(result['counts']['unverified_review'], 1)
        self.assertEqual(result['records'][0]['outcome'], 'REVIEW_REQUIRED')
        target.launch(cid)
        target.step(cid)
        self.assertEqual(target.transport.posts, [])

    def test_unexplained_intent_blocks_other_campaigns_in_same_store(self):
        service = self.fresh_service()
        cid, _ = prepare(service)
        service.transport.result_mode = 'lost_response'
        service.launch(cid)
        with self.assertRaises(TimeoutError):
            service.step(cid)
        source = demo_manifest(1)
        source['campaign_id'] = 'SYN-RUN-SECOND-CAMPAIGN'
        service.prepare_audience(source)
        with self.assertRaisesRegex(CampaignError, 'UNEXPLAINED_INTENT'):
            service.launch(source['campaign_id'])
        self.assertEqual(len(service.transport.posts), 1)

    def test_campaign_to_reply_to_reviewed_draft_survives_restart(self):
        from synthetic_sales_assist.campaign_replies.replies import RepliesService
        from synthetic_sales_assist.campaign_replies.reply_fixtures import (
            snapshot_from_campaign_records,
        )

        service = self.fresh_service()
        cid, key = accepted(service)
        record = service.detail(cid)['records'][0]
        replies = RepliesService(service.store)
        replies.import_snapshot(snapshot_from_campaign_records([record]))
        detail = replies.detail(record['conversation_id'])
        self.assertEqual(detail['queue_key'], key)
        self.assertEqual(detail['anchor_thread_id'], record['anchor_thread_id'])
        self.assertTrue(detail['needs_reply'])
        text = 'Hello, I can help with the synthetic checkout question.'
        replies.save_draft(record['conversation_id'], text, 0,
                           detail['source_fingerprint'], detail['style_profile']['version'],
                           reviewed=True)
        restarted = RepliesService(Store(service.store.path))
        saved = restarted.detail(record['conversation_id'])['local_draft']
        self.assertEqual(saved['text'], text)
        self.assertTrue(saved['reviewed'])
        self.assertEqual(len(service.transport.posts), 1)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.tmp_path = Path(self.temp.name)
        self.counter = 0

    def fresh_service(self):
        self.counter += 1
        return CampaignService(Store(self.tmp_path / (str(self.counter) + '.sqlite')))

    def test_prepare_immutable_sort_original_rank_exclusions_and_exact_preview(self):
        service = self.fresh_service()
        manifest = demo_manifest(5)
        manifest['records'][0]['cart_total_cents'] = 10000
        manifest['records'][0]['email'] = '  SYNTHETIC-CUSTOMER-1@EXAMPLE.TEST  '
        manifest['records'][1]['address_review'] = True
        manifest['records'][2]['excluded'] = True
        manifest['records'][3]['eligibility'] = 'unknown'
        detail = service.prepare_audience(manifest)
        assert [r['original_rank'] for r in detail['records']] == [2, 3, 4, 1, 5]
        assert detail['counts']['held'] == 3
        record = detail['records'][3]
        assert record['email'] == 'synthetic-customer-1@example.test'
        assert record['cart_url'] == manifest['records'][0]['cart_url']
        preview = service.preview(detail['campaign_id'], record['queue_key'])
        assert preview['payload']['threads'][0]['draft'] is False
        assert preview['payload']['threads'][0]['text'] == record['body_html']
        assert '<br><br>' in record['body_html']
        assert preview['payload_sha256'] == sha(encoded(preview['payload']))
        assert service.prepare_audience(manifest) == detail
        manifest['template'] += ' changed'
        with self.assertRaisesRegex(CampaignError, 'IMMUTABLE_CAMPAIGN_CHANGED'):
            service.prepare_audience(manifest)

    def test_invalid_audience_is_atomic(self):
        cases = [
            ('email', 'customer@' + 'example.com'), ('customer_id', '12345'),
            ('cart_url', 'https' + '://example.test/cart?product=SYN-SKU-1'),
            ('cart_total_cents', -1), ('eligibility', 'assumed'), ('original_rank', True),
        ]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                service = self.fresh_service()
                source = demo_manifest()
                source['records'][-1][field] = value
                with self.assertRaises(ValueError):
                    service.prepare_audience(source)
                assert service.list_campaigns() == []

    def test_duplicate_keys_recipients_and_ranks_rejected(self):
        for field in ['queue_key', 'email', 'original_rank']:
            with self.subTest(field=field):
                service = self.fresh_service()
                source = demo_manifest(2)
                source['records'][1][field] = source['records'][0][field]
                with self.assertRaises(CampaignError):
                    service.prepare_audience(source)
                assert not service.list_campaigns()

    def test_fresh_send_persists_intent_before_one_post_and_rerun_skips(self):
        service = self.fresh_service()
        cid, key = prepare(service)

        def check_intent():
            row = service.detail(cid)['records'][0]
            assert row['intent'] and (not row['receipt'])
            assert row['intent']['payload_sha256'] == service.preview(cid, key)['payload_sha256']
        service.transport.on_create = check_intent
        service.launch(cid)
        detail = service.step(cid)
        assert detail['counts']['accepted'] == 1
        record = detail['records'][0]
        assert record['conversation_id'].startswith('SYN-CONVERSATION-')
        assert record['anchor_thread_id'].startswith('SYN-INTERACTION-')
        assert record['observation']['delivery'] == 'unverified'
        service.step(cid)
        assert service.resume(cid)['status'] == 'RUNNING'
        service.step(cid)
        assert len(service.transport.posts) == 1

    def test_uncertain_creation_never_retries_or_admits_next_recipient(self):
        for mode in ['lost_response', '429', '500', 'missing_resource', 'other_400']:
            with self.subTest(mode=mode):
                service = self.fresh_service()
                cid, _ = prepare(service, 2)
                service.transport.result_mode = mode
                service.launch(cid)
                with self.assertRaises((ValueError, TimeoutError)):
                    service.step(cid)
                detail = service.detail(cid)
                assert detail['status'] == 'BLOCKED'
                assert detail['counts'] == {'accepted': 0, 'unverified_review': 0,
                    'unknown': 1, 'held': 0, 'untouched': 1}
                restarted = CampaignService(service.store)
                with self.assertRaisesRegex(CampaignError, 'UNEXPLAINED_INTENT'):
                    restarted.resume(cid)
                assert len(service.transport.posts) == 1 and restarted.transport.posts == []

    def test_receipt_save_failure_retains_unknown_and_never_retries(self):
        service = self.fresh_service()
        cid, _ = prepare(service)

        def fail(*args):
            raise OSError('SIMULATED_RECEIPT_DISK_FAILURE')
        service._save_receipt = fail
        service.launch(cid)
        with self.assertRaises(OSError):
            service.step(cid)
        assert service.detail(cid)['counts']['unknown'] == 1
        with self.assertRaises(CampaignError):
            service.resume(cid)
        assert len(service.transport.posts) == 1

    def test_history_hold_and_incomplete_lookup_make_zero_posts(self):
        service = self.fresh_service()
        cid, _ = prepare(service, 2)
        records = service.detail(cid)['records']
        service.transport.histories[records[0]['email']] = 'found'
        service.transport.histories[records[1]['email']] = 'incomplete'
        service.launch(cid)
        assert service.step(cid)['counts']['held'] == 1
        with self.assertRaisesRegex(CampaignError, 'HISTORY_INCOMPLETE'):
            service.step(cid)
        assert service.transport.posts == []
        assert service.detail(cid)['counts']['untouched'] == 1

    def test_address_review_hold_stays_unattempted_without_correction(self):
        service = self.fresh_service()
        source = demo_manifest(1)
        source['records'][0]['address_review'] = True
        cid = source['campaign_id']
        service.prepare_audience(source)
        service.launch(cid)
        result = service.step(cid)
        assert result['counts']['held'] == 1
        assert result['records'][0]['email'] == source['records'][0]['email']
        assert not service.transport.posts

    def test_strict_invalid_address_hold_has_bound_evidence_no_retry(self):
        service = self.fresh_service()
        tmp_path = self.tmp_path
        cid, key = prepare(service)
        service.transport.result_mode = 'invalid_address'
        service.launch(cid)
        detail = service.step(cid)
        assert detail['records'][0]['outcome'] == 'INVALID_ADDRESS_HOLD'
        hold = detail['records'][0]['hold']
        assert hold['intent_sha256'] == sha(encoded(detail['records'][0]['intent']))
        service.step(cid)
        assert len(service.transport.posts) == 1
        bundle = service.export_send_state(cid)
        other = CampaignService(Store(tmp_path / 'import.sqlite'))
        other.import_send_state(bundle)
        other.launch(cid)
        other.step(cid)
        assert other.transport.posts == []
        edit_file(bundle, f'records/{key}/hold.json', lambda x: x.update(error_sha256='0' * 64))
        untouched = CampaignService(Store(tmp_path / 'bad.sqlite'))
        with self.assertRaisesRegex(CampaignError, 'REVIEW_ERROR_HASH'):
            untouched.import_send_state(bundle)
        assert not untouched.list_campaigns()

    def test_400_evidence_must_exclusively_match_supported_email_fields(self):
        for field, value in [('email_validation_only', False), ('resource_id_absent', False),
            ('fields', []), ('fields', [{'path': 'subject', 'code': 'Email'}]),
            ('conversation_id', 'SYN-CONVERSATION-PRESENT')]:
            with self.subTest(field=field, value=value):
                error = {'http_status': 400, 'resource_id_absent': True, 'email_validation_only': True, 'fields': [{'path': 'customer.email', 'code': 'Email'}]}
                error[field] = value
                assert not CampaignService._email_error(error)

    def test_pause_during_request_saves_result_but_admits_no_next_send(self):
        service = self.fresh_service()
        cid, _ = prepare(service, 2)

        def pause():
            assert service.pause(cid)['status'] == 'PAUSE_REQUESTED'
        service.transport.on_create = pause
        service.launch(cid)
        detail = service.step(cid)
        assert detail['status'] == 'PAUSED' and detail['counts']['accepted'] == 1
        with self.assertRaises(CampaignError):
            service.step(cid)
        assert len(service.transport.posts) == 1
        service.transport.on_create = None
        service.resume(cid)
        assert service.step(cid)['counts']['accepted'] == 2

    def test_pause_during_history_admits_no_creation(self):
        service = self.fresh_service()
        cid, _ = prepare(service)
        service.transport.on_history = lambda: service.pause(cid)
        service.launch(cid)
        assert service.step(cid)['status'] == 'PAUSED'
        assert not service.transport.posts and (not service.detail(cid)['records'][0]['intent'])

    def test_store_ownership_is_exclusive_and_no_claim_for_another_pc(self):
        service = self.fresh_service()
        cid, _ = prepare(service)
        competitor = CampaignService(service.store)
        service.launch(cid)
        with self.assertRaisesRegex(CampaignError, 'OWNERSHIP_UNAVAILABLE'):
            competitor.launch(cid)
        service.pause(cid)
        competitor.transport.ownership_available = False
        with self.assertRaisesRegex(CampaignError, 'OWNERSHIP_UNAVAILABLE'):
            competitor.launch(cid)
        assert not competitor.transport.posts

    def test_reentrant_worker_step_cannot_double_post(self):
        service = self.fresh_service()
        cid, _ = prepare(service, 2)

        def reenter():
            with self.assertRaisesRegex(CampaignError, 'BUSY'):
                service.step(cid)
        service.transport.on_create = reenter
        service.launch(cid)
        service.step(cid)
        assert len(service.transport.posts) == 1

    def test_preflight_simulation_budget_and_authorization_are_required(self):
        for flag in ['authorized', 'rate_budget_available']:
            with self.subTest(flag=flag):
                service = self.fresh_service()
                cid, _ = prepare(service)
                service.launch(cid)
                setattr(service.transport, flag, False)
                with self.assertRaises(CampaignError):
                    service.step(cid)
                assert (
                    not service.transport.posts
                    and (not service.detail(cid)['records'][0]['intent'])
                )

    def test_no_live_transport_can_be_injected(self):
        service = self.fresh_service()

        class PretendTransport(SimulationTransport):
            pass
        with self.assertRaisesRegex(CampaignError, 'SIMULATION_TRANSPORT_ONLY'):
            CampaignService(service.store, PretendTransport())

    def test_bad_to_evidence_stays_review_no_resend(self):
        for to in [None, 'customer@example.test', ['extra@example.test'],
            ['synthetic-customer-1@example.test', 'extra@example.test']]:
            with self.subTest(to=to):
                service = self.fresh_service()
                cid, key = accepted(service)
                record = service.detail(cid)['records'][0]
                obs = service.transport.observe(record, record['receipt'])
                obs['to'] = to
                with self.assertRaisesRegex(CampaignError, 'TO_HEADER'):
                    service.reconcile(cid, key, obs)
                assert service.detail(cid)['counts']['unverified_review'] == 1
                service.step(cid)
                assert len(service.transport.posts) == 1

    def test_explicit_empty_to_is_distinct_and_missing_to_is_review(self):
        service = self.fresh_service()
        cid, key = accepted(service)
        record = service.detail(cid)['records'][0]
        obs = service.transport.observe(record, record['receipt'])
        obs['to'] = []
        detail = service.reconcile(cid, key, obs)
        assert detail['records'][0]['observation']['actual_to_header_verified'] is False
        assert (
            detail['records'][0]['observation']['recipient_verification_basis'] == 'submitted_custo'
            'mer_and_published_thread'
        )
        obs.pop('to')
        with self.assertRaises(CampaignError):
            service.reconcile(cid, key, obs)

    def test_published_verification_checks_full_evidence(self):
        for field, value in [('sender_id', 'SYN-REP-OTHER'), ('inbox_id',
            'SYN-INTERACTION-OTHER'), ('body_html', 'Different spacing'), ('state', 'draft'),
            ('scheduled', '2026-09-11T02:00:00Z'), ('outgoing_message_count', 2), ('cc', None),
            ('complete', False), ('customer_id', 'SYN-CUSTOMER-OTHER')]:
            with self.subTest(field=field, value=value):
                service = self.fresh_service()
                cid, key = accepted(service)
                record = service.detail(cid)['records'][0]
                obs = service.transport.observe(record, record['receipt'])
                obs[field] = value
                with self.assertRaises(CampaignError):
                    service.reconcile(cid, key, obs)
                assert service.detail(cid)['counts']['unverified_review'] == 1

    def test_transfer_roundtrip_preserves_pilot_bindings_and_is_idempotent(self):
        service = self.fresh_service()
        tmp_path = self.tmp_path
        cid, key = prepare(service, 2)
        service.launch(cid)
        service.step(cid)
        service.step(cid)
        bundle = service.export_send_state(cid)
        other = CampaignService(Store(tmp_path / 'import.sqlite'))
        imported = other.import_send_state(bundle)
        assert imported['counts']['accepted'] == 2
        assert (
            imported['records'][0]['intent']['fixture_sha256'] == sha(bundle['files']['pilot.json'])
        )
        assert (
            imported['records'][1]['intent']['fixture_sha256']
            == sha(bundle['files']['campaign.json'])
        )
        assert other.import_send_state(bundle) == imported
        other.launch(cid)
        other.step(cid)
        assert not other.transport.posts
        assert other.export_send_state(cid)['files'] == bundle['files']

    def test_accepted_unverified_import_is_read_only_reconciliation(self):
        service = self.fresh_service()
        tmp_path = self.tmp_path
        cid, key = accepted(service)
        bundle = service.export_send_state(cid)
        remove_file(bundle, f'records/{key}/observation.json', coherent_fixture=True)
        other = CampaignService(Store(tmp_path / 'import.sqlite'))
        assert other.import_send_state(bundle)['counts']['unverified_review'] == 1
        assert other.reconcile(cid, key)['counts']['accepted'] == 1
        assert other.transport.posts == []

    def test_unknown_import_blocks_resume(self):
        service = self.fresh_service()
        tmp_path = self.tmp_path
        cid, key = accepted(service)
        bundle = service.export_send_state(cid)
        remove_file(bundle, f'records/{key}/receipt.json', coherent_fixture=True)
        remove_file(bundle, f'records/{key}/observation.json', coherent_fixture=True)
        other = CampaignService(Store(tmp_path / 'import.sqlite'))
        assert other.import_send_state(bundle)['counts']['unknown'] == 1
        with self.assertRaises(CampaignError):
            other.resume(cid)
        assert not other.transport.posts

    def test_malformed_transfers_are_rejected_atomically(self):
        tmp_path = self.tmp_path
        for tamper in ['hash', 'recipient', 'payload', 'pilot', 'receipt_without_intent',
            'partial', 'path', 'source']:
            with self.subTest(tamper=tamper):
                service = self.fresh_service()
                cid, key = accepted(service)
                bundle = service.export_send_state(cid)
                path = f'records/{key}/intent.json'
                if tamper == 'hash':
                    bundle['hashes'][path] = '0' * 64
                elif tamper == 'recipient':
                    edit_file(bundle, path, lambda x: x.update(email='different@example.test'))
                elif tamper == 'payload':
                    edit_file(bundle, path, lambda x: x.update(payload_sha256='0' * 64))
                elif tamper == 'pilot':
                    edit_file(bundle, path, lambda x:
                        x.update(fixture_sha256=sha(bundle['files']['campaign.json'])))
                elif tamper == 'receipt_without_intent':
                    remove_file(bundle, path)
                elif tamper == 'partial':
                    bundle['complete'] = False
                elif tamper == 'path':
                    bundle['files']['../intent.json'] = '{}'
                    bundle['hashes']['../intent.json'] = sha('{}')
                elif tamper == 'source':
                    edit_file(bundle, 'campaign.json', lambda x:
                        x.update(subject='Changed synthetic subject'))
                other = CampaignService(Store(tmp_path / 'bad.sqlite'))
                with self.assertRaises(ValueError):
                    other.import_send_state(bundle)
                assert other.list_campaigns() == []

    def test_stale_state_import_cannot_erase_intent_or_acceptance(self):
        service = self.fresh_service()
        cid, _ = prepare(service)
        old = service.export_send_state(cid)
        service.launch(cid)
        service.step(cid)
        expected = service.pause(cid)
        with self.assertRaisesRegex(CampaignError, 'STALE_'):
            service.import_send_state(old)
        assert service.detail(cid) == expected

    def test_report_only_cannot_manufacture_acceptance(self):
        service = self.fresh_service()
        with self.assertRaises(CampaignError):
            service.import_send_state({'schema_version': 1, 'profile': 'synthetic',
                'synthetic_fixture': True, 'complete': True, 'results': [{'accepted': True}],
                'files': {}, 'hashes': {}})
        assert not service.list_campaigns()

    def test_changed_review_intent_bytes_fail_hash_even_same_json(self):
        service = self.fresh_service()
        tmp_path = self.tmp_path
        cid, key = prepare(service)
        service.transport.result_mode = 'invalid_address'
        service.launch(cid)
        service.step(cid)
        bundle = copy.deepcopy(service.export_send_state(cid))
        path = f'records/{key}/intent.json'
        bundle['files'][path] += '\n'
        bundle['hashes'][path] = sha(bundle['files'][path])
        other = CampaignService(Store(tmp_path / 'bad.sqlite'))
        with self.assertRaisesRegex(CampaignError, 'HASH|BINDING|BYTES'):
            other.import_send_state(bundle)
        assert not other.list_campaigns()

    def test_companion_scenarios_have_real_service_test_coverage(self):
        path = (
            Path(__file__).resolve().parent
            / 'fixtures/campaign_replies/scenarios.json'
        )
        names = {row['id'] for row in json.loads(path.read_text())['scenarios']}
        assert names == {'SYN-fresh', 'SYN-accepted', 'SYN-unknown', 'SYN-history_hold',
            'SYN-address_hold', 'SYN-unverified_receipt', 'SYN-receipt_without_intent',
            'SYN-changed_binding', 'SYN-changed_review_evidence', 'SYN-report_only',
            'SYN-ownership_unavailable', 'SYN-lost_response_rerun'}
