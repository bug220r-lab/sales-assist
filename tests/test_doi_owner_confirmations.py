"""Fictional capture-bound owner evidence and currency policy regressions."""

import copy
import json
import unittest

from tests.test_csv_staging_independent import summary, line, csv_text
from doi_csv_staging import SUMMARY_HEADERS, LINE_HEADERS
from doi_csv_staging.review import DOIReviewSession, DOIReviewError, review_response_bytes
from doi_csv_staging.review_policy import (
    ConfirmedOtherRep,
    OwnerConfirmations,
    OwnerConfirmationError,
    currency_projection,
    record_digest,
    text_digest,
    parse_owner_confirmations,
)

AS_OF = '2026-10-05T16:00:00Z'


def pair(rows=None):
    rows = rows or [summary(displayed_sales_credit_value='synthetic_unmapped_rep')]
    return (
        rows,
        csv_text(SUMMARY_HEADERS, rows),
        csv_text(LINE_HEADERS, [line(r['order_id']) for r in rows]),
    )


def confirmations(rows, left, right, **changes):
    fields = dict(
        order_id=rows[0]['order_id'],
        summary_ordinal=2,
        record_sha256=record_digest(rows[0]),
        confirmed_at='2026-10-05T15:00:00Z',
        evidence_reference='SYN-OWNER-CONFIRMED',
    )
    fields.update(changes)
    return OwnerConfirmations(text_digest(left), text_digest(right), (ConfirmedOtherRep(**fields),))


def load(row=None):
    _, left, right = pair([row or summary()])
    return DOIReviewSession(as_of=lambda: AS_OF).load(left, right, 0)


class OwnerConfirmationTests(unittest.TestCase):
    def test_exact_bound_record_excluded_with_owner_provenance(self):
        rows, left, right = pair()
        state = DOIReviewSession(
            as_of=lambda: AS_OF, owner_confirmations=confirmations(rows, left, right)
        ).load(left, right, 0)
        self.assertEqual(state['orders'][0]['rep_scope'], 'OTHER_REP')
        self.assertEqual(
            state['orders'][0]['rep_confirmation']['confirmed_at'], '2026-10-05T15:00:00Z'
        )
        self.assertEqual(state['ownership_review']['excluded_count'], 1)
        self.assertEqual(state['orders'][0]['sales_credit_entitlement'], 'UNINTERPRETED')

    def test_same_rep_on_another_order_is_not_a_global_alias(self):
        rows, left, right = pair(
            [
                summary(displayed_sales_credit_value='synthetic_unmapped_rep'),
                summary('90000002', displayed_sales_credit_value='synthetic_unmapped_rep'),
            ]
        )
        state = DOIReviewSession(
            as_of=lambda: AS_OF, owner_confirmations=confirmations(rows, left, right)
        ).load(left, right, 0)
        self.assertEqual([o['rep_scope'] for o in state['orders']], ['OTHER_REP', 'REP_UNMAPPED'])
        self.assertEqual(state['ownership_review']['held_count'], 1)

    def test_changed_csv_in_either_side_invalidates_binding(self):
        rows, left, right = pair()
        policy = confirmations(rows, left, right)
        for a, b in (
            (left.replace('fictional@example.test', 'synthetic@example.test'), right),
            (left, right.replace('SYN-SKU-1', 'SYN-SKU-2')),
        ):
            state = DOIReviewSession(as_of=lambda: AS_OF, owner_confirmations=policy).load(a, b, 0)
            self.assertEqual(state['orders'][0]['rep_scope'], 'REP_UNMAPPED')

    def test_wrong_id_ordinal_or_record_hash_never_applies(self):
        rows, left, right = pair()
        for changed in (
            {'order_id': '90000002'},
            {'summary_ordinal': 3},
            {'record_sha256': '0' * 64},
        ):
            state = DOIReviewSession(
                as_of=lambda: AS_OF, owner_confirmations=confirmations(rows, left, right, **changed)
            ).load(left, right, 0)
            self.assertEqual(state['orders'][0]['rep_scope'], 'REP_UNMAPPED')

    def test_confirmation_before_capture_or_after_as_of_does_not_apply(self):
        rows, left, right = pair()
        for stamp in ('2026-10-05T13:00:00Z', '2026-10-05T17:00:00Z'):
            state = DOIReviewSession(
                as_of=lambda: AS_OF,
                owner_confirmations=confirmations(rows, left, right, confirmed_at=stamp),
            ).load(left, right, 0)
            self.assertEqual(state['orders'][0]['rep_scope'], 'REP_UNMAPPED')

    def test_missing_field_blank_or_untrusted_capture_is_not_reclassified(self):
        for changes in (
            {'displayed_sales_credit_field': ''},
            {'displayed_sales_credit_value': ''},
            {'capture_complete': 'no'},
        ):
            row = summary(displayed_sales_credit_value='synthetic_unmapped_rep')
            row.update(changes)
            rows, left, right = pair([row])
            state = DOIReviewSession(
                as_of=lambda: AS_OF, owner_confirmations=confirmations(rows, left, right)
            ).load(left, right, 0)
            self.assertNotEqual(state['orders'][0]['rep_scope'], 'OTHER_REP')

    def test_private_decisions_never_promote_eligible_aliases(self):
        rows, left, right = pair([summary(displayed_sales_credit_value='customer-web')])
        state = DOIReviewSession(
            as_of=lambda: AS_OF, owner_confirmations=confirmations(rows, left, right)
        ).load(left, right, 0)
        self.assertEqual(state['orders'][0]['rep_scope'], 'UNASSIGNED_WEB')
        self.assertNotIn('rep_confirmation', state['orders'][0])

    def test_duplicate_decisions_and_unsafe_reference_rejected(self):
        rows, left, right = pair()
        policy = confirmations(rows, left, right)
        with self.assertRaises(OwnerConfirmationError):
            OwnerConfirmations(
                policy.summary_text_sha256, policy.lines_text_sha256, policy.decisions * 2
            )
        with self.assertRaises(OwnerConfirmationError):
            confirmations(rows, left, right, evidence_reference='fictional-private@example.test')

    def test_closed_parser_rejects_unknown_members_and_duplicate_keys(self):
        for text in (
            '{}',
            '{"schema":"x","schema":"y"}',
            json.dumps(
                {
                    'schema': 'doi-owner-confirmations/v1',
                    'summary_text_sha256': '',
                    'lines_text_sha256': '',
                    'decisions': [],
                    'all_held': True,
                }
            ),
        ):
            with self.assertRaises(OwnerConfirmationError):
                parse_owner_confirmations(text)

    def test_confirmation_json_roundtrip_and_config_type(self):
        rows, left, right = pair()
        p = confirmations(rows, left, right)
        d = p.decisions[0]
        value = {
            'schema': 'doi-owner-confirmations/v1',
            'summary_text_sha256': p.summary_text_sha256,
            'lines_text_sha256': p.lines_text_sha256,
            'decisions': [d.__dict__],
        }
        self.assertEqual(parse_owner_confirmations(json.dumps(value)), p)
        from synthetic_sales_assist.portal.server import PortalServerConfig

        self.assertEqual(PortalServerConfig(owner_confirmations=p).owner_confirmations, p)
        from synthetic_sales_assist.portal.__main__ import _parser

        self.assertEqual(
            str(
                _parser()
                .parse_args(['--doi-owner-confirmations', 'SYN-private.json'])
                .doi_owner_confirmations
            ),
            'SYN-private.json',
        )

    def test_projection_forged_proof_rejected(self):
        state = load()
        state['orders'][0]['rep_confirmation'] = {
            'confirmed_at': '2026-10-05T15:00:00Z',
            'evidence_reference': 'SYN-OWNER-CONFIRMED',
        }
        with self.assertRaises(DOIReviewError):
            review_response_bytes(state)


class CurrencyPolicyTests(unittest.TestCase):
    def test_missing_currency_resolves_usd_with_policy_provenance_and_raw_tokens(self):
        for code in ('', 'UNKNOWN', 'Unknown - not displayed'):
            state = load(
                summary(
                    currency_code=code,
                    currency_symbol_displayed='$',
                    order_total_numeric='10',
                    order_total_displayed='$10',
                )
            )
            o = state['orders'][0]
            self.assertEqual(o['currency'], [code, '$', 'OWNER_USD'])
            self.assertNotIn('CURRENCY_UNKNOWN', o['holds'])
            self.assertNotIn('CURRENCY_NOT_CONFIRMED', o['evidence']['missing_fact_codes'])
            self.assertEqual(o['split']['total']['amount'], '10')
            self.assertFalse(o['decision_eligible'])

    def test_explicit_usd_is_observed_not_policy(self):
        self.assertEqual(
            load(summary(currency_code='USD', currency_symbol_displayed='$'))['orders'][0][
                'currency'
            ],
            ['USD', '$', 'OBSERVED_USD'],
        )

    def test_contradictory_codes_or_symbols_are_flagged_without_conversion(self):
        for code, symbol in (('EUR', ''), ('USD', '\u20ac'), ('UNKNOWN', '\u00a3'), ('CAD', '$')):
            o = load(summary(currency_code=code, currency_symbol_displayed=symbol))['orders'][0]
            self.assertEqual(o['currency'], [code, symbol, 'CONFLICT'])
            self.assertIn('CURRENCY_CONFLICT', o['holds'])

    def test_malformed_total_stays_invalid_or_mismatched(self):
        for displayed, numeric, status in (('$oops', '10', 'INVALID'), ('$10', '11', 'MISMATCH')):
            o = load(
                summary(
                    currency_code='UNKNOWN',
                    currency_symbol_displayed='$',
                    order_total_displayed=displayed,
                    order_total_numeric=numeric,
                )
            )['orders'][0]
            self.assertEqual(o['split']['total']['status'], status)
            self.assertIsNone(o['split']['total']['amount'])
            self.assertEqual(o['currency'][2], 'OWNER_USD')

    def test_malformed_currency_customer_marker_redacted(self):
        marker = 'SYN-PRIVATE-CUSTOMER@example.test'
        state = load(summary(currency_code=marker, currency_symbol_displayed=marker))
        self.assertNotIn(marker, review_response_bytes(state).decode())
        self.assertEqual(state['orders'][0]['currency'], [None, None, 'CONFLICT'])

    def test_forged_policy_currency_rejected(self):
        state = load(summary(currency_code='EUR'))
        state['orders'][0]['currency'][2] = 'OWNER_USD'
        with self.assertRaises(DOIReviewError):
            review_response_bytes(state)

    def test_large_snapshot_still_obeys_existing_response_cap(self):
        rows = [summary(str(90000000 + i)) for i in range(1, 501)]
        _, left, right = pair(rows)
        state = DOIReviewSession(as_of=lambda: AS_OF).load(left, right, 0)
        self.assertEqual(state['error_code'], 'REVIEW_RESPONSE_LIMIT')
        self.assertEqual(state['orders'], [])
