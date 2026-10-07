"""Synthetic-only split patterns, exact captured totals, and safe ordering."""

import copy
import unittest
from tests.test_csv_staging_independent import summary, line, stage, csv_text
from doi_csv_staging import SUMMARY_HEADERS, LINE_HEADERS
from doi_csv_staging.split_review import (
    classify_split_order,
    parse_order_total,
    split_sort_key,
    validate_split_projection,
)
from doi_csv_staging.review import DOIReviewSession, DOIReviewError, review_response_bytes


def split(summaries=None, lines=None, **kwargs):
    if summaries is None:
        summaries = [summary(active_purchased_rows='2')]
    if lines is None:
        lines = [
            line(current_stock_icon_exact='In Stock'),
            line(line_identifier='SYN-LINE-2', current_stock_icon_exact='Back Ordered'),
        ]
    return classify_split_order(stage(summaries, lines).orders[0], **kwargs)


def total_fields(amount='1234.50', display='$1,234.50', code='USD', symbol='$'):
    return {
        'order_total_numeric': amount,
        'order_total_displayed': display,
        'currency_code': code,
        'currency_symbol_displayed': symbol,
    }


class SplitReviewTests(unittest.TestCase):
    def test_distinct_ready_waiting_physical_lines_only_apparent_candidate(self):
        result = split()
        self.assertEqual(result['status'], 'APPARENT_SPLIT_CANDIDATE')
        self.assertEqual(result['ready_line_ordinals'], [2])
        self.assertEqual(result['waiting_line_ordinals'], [3])
        self.assertFalse(result['quantity_verified'])
        self.assertFalse(result['decision_eligible'])
        self.assertIn('NOT_CONFIRMED_FULL', result['reason_codes'])

    def test_one_conflicting_line_cannot_be_distinct_ready_waiting_pair(self):
        result = split(
            [summary()],
            [line(current_stock_icon_exact='In Stock', product_eta_exact='Back Ordered')],
        )
        self.assertEqual(result['status'], 'INSUFFICIENT_SPLIT_EVIDENCE')
        self.assertEqual(result['ready_line_ordinals'], [])
        self.assertEqual(result['waiting_line_ordinals'], [])
        self.assertIn('STOCK_LABEL_CONFLICT', result['reason_codes'])

    def test_zero_remaining_excluded_unknown_remaining_retains_qualified_candidate(self):
        zero = split(
            lines=[
                line(remaining_quantity='0', current_stock_icon_exact='In Stock'),
                line(line_identifier='SYN-LINE-2', current_stock_icon_exact='Back Ordered'),
            ]
        )
        self.assertNotEqual(zero['status'], 'APPARENT_SPLIT_CANDIDATE')
        self.assertIn('ZERO_REMAINING_EXCLUDED', zero['reason_codes'])
        unknown = split()
        self.assertEqual(unknown['status'], 'APPARENT_SPLIT_CANDIDATE')
        self.assertIn('ACTIVE_QUANTITY_UNVERIFIED', unknown['missing_fact_codes'])

    def test_known_ds_not_used_as_fulfillment_side_unknown_ds_is_qualified(self):
        known = split(
            lines=[
                line(drop_ship='yes', current_stock_icon_exact='In Stock'),
                line(
                    line_identifier='SYN-LINE-2',
                    drop_ship='no',
                    current_stock_icon_exact='Back Ordered',
                ),
            ]
        )
        self.assertNotEqual(known['status'], 'APPARENT_SPLIT_CANDIDATE')
        self.assertIn('KNOWN_DS_EXCLUDED', known['reason_codes'])
        unknown = split()
        self.assertIn('DS_UNVERIFIED', unknown['missing_fact_codes'])

    def test_mixed_order_independent_non_ds_pair_remains_included(self):
        result = split(
            [summary(active_purchased_rows='3')],
            [
                line(drop_ship='yes', current_stock_icon_exact='In Stock'),
                line(
                    line_identifier='SYN-LINE-2',
                    drop_ship='no',
                    current_stock_icon_exact='In Stock',
                ),
                line(line_identifier='SYN-LINE-3', drop_ship='no', current_stock_icon_exact='NLA'),
            ],
        )
        self.assertEqual(result['status'], 'APPARENT_SPLIT_CANDIDATE')
        self.assertEqual(result['ready_line_ordinals'], [3])
        self.assertEqual(result['waiting_line_ordinals'], [4])

    def test_service_rows_never_form_inventory_split_side(self):
        result = split(
            [summary(active_purchased_rows='2', separate_service_rows_displayed='1')],
            [
                line(current_stock_icon_exact='In Stock'),
                line(
                    line_identifier='SYN-SERVICE',
                    physical_or_service='service',
                    current_stock_icon_exact='Back Ordered',
                ),
            ],
        )
        self.assertEqual(result['waiting_line_ordinals'], [])
        self.assertNotEqual(result['status'], 'APPARENT_SPLIT_CANDIDATE')

    def test_components_do_not_double_count_as_ready_or_waiting_purchase(self):
        component = line(
            row_type='component',
            counts_as_purchase='no',
            line_identifier='SYN-COMP',
            parent_line_id='SYN-LINE-1',
            component_coverage_complete='yes',
            component_quantity_required='1',
            current_stock_icon_exact='In Stock',
        )
        result = split(
            [
                summary(
                    active_purchased_rows='2', visible_component_rows='1', component_coverage='yes'
                )
            ],
            [
                line(row_type='Purchased kit parent', current_stock_icon_exact='In Stock'),
                line(line_identifier='SYN-LINE-2', current_stock_icon_exact='Back Ordered'),
                component,
            ],
        )
        self.assertEqual(result['status'], 'APPARENT_SPLIT_CANDIDATE')
        self.assertEqual(result['ready_line_ordinals'], [2])
        self.assertNotIn(4, result['ready_line_ordinals'])

    def test_linked_kit_gap_cannot_exempt_unrelated_incomplete_merchandise(self):
        gap = line(
            row_type='Component coverage gap - not a merchandise line',
            counts_as_purchase='no',
            line_identifier='',
            parent_line_id='SYN-KIT',
            order_capture_complete='no',
        )
        result = split(
            [summary(active_purchased_rows='3', capture_complete='no')],
            [
                line(current_stock_icon_exact='In Stock', order_capture_complete='no'),
                line(
                    line_identifier='SYN-LINE-2',
                    current_stock_icon_exact='Back Ordered',
                    order_capture_complete='no',
                ),
                line(
                    line_identifier='SYN-KIT',
                    row_type='Purchased kit parent',
                    current_stock_icon_exact='In Stock',
                    order_capture_complete='no',
                ),
                gap,
            ],
        )
        self.assertEqual(result['status'], 'CAPTURE_HELD')
        self.assertEqual(result['ready_line_ordinals'], [])
        self.assertEqual(result['waiting_line_ordinals'], [])
        self.assertIn('CAPTURE_COHERENCE_HOLD', result['reason_codes'])
        self.assertIn('KIT_EVIDENCE_UNRESOLVED', result['reason_codes'])
        self.assertIn(4, result['unresolved_line_ordinals'])

    def test_kit_only_gap_without_structured_missing_scope_remains_held(self):
        gap = line(
            row_type='Component coverage gap - not a merchandise line',
            counts_as_purchase='no',
            line_identifier='',
            parent_line_id='SYN-KIT',
            order_capture_complete='no',
        )
        rows = [
            line(current_stock_icon_exact='In Stock'),
            line(line_identifier='SYN-LINE-2', current_stock_icon_exact='Back Ordered'),
            line(
                line_identifier='SYN-KIT',
                row_type='Purchased kit parent',
                current_stock_icon_exact='In Stock',
                order_capture_complete='no',
            ),
            gap,
        ]
        for reason in ('', 'Only kit components are missing; other merchandise is complete'):
            with self.subTest(fictional_missing_reason=reason):
                result = split(
                    [
                        summary(
                            active_purchased_rows='3',
                            capture_complete='no',
                            missing_evidence_reason=reason,
                        )
                    ],
                    rows,
                )
                self.assertEqual(result['status'], 'CAPTURE_HELD')
                self.assertEqual(result['ready_line_ordinals'], [])
                self.assertEqual(result['waiting_line_ordinals'], [])
                self.assertIn('KIT_COMPONENT_SCOPE_UNVERIFIED', result['missing_fact_codes'])

    def test_linked_kit_gap_with_unknown_missing_scope_remains_held(self):
        gap = line(
            row_type='Component coverage gap - not a merchandise line',
            counts_as_purchase='no',
            line_identifier='',
            parent_line_id='SYN-KIT',
            order_capture_complete='no',
        )
        result = split(
            [summary(active_purchased_rows='3', capture_complete='Unknown - not verified')],
            [
                line(current_stock_icon_exact='In Stock', order_capture_complete=''),
                line(
                    line_identifier='SYN-LINE-2',
                    current_stock_icon_exact='Back Ordered',
                    order_capture_complete='',
                ),
                line(
                    line_identifier='SYN-KIT',
                    row_type='Purchased kit parent',
                    current_stock_icon_exact='In Stock',
                    order_capture_complete='no',
                ),
                gap,
            ],
        )
        self.assertEqual(result['status'], 'CAPTURE_HELD')
        self.assertEqual(result['ready_line_ordinals'], [])
        self.assertEqual(result['waiting_line_ordinals'], [])
        self.assertFalse(result['quantity_verified'])
        self.assertFalse(result['decision_eligible'])

    def test_coherence_global_and_terminal_holds_cannot_offer_candidate(self):
        global_result = split(global_input_held=True)
        self.assertEqual(global_result['status'], 'CAPTURE_HELD')
        mismatch = split(
            lines=[
                line(current_stock_icon_exact='In Stock', queue_position='9'),
                line(line_identifier='SYN-LINE-2', current_stock_icon_exact='Back Ordered'),
            ]
        )
        self.assertEqual(mismatch['status'], 'CAPTURE_HELD')
        terminal = split([summary(active_purchased_rows='2', order_status='Shipped')])
        self.assertEqual(terminal['status'], 'CAPTURE_HELD')
        self.assertFalse(terminal['decision_eligible'])
        generic_incomplete = split([summary(active_purchased_rows='2', capture_complete='no')])
        self.assertEqual(generic_incomplete['status'], 'CAPTURE_HELD')

    def test_invalid_date_label_does_not_promise_waiting_ship_date(self):
        result = split(
            lines=[
                line(current_stock_icon_exact='In Stock'),
                line(
                    line_identifier='SYN-LINE-2', current_stock_icon_exact='Ships on Feb 30, 2026'
                ),
            ]
        )
        self.assertEqual(result['waiting_line_ordinals'], [])
        self.assertNotEqual(result['status'], 'APPARENT_SPLIT_CANDIDATE')

    def test_exact_total_numeric_display_currency_reconciled(self):
        parsed = parse_order_total(total_fields())
        self.assertEqual(
            parsed,
            {
                'amount': '1234.5',
                'displayed': '$1,234.50',
                'currency_code': 'USD',
                'currency_symbol': '$',
                'status': 'VALID',
            },
        )
        zero = parse_order_total(total_fields('0.00', '$0.00'))
        self.assertEqual(zero['amount'], '0')

    def test_unknown_currency_preserved_without_symbol_inference(self):
        parsed = parse_order_total(total_fields(code='Unknown - not displayed'))
        self.assertEqual(parsed['status'], 'VALID')
        self.assertIsNone(parsed['currency_code'])
        self.assertEqual(parsed['currency_symbol'], '$')

    def test_closed_unicode_currency_symbols_preserved_without_code_inference(self):
        for symbol in ('€', '£', '¥'):
            parsed = parse_order_total(
                total_fields('1', symbol + '1', 'Unknown - not displayed', symbol)
            )
            self.assertEqual(parsed['status'], 'VALID')
            self.assertEqual(parsed['currency_symbol'], symbol)
            self.assertIsNone(parsed['currency_code'])

    def test_mismatch_invalid_unknown_totals_cannot_create_amount(self):
        self.assertEqual(parse_order_total(total_fields('5', '$6'))['status'], 'MISMATCH')
        self.assertEqual(parse_order_total({})['status'], 'UNKNOWN')
        for amount in ('NaN', '1e3', '-1', '+1', '1,000', '1.0000001', '9' * 19):
            result = parse_order_total(total_fields(amount, '$1'))
            self.assertEqual(result['status'], 'INVALID')
            self.assertIsNone(result['amount'])

    def test_malformed_display_grouping_and_injection_redacted(self):
        for display in ('$12,34.50', '<script>SYN-PRIVATE</script>', '@ raw-private-token', '=1+2'):
            result = parse_order_total(total_fields(display=display))
            self.assertEqual(result['status'], 'INVALID')
            self.assertIsNone(result['displayed'])
            self.assertIsNone(result['amount'])

    def test_total_parser_ignores_subtotal_balance_and_commission_fields(self):
        parsed = parse_order_total({'subtotal': '100', 'balance': '99', 'commission': '10'})
        self.assertEqual(parsed['status'], 'UNKNOWN')
        self.assertIsNone(parsed['amount'])

    def test_exact_decimal_sort_status_first_then_full_total_descending(self):
        lower = split(
            [
                summary(
                    active_purchased_rows='2',
                    **total_fields('9007199254740992.000001', '$9007199254740992.000001')
                )
            ]
        )
        higher = split(
            [
                summary(
                    active_purchased_rows='2',
                    **total_fields('9007199254740992.000002', '$9007199254740992.000002')
                )
            ]
        )
        self.assertLess(split_sort_key(higher), split_sort_key(lower))
        held = split(
            [
                summary(
                    active_purchased_rows='2',
                    **total_fields('999999999999999999', '$999999999999999999')
                )
            ],
            global_input_held=True,
        )
        self.assertLess(split_sort_key(lower), split_sort_key(held))

    def test_missing_invalid_total_last_with_same_split_status(self):
        valid = split([summary(active_purchased_rows='2', **total_fields('1', '$1'))])
        unknown = split()
        invalid = split([summary(active_purchased_rows='2', **total_fields('oops', '$1'))])
        self.assertLess(split_sort_key(valid), split_sort_key(unknown))
        self.assertLess(split_sort_key(valid), split_sort_key(invalid))

    def test_cross_currency_sort_nominal_only_no_aggregation_or_conversion(self):
        usd = split([summary(active_purchased_rows='2', **total_fields('1', '$1', 'USD'))])
        cad = split([summary(active_purchased_rows='2', **total_fields('1', '$1', 'CAD'))])
        self.assertEqual(split_sort_key(usd), split_sort_key(cad))
        self.assertEqual(usd['total']['currency_code'], 'USD')
        self.assertEqual(cad['total']['currency_code'], 'CAD')

    def test_projection_rejects_confirmed_quantity_and_overlapping_ordinals(self):
        valid = split()
        for field, value in (
            ('status', 'CONFIRMED_SPLIT_CRITERIA'),
            ('quantity_verified', True),
            ('decision_eligible', True),
        ):
            forged = copy.deepcopy(valid)
            forged[field] = value
            with self.assertRaises(ValueError):
                validate_split_projection(forged)
        forged = copy.deepcopy(valid)
        forged['waiting_line_ordinals'] = [2]
        with self.assertRaises(ValueError):
            validate_split_projection(forged)
        forged = copy.deepcopy(valid)
        forged['total'] = parse_order_total(total_fields('1', '$1'))
        forged['total']['amount'] = '2'
        with self.assertRaises(ValueError):
            validate_split_projection(forged)
        for index, field, value in (
            (0, 'ds', 'YES'),
            (0, 'current_stock', 'Back Ordered'),
            (1, 'current_stock', 'In Stock'),
        ):
            forged = copy.deepcopy(valid)
            forged['line_items'][index][field] = value
            with self.assertRaises(ValueError):
                validate_split_projection(forged)
        for reason in ('CAPTURE_COHERENCE_HOLD', 'TERMINAL_ORDER_OBSERVED'):
            forged = copy.deepcopy(valid)
            forged['reason_codes'].append(reason)
            with self.assertRaises(ValueError):
                validate_split_projection(forged)

    def test_session_sort_full_total_then_source_ordinal_is_deterministic(self):
        summaries = []
        lines = []
        for order, amount, status in (
            ('90000001', '1', 'pair'),
            ('90000002', '9', 'pair'),
            ('90000003', '9', 'pair'),
            ('90000004', '999', 'none'),
        ):
            summaries.append(
                summary(order, active_purchased_rows='2', **total_fields(amount, '$' + amount))
            )
            lines.extend(
                [
                    line(order, current_stock_icon_exact='In Stock'),
                    line(
                        order,
                        line_identifier='SYN-LINE-2',
                        current_stock_icon_exact='Back Ordered' if status == 'pair' else 'In Stock',
                    ),
                ]
            )
        session = DOIReviewSession(as_of=lambda: '2026-10-05T14:00:00Z')
        state = session.load(csv_text(SUMMARY_HEADERS, summaries), csv_text(LINE_HEADERS, lines), 0)
        self.assertEqual(
            [o['order_id'] for o in state['orders']],
            ['90000004', '90000002', '90000003', '90000001'],
        )
        self.assertEqual(state['split_review']['confirmed_split_count'], 0)
        self.assertEqual(state['split_review']['decision_eligible_count'], 0)

    def test_minimized_line_items_no_private_rawtext_and_side_ordinals_subsets(self):
        private = 'SYN-PRIVATE <script>raw-private-token</script> @'
        result = split(
            lines=[
                line(
                    es_number='ES#000123', product_name=private, current_stock_icon_exact='In Stock'
                ),
                line(
                    line_identifier='SYN-LINE-2',
                    es_number=private,
                    current_stock_icon_exact='Back Ordered',
                ),
            ]
        )
        items = result['line_items']
        self.assertEqual({item['record_ordinal'] for item in items}, {2, 3})
        self.assertEqual(items[0]['es_number'], '123')
        self.assertIsNone(items[1]['es_number'])
        for item in items:
            self.assertEqual(set(item), {'record_ordinal', 'es_number', 'current_stock', 'ds'})
        for key in ('ready_line_ordinals', 'waiting_line_ordinals', 'unresolved_line_ordinals'):
            self.assertTrue(set(result[key]) <= {item['record_ordinal'] for item in items})
        self.assertNotIn(private, str(result))

    def test_closed_response_rejects_split_side_outside_minimized_line_items(self):
        session = DOIReviewSession(as_of=lambda: '2026-10-05T14:00:00Z')
        state = session.load(
            csv_text(SUMMARY_HEADERS, [summary(active_purchased_rows='2')]),
            csv_text(
                LINE_HEADERS,
                [
                    line(current_stock_icon_exact='In Stock'),
                    line(line_identifier='SYN-LINE-2', current_stock_icon_exact='Back Ordered'),
                ],
            ),
            0,
        )
        state['orders'][0]['split']['ready_line_ordinals'] = [999]
        with self.assertRaises(DOIReviewError):
            review_response_bytes(state)
        state['orders'][0]['split']['ready_line_ordinals'] = [2]
        state['orders'][0]['split']['line_items'][1]['current_stock'] = 'Ships on Oct 4, 2026'
        with self.assertRaises(DOIReviewError):
            review_response_bytes(state)

    def test_dated_waiting_labels_1999_and_before_capture_not_promises(self):
        for label in ('Ships on Oct 20, 1999', 'Ships on Oct 4, 2026'):
            result = split(
                lines=[
                    line(current_stock_icon_exact='In Stock'),
                    line(line_identifier='SYN-LINE-2', current_stock_icon_exact=label),
                ]
            )
            self.assertEqual(result['waiting_line_ordinals'], [])
            self.assertNotEqual(result['status'], 'APPARENT_SPLIT_CANDIDATE')

    def test_explicit_as_of_future_capture_held_without_implicit_age_rule(self):
        future = split(as_of='2026-10-05T13:59:59Z')
        self.assertEqual(future['status'], 'CAPTURE_HELD')
        self.assertEqual(future['ready_line_ordinals'], [])
        self.assertEqual(future['waiting_line_ordinals'], [])
        older = split(as_of='2026-10-07T14:00:00Z')
        self.assertEqual(older['status'], 'APPARENT_SPLIT_CANDIDATE')
        self.assertFalse(older['decision_eligible'])

    def test_split_renderer_integrates_full_navigation_and_keeps_review_only_option(self):
        from synthetic_sales_assist.portal.doi_csv_review_ui import render_doi_csv_review_page

        full = render_doi_csv_review_page('a' * 64, review_only=False).decode('utf-8')
        isolated = render_doi_csv_review_page('a' * 64, review_only=True).decode('utf-8')
        self.assertIn('href="/overview"', full)
        self.assertIn('href="/sales-credit"', full)
        self.assertIn('href="/doi"', full)
        self.assertNotIn('href="/overview"', isolated)
        self.assertIn('Split-review worklist', full)
        self.assertNotIn('/evaluate', full)


if __name__ == '__main__':
    unittest.main()
