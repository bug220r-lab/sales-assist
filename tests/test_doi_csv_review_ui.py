"""Independent UI/session tests using only generated fictional capture records."""

import json
import unittest
import http.client
import threading

from tests.test_csv_staging_independent import summary, line, csv_text
from doi_csv_staging import SUMMARY_HEADERS, LINE_HEADERS
from doi_csv_staging.review import (
    DOIReviewSession,
    DOIReviewError,
    MAX_CSV_BYTES,
    parse_review_request,
)
from synthetic_sales_assist.portal.doi_csv_review_ui import (
    render_doi_csv_review_page,
    DOI_CSV_REVIEW_JS,
)


def fictional_csvs(summaries=None, lines=None):
    return (
        csv_text(SUMMARY_HEADERS, summaries if summaries is not None else [summary()]),
        csv_text(LINE_HEADERS, lines if lines is not None else [line()]),
    )


class ReviewSessionTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000.0
        self.session = DOIReviewSession(clock=lambda: self.now, ttl_seconds=10)

    def load(self, summaries=None, lines=None):
        a, b = fictional_csvs(summaries, lines)
        self.session.load(a, b, self.session.snapshot()['revision'])
        return self.session.snapshot()

    def test_counts_are_occurrences_and_orders_not_fulfillment_actions(self):
        state = self.load(
            [summary(active_purchased_rows='2')],
            [line(drop_ship='yes'), line(line_identifier='SYN-LINE-2', drop_ship='no')],
        )
        self.assertEqual(state['counts']['summary_records'], 1)
        self.assertEqual(state['counts']['line_records'], 2)
        self.assertEqual(state['counts']['orders'], 1)
        self.assertEqual(state['counts']['purchased_records'], 2)
        self.assertFalse(state['orders'][0]['decision_eligible'])
        self.assertFalse(state['orders'][0]['evidence_complete'])
        self.assertNotIn('DS_SEPARATION', json.dumps(state))

    def test_private_marker_fields_never_enter_closed_snapshot(self):
        private = 'SYN-PRIVATE <script>alert("fictional")</script> fictional-secret@example.test'
        state = self.load(
            [
                summary(
                    customer_info_email=private,
                    displayed_sales_credit_value=private,
                    queue_source_url=private,
                )
            ],
            [line(product_name=private, queue_source_url=private)],
        )
        self.assertNotIn(private, json.dumps(state))
        self.assertNotIn('fictional-secret@example.test', json.dumps(state))
        self.assertEqual(
            set(state),
            {
                'schema',
                'revision',
                'status',
                'counts',
                'groups',
                'orders',
                'batch_holds',
                'error_code',
                'expires_in_seconds',
                'split_review',
                'ownership_review',
            },
        )

    def test_jude_assignment_distinct_from_customer_web_credit(self):
        state = self.load([summary(displayed_sales_credit_value='Customer / Web')])
        self.assertNotIn('REVIEW_ASSIGNMENT_UNVERIFIED', json.dumps(state))
        self.assertFalse(state['orders'][0]['decision_eligible'])

    def test_placeholder_is_not_purchase_and_unknown_fields_not_actionable(self):
        placeholder = line(
            row_type='Component coverage gap - not a merchandise line',
            counts_as_purchase='no',
            parent_line_id='SYN-LINE-1',
            line_identifier='',
            order_capture_complete='no',
        )
        state = self.load(
            [summary(capture_complete='no')],
            [line(drop_ship='UNKNOWN', remaining_quantity='Unknown - not displayed'), placeholder],
        )
        self.assertEqual(state['counts']['purchased_records'], 1)
        self.assertEqual(state['counts']['placeholder_records'], 1)
        self.assertTrue(state['orders'][0]['visible_coverage_complete'])
        self.assertFalse(state['orders'][0]['decision_eligible'])

    def test_duplicate_structural_hold_preserves_occurrence_counts(self):
        state = self.load([summary(active_purchased_rows='2')], [line(), line()])
        self.assertEqual(state['counts']['line_records'], 2)
        self.assertIn('DUPLICATE_LINE_ID', json.dumps(state))
        self.assertFalse(state['orders'][0]['visible_coverage_complete'])

    def test_formula_batch_quarantine_does_not_publish_safe_old_state(self):
        self.load()
        state = self.load([summary(stock_eta_exact='=FICTIONAL(1)')])
        self.assertIn('CSV_FORMULA_RISK', json.dumps(state))
        self.assertTrue(state['batch_holds'])
        self.assertTrue(all(not o['decision_eligible'] for o in state['orders']))

    def test_revision_mismatch_preserves_state_without_mutation(self):
        before = self.load()
        a, b = fictional_csvs([summary('90000002')], [line('90000002')])
        with self.assertRaises(DOIReviewError) as caught:
            self.session.load(a, b, before['revision'] - 1)
        self.assertEqual(caught.exception.code, 'REVISION_MISMATCH')
        self.assertEqual(self.session.snapshot(), before)

    def test_clear_removes_orders_and_increments_revision(self):
        before = self.load()
        self.session.clear(before['revision'])
        after = self.session.snapshot()
        self.assertEqual(after['orders'], [])
        self.assertGreater(after['revision'], before['revision'])

    def test_repeated_load_replaces_instead_of_appending(self):
        self.load()
        after = self.load([summary('90000002')], [line('90000002')])
        self.assertEqual(after['counts']['orders'], 1)
        self.assertEqual(after['orders'][0]['order_id'], '90000002')
        self.assertNotIn('90000001', json.dumps(after))

    def test_interrupted_flow_invalidate_discards_loaded_state(self):
        self.load()
        self.session.invalidate('REVIEW_TRANSPORT_INVALID')
        state = self.session.snapshot()
        self.assertEqual(state['orders'], [])
        self.assertEqual(state['error_code'], 'REVIEW_TRANSPORT_INVALID')

    def test_ttl_expires_without_reusing_stale_order_state(self):
        before = self.load()
        self.now += 11
        after = self.session.snapshot()
        self.assertEqual(after['orders'], [])
        self.assertGreater(after['revision'], before['revision'])
        self.assertEqual(after['expires_in_seconds'], 0)

    def test_independent_sessions_and_returned_state_are_isolated(self):
        before = self.load()
        other = DOIReviewSession(clock=lambda: self.now, ttl_seconds=10)
        self.assertEqual(other.snapshot()['orders'], [])
        before['orders'].clear()
        self.assertEqual(len(self.session.snapshot()['orders']), 1)

    def test_close_discards_orders(self):
        self.load()
        self.session.close()
        self.assertEqual(self.session.snapshot()['orders'], [])

    def test_failed_reload_replaces_old_state_with_truthful_empty_error(self):
        self.load()
        self.session.load('x' * (MAX_CSV_BYTES + 1), '', self.session.snapshot()['revision'])
        state = self.session.snapshot()
        self.assertEqual(state['status'], 'error')
        self.assertEqual(state['error_code'], 'REVIEW_CSV_TOO_LARGE')
        self.assertEqual(state['orders'], [])
        self.assertEqual(state['counts']['summary_records'], 0)

    def test_malformed_headers_orphan_and_overflow_are_closed_holds(self):
        for summaries, lines, code in (
            ([summary()], [line('90000002')], 'ORPHAN_LINE'),
            (
                [
                    summary(
                        captured_at_america_new_york='0001-01-01T00:00:00+23:00',
                        utc_offset='+23:00',
                    )
                ],
                [line()],
                'TIMESTAMP_RANGE_UNSUPPORTED',
            ),
        ):
            state = self.load(summaries, lines)
            self.assertIn(code, json.dumps(state))
            self.assertTrue(all(not o['decision_eligible'] for o in state['orders']))
        a, b = fictional_csvs()
        self.session.load(
            a.replace('order_id,', 'order_id,order_id,', 1), b, self.session.snapshot()['revision']
        )
        self.assertIn('DUPLICATE_HEADER', json.dumps(self.session.snapshot()))

    def test_unknown_boolean_and_unicode_trim_do_not_inflate_role_counts(self):
        state = self.load(
            lines=[
                line(
                    row_type='component', counts_as_purchase='UNKNOWN', parent_line_id='SYN-LINE-1'
                ),
                line(line_identifier='SYN-LINE-2', counts_as_purchase='\u00a0yes\u00a0'),
            ]
        )
        self.assertEqual(state['counts']['purchased_records'], 0)
        self.assertEqual(state['counts']['component_records'], 0)
        self.assertEqual(state['counts']['placeholder_records'], 0)

    def test_at_order_warehouse_and_current_fields_do_not_prove_readiness(self):
        # A real-time snapshot age can contain the stock marker's digits.
        self.session = DOIReviewSession(
            clock=lambda: self.now, ttl_seconds=10, as_of=lambda: '2026-10-05T14:00:00Z'
        )
        state = self.load(
            lines=[
                line(
                    OH_displayed='999',
                    OS_displayed='999',
                    PC_displayed='999',
                    current_stock_icon_exact='IN STOCK',
                )
            ]
        )
        self.assertFalse(state['orders'][0]['evidence_complete'])
        self.assertFalse(state['orders'][0]['decision_eligible'])
        self.assertNotIn('999', json.dumps(state))

    def test_closed_request_parser_rejects_duplicate_keys_and_boolean_revision(self):
        for body, code in (
            (b'{"revision":0,"revision":1}', 'REVIEW_DUPLICATE_JSON_KEY'),
            (b'{"revision":true}', 'REVIEW_REVISION_INVALID'),
        ):
            with self.assertRaises(DOIReviewError) as caught:
                parse_review_request(body, clear=True)
            self.assertEqual(caught.exception.code, code)

    def test_local_structural_hold_is_not_global_batch_quarantine(self):
        state = self.load([summary(active_purchased_rows='2')], [line(), line()])
        self.assertEqual(state['status'], 'quarantined')
        self.assertEqual(state['batch_holds'], [])
        self.assertEqual(state['groups']['coverage_held'], 1)
        self.assertEqual(state['groups']['batch_quarantine'], 0)
        global_state = self.load([summary(stock_eta_exact='=FICTIONAL(1)')])
        self.assertTrue(global_state['batch_holds'])
        self.assertEqual(global_state['groups']['batch_quarantine'], 1)

    def test_malformed_csv_counts_only_parsed_prefix_and_holds_unknown_total(self):
        a, b = fictional_csvs()
        self.session.load(
            a + '"fictional unterminated tail', b, self.session.snapshot()['revision']
        )
        state = self.session.snapshot()
        self.assertEqual(state['counts']['summary_records'], 1)
        self.assertIn('MALFORMED_CSV', state['batch_holds'])
        self.assertEqual(state['groups']['batch_quarantine'], 1)


class ReviewRenderingTests(unittest.TestCase):
    def test_renderer_rejects_malicious_token_and_contains_no_action_or_eval_route(self):
        with self.assertRaises(ValueError):
            render_doi_csv_review_page('SYN-TOKEN-"<>&')
        html = render_doi_csv_review_page('a' * 64)
        if isinstance(html, bytes):
            html = html.decode('utf-8')
        self.assertNotIn('SYN-TOKEN-"<>&', html)
        self.assertNotIn('/evaluate', html)
        self.assertNotIn('/api/v1/orders/', html)
        self.assertNotIn('mailto:', html)
        self.assertIn('doi-csv-review', html)

    def test_js_uses_text_nodes_and_closed_review_routes(self):
        self.assertIn('textContent', DOI_CSV_REVIEW_JS)
        self.assertNotIn('innerHTML', DOI_CSV_REVIEW_JS)
        self.assertNotIn('/evaluate', DOI_CSV_REVIEW_JS)
        self.assertIn('/api/v1/doi-csv-review/', DOI_CSV_REVIEW_JS)
        self.assertIn('AbortController', DOI_CSV_REVIEW_JS)
        self.assertIn('pageshow', DOI_CSV_REVIEW_JS)
        self.assertIn('pagehide', DOI_CSV_REVIEW_JS)
        self.assertIn('epoch', DOI_CSV_REVIEW_JS)

    def test_frontend_labels_parsed_scope_and_keeps_stale_flow_guards(self):
        html = render_doi_csv_review_page('a' * 64).decode('utf-8')
        combined = html + DOI_CSV_REVIEW_JS
        self.assertTrue(
            'Parsed summary' in combined, 'Summary count must disclose parsed-prefix scope'
        )
        self.assertTrue('Parsed line' in combined, 'Line count must disclose parsed-prefix scope')
        self.assertIn('doi-new-pair', html)
        self.assertIn('doi-clear', html)
        self.assertIn('pagehide', DOI_CSV_REVIEW_JS)
        self.assertIn('pageshow', DOI_CSV_REVIEW_JS)
        self.assertIn('AbortController', DOI_CSV_REVIEW_JS)
        self.assertNotIn('group.value === "batch_quarantine" && current.status', DOI_CSV_REVIEW_JS)


class ReviewHTTPTests(unittest.TestCase):
    def setUp(self):
        from synthetic_sales_assist.portal.server import PortalHTTPServer, PortalServerConfig

        self.server = PortalHTTPServer(
            None,
            PortalServerConfig('127.0.0.1', 0),
            csrf_token='a' * 64,
            shutdown_token='b' * 64,
            doi_csv_review_only=True,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]
        self.origin = f'http://127.0.0.1:{self.port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def request(self, method, path, body=None, headers=None):
        defaults = {'Host': f'127.0.0.1:{self.port}'}
        if method == 'POST':
            defaults.update(
                {
                    'Origin': self.origin,
                    'X-SSA-CSRF-Token': 'a' * 64,
                    'Content-Type': 'application/json',
                }
            )
        defaults.update(headers or {})
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=3)
        try:
            connection.request(method, path, body=body, headers=defaults)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_review_only_http_load_clear_and_security_headers(self):
        status, headers, body = self.request('GET', '/doi-csv-review')
        self.assertEqual(status, 200)
        self.assertIn('no-store', headers.get('Cache-Control', ''))
        self.assertEqual(headers.get('X-Content-Type-Options'), 'nosniff')
        self.assertIn('Content-Security-Policy', headers)
        a, b = fictional_csvs()
        status, _, body = self.request(
            'POST',
            '/api/v1/doi-csv-review/load',
            json.dumps({'revision': 0, 'summary_csv': a, 'lines_csv': b}),
        )
        self.assertEqual(status, 200)
        loaded = json.loads(body)
        self.assertEqual(loaded['counts']['orders'], 1)
        status, _, body = self.request(
            'POST', '/api/v1/doi-csv-review/clear', json.dumps({'revision': loaded['revision']})
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['orders'], [])

    def test_unauthorized_requests_preserve_loaded_session(self):
        a, b = fictional_csvs()
        self.server.doi_review_session.load(a, b, 0)
        before = self.server.doi_review_session.snapshot()
        for headers in (
            {'X-SSA-CSRF-Token': 'c' * 64},
            {'Origin': 'https' + '://example.test'},
            {'Host': 'example.test'},
        ):
            status, _, _ = self.request(
                'POST',
                '/api/v1/doi-csv-review/clear',
                json.dumps({'revision': before['revision']}),
                headers,
            )
            self.assertGreaterEqual(status, 400)
            after = self.server.doi_review_session.snapshot()
            self.assertEqual(after['revision'], before['revision'])
            self.assertEqual(after['orders'], before['orders'])

    def test_review_only_denies_legacy_evaluation_and_untrusted_revision_preserves_state(self):
        status, _, _ = self.request('GET', '/api/v1/scenarios')
        self.assertGreaterEqual(status, 400)
        a, b = fictional_csvs()
        self.server.doi_review_session.load(a, b, 0)
        before = self.server.doi_review_session.snapshot()
        status, _, _ = self.request(
            'POST', '/api/v1/doi-csv-review/load', '{"revision":1,"revision":1}'
        )
        self.assertGreaterEqual(status, 400)
        after = self.server.doi_review_session.snapshot()
        self.assertEqual(after['revision'], before['revision'])
        self.assertEqual(after['orders'], before['orders'])

    def test_stale_invalid_load_and_clear_requests_preserve_newer_state(self):
        a, b = fictional_csvs()
        self.server.doi_review_session.load(a, b, 0)
        before = self.server.doi_review_session.snapshot()
        bodies = (
            ('load', {'revision': 0, 'summary_csv': False, 'lines_csv': ''}),
            ('load', {'revision': 0, 'summary_csv': ''}),
            (
                'load',
                {'revision': 0, 'summary_csv': '', 'lines_csv': '', 'unexpected': 'fictional'},
            ),
            ('clear', {'revision': 0, 'unexpected': 'fictional'}),
        )
        for route, request in bodies:
            with self.subTest(route=route, members=tuple(request)):
                status, _, _ = self.request(
                    'POST', '/api/v1/doi-csv-review/' + route, json.dumps(request)
                )
                self.assertEqual(status, 409)
                after = self.server.doi_review_session.snapshot()
                self.assertEqual(after['revision'], before['revision'])
                self.assertEqual(after['orders'], before['orders'])

    def test_missing_duplicate_or_undecodable_revision_never_mutates_state(self):
        a, b = fictional_csvs()
        self.server.doi_review_session.load(a, b, 0)
        before = self.server.doi_review_session.snapshot()
        bodies = (
            b'{}',
            b'{"revision":1,"revision":1}',
            b'{"revision":false}',
            b'{"revision":"1"}',
            b'{"revision":1',
            b'\xff',
        )
        for route in ('load', 'clear'):
            for body in bodies:
                with self.subTest(route=route, body_kind=body[:18]):
                    status, _, _ = self.request('POST', '/api/v1/doi-csv-review/' + route, body)
                    self.assertGreaterEqual(status, 400)
                    after = self.server.doi_review_session.snapshot()
                    self.assertEqual(after['revision'], before['revision'])
                    self.assertEqual(after['orders'], before['orders'])

    def test_current_revision_invalid_body_may_clear_prior_state(self):
        a, b = fictional_csvs()
        before = self.server.doi_review_session.load(a, b, 0)
        status, _, _ = self.request(
            'POST',
            '/api/v1/doi-csv-review/load',
            json.dumps({'revision': before['revision'], 'summary_csv': False, 'lines_csv': ''}),
        )
        self.assertGreaterEqual(status, 400)
        after = self.server.doi_review_session.snapshot()
        self.assertEqual(after['orders'], [])
        self.assertGreater(after['revision'], before['revision'])


if __name__ == '__main__':
    unittest.main()
