"""Synthetic labeled-copy rendering, exact approval, and mocked API readback."""

from __future__ import annotations

import copy
import html
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from doi_draft_transfer.contract import (
    CTA_TEXT, CTA_URL, MAILBOX_ID, SIGNATURE, USER_ID, TransferError,
    approval_binding, body_segments, rendered_body, review_holds, row_holds, text_hash,
)
from doi_draft_transfer.helpscout import HelpScoutDraftClient, body_links, body_text, payload_for
from doi_draft_transfer.service import DraftTransferService
from doi_draft_transfer.store import DraftTransferStore, FILENAME
from tests.test_doi_draft_transfer import MockClient, csv_text, synthetic_row, verified_review

LABEL = 'SYN bracket & washer'
INTRO = 'SYN question only; no order change.'


def labeled_row():
    row = synthetic_row()
    cart = json.loads(row['cart_links_json'])[0]['url']
    row['selected_body_text'] = (
        f'{INTRO}\n\n[{LABEL}]({cart})\n\n{SIGNATURE}\n\n[{CTA_TEXT}]({CTA_URL})'
    )
    row['selected_body_sha256'] = text_hash(row['selected_body_text'])
    return row


def expected_html(row):
    """Independent response fixture includes harmless inline markup from a remote editor."""
    cart = json.loads(row['cart_links_json'])[0]['url']
    return (
        '<div>' + INTRO + '<br><br><a href="' + html.escape(cart, quote=True)
        + '"><span>SYN</span> bracket &amp; washer</a><br><br>'
        + SIGNATURE.replace('\n', '<br>') + '<br><br><a href="'
        + html.escape(CTA_URL, quote=True) + '">' + CTA_TEXT + '</a></div>'
    )


def remote_draft(row, body):
    return {
        'id': 99000001, 'state': 'draft', 'mailboxId': MAILBOX_ID,
        'subject': row['subject'], 'assignee': {'id': USER_ID},
        'primaryCustomer': {'email': row['recipient_email']},
        '_embedded': {'threads': [{
            'type': 'message', 'state': 'draft', 'createdBy': {'id': USER_ID},
            'to': [row['recipient_email']], 'body': body,
        }]},
    }


class LabeledCopyTests(unittest.TestCase):
    def test_exact_labels_urls_visible_text_and_source_hashes_are_preserved(self):
        row = labeled_row()
        before = copy.deepcopy(row)
        value = rendered_body(row['selected_body_text'])
        visible = f'{INTRO}\n\n{LABEL}\n\n{SIGNATURE}\n\n{CTA_TEXT}'
        self.assertEqual(body_text(value), visible)
        self.assertEqual(''.join(part['text'] for part in body_segments(row['selected_body_text'])),
                         visible)
        self.assertEqual(body_links(value), body_links(expected_html(row)))
        self.assertEqual(value.count('<a '), 2)
        self.assertNotIn('](', value)
        self.assertNotIn('<a ', value.split('>SYN bracket')[1].split('</a>')[0])
        self.assertEqual(row_holds(row), [])
        self.assertEqual(row, before)
        self.assertEqual(row['source_body_sha256'], synthetic_row()['source_body_sha256'])

    def test_html_is_escaped_and_legacy_plain_copy_and_newlines_remain_exact(self):
        row = synthetic_row()
        self.assertEqual(body_text(rendered_body(row['selected_body_text'])),
                         row['selected_body_text'])
        sample = '[SYN <img src=x onerror=bad> & "quoted"]'
        sample += '(https://example.invalid/?a=1&b=2)\r\nSYN plain\rline'
        value = rendered_body(sample)
        self.assertNotIn('<img', value)
        self.assertIn('&lt;img', value)
        self.assertEqual(body_text(value),
                         'SYN <img src=x onerror=bad> & "quoted"\nSYN plain\nline')
        self.assertEqual(body_links(value)[0][0], ['https://example.invalid/?a=1&b=2'])
        unsafe = '[SYN](javascript:alert(1)) <script>SYN</script>'
        self.assertNotIn('<a ', rendered_body(unsafe))
        self.assertEqual(body_text(rendered_body(unsafe)), unsafe)

    def test_label_and_destination_changes_invalidate_exact_approval_binding(self):
        row, review = labeled_row(), verified_review()
        initial = approval_binding(row, 1, review)
        for body in (row['selected_body_text'].replace(LABEL, 'SYN changed label'),
                     row['selected_body_text'].replace('add1=99000001', 'add1=99000002')):
            changed = dict(row, selected_body_text=body, selected_body_sha256=text_hash(body))
            self.assertNotEqual(approval_binding(changed, 1, review), initial)

    def test_mocked_create_accepts_labeled_draft_and_keeps_closed_payload(self):
        row = labeled_row()
        client = HelpScoutDraftClient('SYN-DUMMY-NOT-A-CREDENTIAL')
        replies = [(201, {'resource-id': '99000001'}, b''),
                   (200, {}, json.dumps(remote_draft(row, expected_html(row))).encode())]
        with patch.object(client, '_request', side_effect=replies) as requests:
            outcome = client.create_draft(row)
        self.assertEqual(outcome['state'], 'CREATED')
        self.assertFalse(outcome['retry_allowed'])
        self.assertEqual([call.args[:2] for call in requests.call_args_list], [
            ('POST', '/v2/conversations'), ('GET', '/v2/conversations/99000001?embed=threads')
        ])
        payload = requests.call_args_list[0].args[2]
        self.assertEqual(payload, payload_for(row))
        self.assertEqual(payload['mailboxId'], MAILBOX_ID)
        self.assertEqual(payload['assignTo'], USER_ID)
        self.assertFalse(payload['autoReply'])
        self.assertEqual(len(payload['threads']), 1)
        self.assertEqual(payload['threads'][0]['type'], 'reply')
        self.assertIs(payload['threads'][0]['draft'], True)
        self.assertNotIn('cc', payload['threads'][0])
        self.assertNotIn('bcc', payload['threads'][0])

    def test_readback_rejects_changed_link_text_target_span_and_malformed_anchors(self):
        row = labeled_row()
        good = expected_html(row)
        cart = html.escape(json.loads(row['cart_links_json'])[0]['url'], quote=True)
        moved = good.replace('<a href="' + cart + '"><span>SYN</span> bracket &amp; washer</a>',
                             '<span>SYN</span> <a href="' + cart + '">bracket</a> &amp; washer')
        self.assertEqual(body_text(moved), body_text(good))
        variants = [
            good.replace('bracket', 'different'),
            good.replace('add1=99000001', 'add1=99000002'), moved,
            good.replace('<span>SYN</span>', '<a>SYN</a>'),
            good.replace('<a href=', '<a href="https://example.invalid/" href=', 1),
            good.replace('</a>', '', 1),
        ]
        client = HelpScoutDraftClient('SYN-DUMMY-NOT-A-CREDENTIAL')
        for changed in variants:
            with self.subTest(body=changed), patch.object(client, '_request', return_value=(
                200, {}, json.dumps(remote_draft(row, changed)).encode()
            )) as requests:
                outcome = client.verify_draft(row, {
                    'conversation_id': '99000001', 'state': 'CREATED', 'retry_allowed': False
                })
                self.assertEqual(outcome['state'], 'CREATED_UNVERIFIED')
                self.assertEqual(outcome['conversation_id'], '99000001')
                self.assertFalse(outcome['retry_allowed'])
                self.assertEqual(requests.call_args.args[0], 'GET')

    def test_conditional_review_does_not_invent_factual_or_cart_evidence(self):
        row, review = labeled_row(), verified_review()
        review['checks']['customer_approval'].update(
            decision='pending_conditional_outreach', conditional_copy_reviewed=True,
            evidence='SYN exact question reviewed; customer decision remains pending',
        )
        self.assertEqual(review_holds(row, review), [])
        acknowledged = copy.deepcopy(review)
        acknowledged['checks']['allocation']['evidence'] = (
            'SYN allocation remains unknown; exact conditional copy makes no allocation promise'
        )
        self.assertEqual(review_holds(row, acknowledged), [])
        for name in ('fitment', 'allocation', 'stock', 'price', 'quantity', 'kit_scope'):
            missing = copy.deepcopy(review)
            missing['checks'][name] = {'resolved': False, 'evidence': ''}
            self.assertIn('REVIEW_' + name.upper(), review_holds(row, missing))
        missing = copy.deepcopy(review)
        missing['carts']['SYN-OPTION-1']['verified'] = False
        self.assertIn('CART_CONTENT_REVIEW_REQUIRED', review_holds(row, missing))


class LabeledApprovalTests(unittest.TestCase):
    def test_changed_rendering_marks_old_approval_pending_and_allows_explicit_reapproval(self):
        with tempfile.TemporaryDirectory(
            prefix='ssa-synthetic-labels-', dir=os.environ.get('SSA_TRANSFER_TEST_ROOT')
        ) as folder:
            client = MockClient()
            service = DraftTransferService(DraftTransferStore(Path(folder) / FILENAME), client)
            row = labeled_row()
            preview = service.preview_import(csv_text([row]))
            self.assertEqual(preview['errors'], [])
            service.commit_import(preview['preview_token'], preview['revision'])
            item = service.detail(row['order_id'])
            service.edit(item['order_id'], item['version'], {
                key: row[key] for key in ('selected_body_text', 'recipient_email', 'reviewer_notes')
            }, verified_review())
            with patch('doi_draft_transfer.contract.rendered_body',
                       return_value='<div>SYN prior renderer preview</div>'):
                old = service.detail(row['order_id'])
                service.approve(old['order_id'], old['version'], old['approval_binding'],
                                'I_APPROVE_THIS_EXACT_HELP_SCOUT_DRAFT')
                self.assertTrue(service.detail(row['order_id'])['approved'])
            current = service.detail(row['order_id'])
            self.assertFalse(current['approved'])
            self.assertEqual(current['review_approval'], 'PENDING')
            self.assertNotEqual(current['approval_binding'], old['approval_binding'])
            with self.assertRaisesRegex(TransferError, 'CURRENT_EXACT_APPROVAL_REQUIRED'):
                service.transfer(current['order_id'], current['version'],
                                 current['approval_binding'])
            self.assertEqual(client.calls, [])
            service.approve(current['order_id'], current['version'], current['approval_binding'],
                            'I_APPROVE_THIS_EXACT_HELP_SCOUT_DRAFT')
            rebound = service.detail(row['order_id'])
            self.assertTrue(rebound['approved'])
            self.assertEqual(rebound['approval']['binding'], rebound['approval_binding'])
            self.assertEqual(rebound['row'], row)
            self.assertEqual(rebound['preview_segments'], body_segments(row['selected_body_text']))
            self.assertEqual(client.calls, [])


if __name__ == '__main__':
    unittest.main()
