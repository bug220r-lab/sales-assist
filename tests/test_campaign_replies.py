"""Synthetic reply lifecycle parity, atomic imports, and durable review boundaries."""
from __future__ import annotations
import copy
import json
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from unittest.mock import patch
import tempfile
import unittest
from synthetic_sales_assist.campaign_replies.replies import (
    DraftConflict, RepliesService, ReplyValidationError, classify, derive, plain, prepare_evidence
)
from synthetic_sales_assist.campaign_replies.reply_fixtures import (
    demo_contact, demo_snapshot, demo_thread
)
from synthetic_sales_assist.campaign_replies.store import Store

def single_snapshot() -> dict[str, Any]:
    snapshot = demo_snapshot(1)
    snapshot['contacts'][0] = demo_contact()
    return snapshot

def import_one(service: RepliesService) -> dict[str, Any]:
    snapshot = single_snapshot()
    service.import_snapshot(snapshot)
    return service.detail(snapshot['contacts'][0]['conversation_id'])

def save(service: RepliesService, row: dict[str, Any], text:
    str='Hello, I will check the details.', reviewed: bool=True) -> dict[str, Any]:
    return service.save_draft(row['conversation_id'], text, row['local_draft']['revision'] if
        row['local_draft'] else 0, row['source_fingerprint'],
            row['style_profile']['version'], reviewed)

def newer(snapshot: dict[str, Any]) -> dict[str, Any]:
    snapshot = copy.deepcopy(snapshot)
    snapshot['last_success_utc'] = '2026-09-11T17:00:00Z'
    for contact in snapshot['contacts']:
        contact['last_checked_utc'] = snapshot['last_success_utc']
    return snapshot

class CampaignRepliesTests(unittest.TestCase):

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix='ssa-replies-test-')
        self.addCleanup(self.temporary.cleanup)
        self.temporary_path = Path(self.temporary.name)
        self.serial = 0

    def new_service(self) -> RepliesService:
        self.serial += 1
        return RepliesService(Store(self.temporary_path / f'replies-{self.serial}.sqlite3'))

    def test_repeat_partial_older_and_malformed_import_preserve_prior_state(self) -> None:
        service = self.new_service()
        snapshot = single_snapshot()
        assert service.import_snapshot(snapshot)['status'] == 'IMPORTED'
        assert service.import_snapshot(snapshot)['status'] == 'IDEMPOTENT'
        for mutation in (lambda s: s.update(sync_complete=False), lambda s:
            s.update(expected_contacts=2), lambda s:
                s.update(last_success_utc='2026-09-11T15:00:00Z'), lambda s:
                    s['contacts'][0].update(email='not-synthetic@' + 'example' + '.com'), lambda s:
                        s.update(extra='unknown')):
            broken = copy.deepcopy(snapshot)
            mutation(broken)
            with self.assertRaises(ValueError):
                service.import_snapshot(broken)
            assert service.list_queue()['total'] == 1
            assert (
                service.detail(snapshot['contacts'][0]['conversation_id'])['source_fingerprint']
                == import_one(service)['source_fingerprint']
            )
        truncated = newer(snapshot)
        truncated.update(contacts=[], expected_contacts=0)
        with self.assertRaisesRegex(ReplyValidationError, 'REMOVES_PRIOR_CONTACTS'):
            service.import_snapshot(truncated)

    def test_failed_late_contact_validation_commits_nothing(self) -> None:
        service = self.new_service()
        service.import_snapshot(single_snapshot())
        snapshot = newer(demo_snapshot(2))
        snapshot['contacts'][1]['threads'][0]['id'] = '12345'
        with self.assertRaises(ValueError):
            service.import_snapshot(snapshot)
        assert service.list_queue()['total'] == 1

    def test_drafts_survive_new_service_and_conflicting_editor(self) -> None:
        service = self.new_service()
        row = import_one(service)
        first = save(service, row)
        restarted = RepliesService(service.store)
        assert restarted.detail(row['conversation_id'])['local_draft']['text'] == first['text']
        with self.assertRaisesRegex(DraftConflict, 'REVISION'):
            save(restarted, row, 'A stale editor tries another response.')
        current = restarted.detail(row['conversation_id'])
        changed = save(restarted, current, 'A revised local response.', reviewed=False)
        assert not changed['reviewed']
        assert len(restarted.detail(row['conversation_id'])['superseded_drafts']) == 1

    def test_full_source_changes_invalidate_review_without_losing_text(self) -> None:
        for change in ['customer', 'staff', 'note', 'attachment', 'owner', 'recipient',
            'schedule', 'body', 'identity']:
            with self.subTest(change=change):
                service = self.new_service()
                row = import_one(service)
                saved = save(service, row)
                snapshot = newer(single_snapshot())
                contact = snapshot['contacts'][0]
                if change in ('customer', 'staff', 'note'):
                    contact['threads'].append(demo_thread(1, 2, {'staff':
                        'message'}.get(change, change), 'More context.'))
                elif change == 'attachment':
                    thread = demo_thread(1, 2, body='')
                    thread['_embedded']['attachments'] = [{'id':
                        'SYN-EVIDENCE-NEW-ATTACHMENT', 'filename': 'synthetic.png', 'size':
                            22, 'state': 'valid'}]
                    contact['threads'].append(thread)
                elif change == 'owner':
                    contact['conversation']['assignee']['id'] = 'SYN-REP-SECOND'
                elif change == 'recipient':
                    contact['threads'][0]['cc'] = ['another@example.test']
                elif change == 'schedule':
                    contact['threads'][0]['scheduled'] = {'sendAt': '2027-01-01T00:00:00Z'}
                elif change == 'body':
                    contact['threads'][1]['body'] = 'An updated checkout question.'
                else:
                    contact['conversation']['primaryCustomer'] = {'id': 'SYN-CUSTOMER-OTHER',
                        'email': 'other@example.test'}
                assert service.import_snapshot(snapshot)['invalidated_reviews'] == 1
                current = service.detail(row['conversation_id'])
                assert current['local_draft']['text'] == saved['text']
                assert current['local_draft']['reviewed'] is False
                assert current['source_fingerprint'] != row['source_fingerprint']
                with self.assertRaises(ReplyValidationError):
                    service.synthetic_job(row['conversation_id'])

    def test_profile_revision_invalidates_review_and_stale_style_save(self) -> None:
        service = self.new_service()
        row = import_one(service)
        saved = save(service, row)
        profile = {'version': 2, 'status': 'approved', 'source_label':
            'Locally approved synthetic test style', 'rules': ['Use concise paragraphs.']}
        service.set_style_profile(profile)
        current = service.detail(row['conversation_id'])
        assert current['local_draft']['text'] == saved['text']
        assert not current['local_draft']['reviewed']
        with self.assertRaisesRegex(DraftConflict, 'STYLE'):
            service.save_draft(row['conversation_id'], 'Review again.',
                current['local_draft']['revision'], current['source_fingerprint'], 1, True)
        assert service.style_profile() == profile

    def test_snapshot_poll_time_only_preserves_review(self) -> None:
        service = self.new_service()
        row = import_one(service)
        save(service, row)
        service.import_snapshot(newer(single_snapshot()))
        assert service.detail(row['conversation_id'])['local_draft']['reviewed']

    def test_undelivered_staff_content_does_not_answer(self) -> None:
        for kind, state, scheduled in [('note', 'published', False), ('message', 'draft',
            False), ('message', 'bounced', False), ('message', 'published', {'sendAt':
                '2027-01-01T00:00:00Z'})]:
            with self.subTest(kind=kind, state=state, scheduled=scheduled):
                contact = demo_contact()
                thread = demo_thread(1, 2, kind, 'A staff item.', state=state)
                thread['scheduled'] = scheduled
                contact['threads'].append(thread)
                assert derive(contact)['needs']

    def test_published_answer_resolves_and_followup_reopens_independently_of_workflow(self) -> None:
        contact = demo_contact()
        contact['conversation']['status'] = 'closed'
        assert derive(contact)['needs']
        contact['threads'].append(demo_thread(1, 2, 'message', 'A delivered response.'))
        assert not derive(contact)['needs']
        contact['threads'].append(demo_thread(1, 3, 'customer', 'One more question.'))
        assert derive(contact)['needs']

    def test_optout_and_complaint_preserved_and_cart_sort_deliberate(self) -> None:
        service = self.new_service()
        snapshot = demo_snapshot(2)
        snapshot['contacts'][0]['cart_total_cents'] = 999999
        snapshot['contacts'][1]['cart_total_cents'] = 10
        snapshot['contacts'][1]['threads'].append(demo_thread(2, 2, body='Can you confirm?'))
        service.import_snapshot(snapshot)
        assert service.list_queue()['items'][0]['category'] == 'optout'
        assert service.list_queue(sort='value')['items'][0]['category'] == 'ready'
        assert service.list_queue(needs_reply=False)['items'] == []
        assert service.list_queue(owner='SYN-REP-DEMO', limit=1)['total'] == 2
        assert len(service.list_queue(limit=1)['items']) == 1

    def test_attachment_only_latest_thread_preserves_meaningful_text(self) -> None:
        contact = demo_contact(3, variation=True)
        row = derive(contact)
        assert row['category'] == 'fitment'
        assert row['latest_thread_id'].endswith('001')
        assert row['latest_incoming_thread_id'].endswith('002')
        assert row['attachment_count'] == 1

    def test_exceptions_are_visible(self) -> None:
        for kind in ['anchor', 'identity', 'merge', 'sync', 'same_time']:
            with self.subTest(kind=kind):
                service = self.new_service()
                snapshot = single_snapshot()
                contact = snapshot['contacts'][0]
                if kind == 'anchor':
                    contact['anchor_thread_id'] = 'SYN-INTERACTION-MISSING'
                elif kind == 'identity':
                    contact['threads'][0]['customer'] = None
                elif kind == 'merge':
                    contact['merge_unresolved'] = True
                elif kind == 'sync':
                    contact['sync_error'] = 'A synthetic thread page is unavailable.'
                else:
                    contact['threads'].append(demo_thread(1, 3, 'message', minute=1))
                service.import_snapshot(snapshot)
                row = service.list_queue()['items'][0]
                assert row['category'] == 'exception'
                assert row['review'] is True

    def test_future_writer_blockers_remain_visible_and_no_job(self) -> None:
        for blocker in ['draft', 'unknown', 'scheduled', 'cc']:
            with self.subTest(blocker=blocker):
                service = self.new_service()
                snapshot = single_snapshot()
                contact = snapshot['contacts'][0]
                if blocker == 'draft':
                    contact['threads'].append(demo_thread(1, 2, 'message', state='draft'))
                elif blocker == 'unknown':
                    contact['write_outcome'] = 'accepted_unverified'
                elif blocker == 'scheduled':
                    thread = demo_thread(1, 2, 'message')
                    thread['scheduled'] = {'sendAt': '2027-01-01T00:00:00Z'}
                    contact['threads'].append(thread)
                else:
                    contact['conversation']['cc'] = ['second@example.test']
                service.import_snapshot(snapshot)
                row = service.detail(contact['conversation_id'])
                assert row['blockers'] and row['proposal'] is None
                save(service, row, reviewed=False)
                with self.assertRaises(ReplyValidationError):
                    service.synthetic_job(contact['conversation_id'])

    def test_reviewed_job_serializes_full_evidence_and_cannot_be_production_job(self) -> None:
        service = self.new_service()
        row = import_one(service)
        save(service, row)
        job = json.loads(json.dumps(service.synthetic_job(row['conversation_id'])))
        assert job['draft'] is True and job['synthetic_only'] is True
        assert job['remote_write_allowed'] is False and job['production_writer_compatible'] is False
        assert job['schema_version'] == 'synthetic-reviewed-job-v1'
        assert job['job']['conversation_id'].startswith('SYN-CONVERSATION-')
        assert job['job']['source_threads'] == row['source_threads']
        assert all((len(t['body_sha256']) == 64 for t in job['job']['source_threads']))

    def test_duplicate_thread_copies_require_exact_equality(self) -> None:
        service = self.new_service()
        snapshot = single_snapshot()
        snapshot['contacts'][0]['threads'].append(
            copy.deepcopy(snapshot['contacts'][0]['threads'][1])
        )
        service.import_snapshot(snapshot)
        assert len(service.detail(snapshot['contacts'][0]['conversation_id'])['threads']) == 2
        changed = newer(snapshot)
        changed['contacts'][0]['threads'][-1]['body'] = 'Conflicting duplicate copy.'
        with self.assertRaisesRegex(ReplyValidationError, 'CONFLICTING_THREAD_COPY'):
            service.import_snapshot(changed)

    def test_html_inert_and_reported_purchase_does_not_prove_revenue(self) -> None:
        service = self.new_service()
        assert plain('<script>alert(1)</script><p>&lt;img onerror=x&gt;</p>') == '<img onerror=x>'
        snapshot = single_snapshot()
        snapshot['contacts'][0]['threads'][1]['body'] = (
            '<p>I already purchased.</p><img onerror="alert(1)">'
        )
        service.import_snapshot(snapshot)
        row = service.detail(snapshot['contacts'][0]['conversation_id'])
        assert row['category'] == 'purchased'
        assert 'no order or recovered revenue' in row['action']
        assert '<' not in row['threads'][1]['display_text']
        assert row['outbound_links_enabled'] is False

    def test_shared_parity_fixture_matches_companion_node_lifecycle_and_evidence(self) -> None:
        tmp_path = self.temporary_path
        node = shutil.which('node')
        if node is None:
            self.skipTest('Node runtime unavailable; bundled companion parity requires Node')
        contacts = [demo_contact(i, variation=True) for i in range(1, 9)]
        for kind, state in (('note', 'published'), ('message', 'draft'), ('message', 'bounced')):
            contact = demo_contact()
            contact['threads'].append(demo_thread(1, 2, kind, 'Extra context', state=state))
            contacts.append(contact)
        fixture = tmp_path / 'parity.json'
        fixture.write_text(json.dumps(contacts), encoding='utf-8')
        base = (Path(__file__).resolve().parent / 'fixtures' / 'campaign_replies'
                / 'companion-reference')
        script = (
            "const fs=require('fs'),R=require(process.argv[1]),D=require(process"
            '.argv[2]);(async()=>{const rows=JSON.parse(fs.readFileSync(process.'
            "argv[3],'utf8'));const result=[];for(const c of rows){const r=R.der"
            'ive(c);result.push({category:r.category,needs:r.needs,replied:r.rep'
            'lied,latest_thread_id:r.latest_thread_id||null,latest_incoming_thre'
            'ad_id:r.latest_incoming_thread_id||null,attachment_count:r.attachme'
            'nt_count,has_draft:r.has_draft,source_threads:await D.prepareEviden'
            'ce(r)});}process.stdout.write(JSON.stringify(result));})().catch(e='
            '>{console.error(e);process.exitCode=1;});'
        )
        result = subprocess.run([node, '-e', script, str(base / 'replies-core.js'), str(base
            / 'drafts-core.js'), str(fixture)], check=True, text=True, capture_output=True,
                timeout=30)
        expected = json.loads(result.stdout)
        for contact, javascript in zip(contacts, expected, strict=True):
            python = derive(contact)
            for field in javascript:
                assert (prepare_evidence(contact) if field == 'source_threads' else
                    python[field]) == javascript[field], field

    def test_scale_fixture_import_and_paged_cached_queue(self) -> None:
        service = self.new_service()
        snapshot = demo_snapshot(10000)
        started = time.perf_counter()
        service.import_snapshot(snapshot)
        imported = time.perf_counter() - started
        started = time.perf_counter()
        page = service.list_queue(offset=9950, limit=50)
        queued = time.perf_counter() - started
        assert page['total'] == 10000 and len(page['items']) == 50
        assert all(('threads' not in item for item in page['items']))
        print(
            f'\nSYNTHETIC_SCALE conversations=10000 import_seconds={imported:.3f} '
            f'queue_seconds={queued:.3f}'
        )

    def test_unknown_starter_is_labeled_and_empty_prepared_list_is_not_invented(self) -> None:
        service = self.new_service()
        snapshot = single_snapshot()
        snapshot['contacts'][0]['threads'][1]['body'] = 'Could you explain that?'
        service.import_snapshot(snapshot)
        row = service.detail(snapshot['contacts'][0]['conversation_id'])
        assert row['proposal']['source'] == 'Reusable starter'
        assert row['proposal']['body'] == ''
        assert row['proposal']['analysis_status'] == 'Not AI analysis'
        assert classify('I already ordered; can you check shipping?')['category'] == 'service'

    def test_concurrent_edit_has_exactly_one_winner(self) -> None:
        service = self.new_service()
        row = import_one(service)
        barrier = threading.Barrier(2)

        def edit(text: str) -> str:
            independent = RepliesService(service.store)
            barrier.wait(timeout=10)
            try:
                save(independent, row, text)
                return "saved"
            except DraftConflict:
                return "conflict"

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(edit, ["First local edit.", "Second local edit."]))
        self.assertEqual(sorted(outcomes), ["conflict", "saved"])
        self.assertEqual(service.detail(row["conversation_id"])["local_draft"]["revision"], 1)

    def test_new_source_requires_new_fingerprint_even_for_unreviewed_edit(self) -> None:
        service = self.new_service()
        row = import_one(service)
        snapshot = newer(single_snapshot())
        snapshot["contacts"][0]["threads"].append(demo_thread(1, 2, "note", "Changed context."))
        service.import_snapshot(snapshot)
        with self.assertRaisesRegex(DraftConflict, "SOURCE"):
            save(service, row, reviewed=False)

    def test_metrics_and_future_suppressions_are_explicitly_synthetic(self) -> None:
        service = self.new_service()
        service.import_snapshot(demo_snapshot())
        metrics = service.list_queue()["metrics"]
        self.assertEqual(metrics["accepted_outreach"], 8)
        self.assertEqual(metrics["incoming_replies"], 9)
        self.assertEqual(metrics["unanswered_requests"], 6)
        self.assertEqual(metrics["customer_reported_purchases"], 1)
        self.assertNotIn("recovered_revenue", metrics)
        suppressions = service.suppression_candidates()
        self.assertFalse(suppressions["enforced_by_running_sender"])
        self.assertEqual(suppressions["profile"], "synthetic")
        self.assertEqual(suppressions["candidates"][0]["category"], "optout")

    def test_legacy_metrics_projection_rebuild_preserves_facts_and_review(self) -> None:
        service = self.new_service()
        snapshot = demo_snapshot()
        service.import_snapshot(snapshot)
        row = service.detail(snapshot["contacts"][0]["conversation_id"])
        save(service, row)
        expected_metrics = service.list_queue()["metrics"]
        preserved_tables = (
            "cr_snapshots", "cr_local_drafts", "cr_draft_versions", "cr_style_profiles",
        )
        with service.store.transaction() as db:
            preserved = {
                table: [tuple(item) for item in db.execute("SELECT * FROM " + table)]
                for table in preserved_tables
            }
            sources = [tuple(item) for item in db.execute(
                "SELECT conversation_id,source_json,fingerprint FROM cr_reply_contacts "
                "ORDER BY conversation_id"
            )]
            for item in db.execute(
                "SELECT conversation_id,derived_json FROM cr_reply_contacts"
            ).fetchall():
                legacy = json.loads(item["derived_json"])
                for field in (
                    "accepted_outreach", "incoming_reply_count", "customer_reported_purchase",
                ):
                    del legacy[field]
                db.execute(
                    "UPDATE cr_reply_contacts SET derived_json=? WHERE conversation_id=?",
                    (json.dumps(legacy), item["conversation_id"]),
                )
            db.execute("DROP TABLE cr_reply_projection_schema")
        self.assertEqual(service.list_queue()["metrics"]["accepted_outreach"], 0)
        reopened = RepliesService(service.store)
        self.assertEqual(reopened.list_queue()["metrics"], expected_metrics)
        with service.store.read() as db:
            for table in preserved_tables:
                self.assertEqual(
                    [tuple(item) for item in db.execute("SELECT * FROM " + table)],
                    preserved[table],
                )
            self.assertEqual(sources, [tuple(item) for item in db.execute(
                "SELECT conversation_id,source_json,fingerprint FROM cr_reply_contacts "
                "ORDER BY conversation_id"
            )])
            self.assertEqual(
                db.execute("SELECT version FROM cr_reply_projection_schema").fetchone()[0], 1,
            )
        with patch(
            "synthetic_sales_assist.campaign_replies.replies.derive",
            side_effect=AssertionError("Cached reads and subsequent restarts must not regenerate"),
        ):
            cached = RepliesService(service.store)
            self.assertEqual(cached.list_queue()["metrics"], expected_metrics)
