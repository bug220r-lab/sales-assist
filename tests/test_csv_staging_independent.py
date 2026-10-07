"""All identifiers and records in this module are generated fictional fixtures.

90000001/90000002 are fabricated order IDs, never copied from owner inputs.
"""
import csv
import io
import unittest
from dataclasses import FrozenInstanceError

from doi_csv_staging import SUMMARY_HEADERS, LINE_HEADERS, stage_capture_csvs

STAMP = '2026-10-05T10:00:00-04:00'

def summary(order='90000001', **changes):
    row = dict.fromkeys(SUMMARY_HEADERS, '')
    row.update(order_id=order, displayed_order_id=order, order_id_matches_queue='yes',
               doi_review_assignment='Jude', doi_source_assignment_conflict='no',
               captured_at_america_new_york=STAMP, timezone='America/New_York',
               utc_offset='-04:00', active_purchased_rows='1',
               separate_service_rows_displayed='0', visible_component_rows='0',
               purchased_line_coverage_complete='yes', capture_complete='yes',
               snapshot_consistency_verified='yes', customer_info_email='fictional@example.test',
               displayed_sales_credit_field='ECS Sales Rep', displayed_sales_credit_value='jlewis', pagination_controls_displayed='no',
               queue_position='1',queue_sheet_row='7',original_source_rows='7',
               queue_source_url='http://127.0.0.1/SYN-queue',order_admin_url='http://127.0.0.1/SYN-order')
    row.update(changes)
    return row

def line(order='90000001', **changes):
    row = dict.fromkeys(LINE_HEADERS, '')
    row.update(order_id=order, row_type='purchased', counts_as_purchase='yes',
               line_identifier='SYN-LINE-1', sku='SYN-SKU-1', physical_or_service='physical',
               captured_at_america_new_york=STAMP, line_coverage_complete='yes',
               order_capture_complete='yes',queue_position='1',queue_sheet_row='7',
               original_source_rows='7',queue_source_url='http://127.0.0.1/SYN-queue',
               order_admin_url='http://127.0.0.1/SYN-order')
    row.update(changes)
    return row

def csv_text(headers, rows):
    stream = io.StringIO(newline='')
    writer = csv.writer(stream)
    writer.writerow(headers)
    writer.writerows([[r.get(h, '') for h in headers] for r in rows])
    return stream.getvalue()

def stage(summaries=None, lines=None):
    return stage_capture_csvs(csv_text(SUMMARY_HEADERS, summaries if summaries is not None else [summary()]),
                              csv_text(LINE_HEADERS, lines if lines is not None else [line()]))

def codes(batch):
    return {i.code for i in batch.issues}


class IndependentStagingTests(unittest.TestCase):
    def test_preserves_raw_provenance_and_normalizes_leading_zeros(self):
        batch = stage([summary(' \t00090000001 ', original_source_rows='7;9', source_occurrences='2')])
        occurrence = batch.summary_occurrences[0]
        self.assertEqual(occurrence.raw_order_id, ' \t00090000001 ')
        self.assertEqual(occurrence.canonical_order_id, '90000001')
        self.assertEqual(dict(occurrence.raw_fields)['original_source_rows'], '7;9')
        self.assertEqual(occurrence.row_number, 2)
        self.assertEqual(occurrence.physical_line_start, 2)
        self.assertIsInstance(occurrence.raw_cells, tuple)
        with self.assertRaises(FrozenInstanceError):
            occurrence.raw_order_id = 'changed'

    def test_review_assignment_is_distinct_from_customer_web_sales_credit(self):
        order = stage([summary(displayed_sales_credit_value='Customer / Web')]).orders[0]
        self.assertEqual(dict(order.review_projection)['review_assignment'], 'Jude')
        self.assertTrue(dict(order.review_projection)['review_included'])
        self.assertNotIn('REVIEW_ASSIGNMENT_UNVERIFIED', {i.code for i in order.issues})
        self.assertFalse(order.decision_eligible)
        self.assertNotIn('customer_info_email', dict(order.review_projection))

    def test_complete_visible_evidence_never_authorizes_decision(self):
        order = stage().orders[0]
        self.assertTrue(order.visible_coverage_complete)
        self.assertFalse(order.evidence_complete)
        self.assertFalse(order.decision_eligible)
        self.assertIn('PRODUCTION_EVALUATION_NOT_PERFORMED', order.holds)

    def test_twenty_nine_purchases_plus_placeholder_retains_thirty_occurrences(self):
        lines = [line(line_identifier=f'SYN-LINE-{i}', sku=f'SYN-SKU-{i}') for i in range(1,30)]
        lines.append(line(row_type='placeholder', counts_as_purchase='no', line_identifier='',
                          parent_line_id='SYN-LINE-1', missing_evidence_reason='not visible'))
        batch = stage([summary(active_purchased_rows='29')], lines)
        self.assertEqual(len(batch.line_occurrences), 30)
        self.assertNotIn('SUMMARY_LINE_COUNT_MISMATCH', codes(batch))
        self.assertNotIn('MISSING_LINE_ID', codes(batch))
        self.assertIn('VISIBLE_COVERAGE_GAP', codes(batch))
        self.assertTrue(batch.orders[0].visible_coverage_complete)

    def test_kit_name_does_not_infer_component_inventory(self):
        order = stage(lines=[line(product_name='SYN fictional kit assembly')]).orders[0]
        self.assertTrue(order.visible_coverage_complete)
        self.assertEqual(len(order.line_occurrences), 1)
        self.assertFalse(order.decision_eligible)

    def test_explicit_components_do_not_add_purchases_services_are_total_subset(self):
        component=line(row_type='component', counts_as_purchase='no', line_identifier='SYN-COMP-1',
                       parent_line_id='SYN-LINE-1', component_coverage_complete='yes')
        service=line(line_identifier='SYN-SERVICE-1', physical_or_service='service')
        batch=stage([summary(active_purchased_rows='2',visible_component_rows='1', separate_service_rows_displayed='1', component_coverage='yes')], [line(),component,service])
        self.assertNotIn('SUMMARY_LINE_COUNT_MISMATCH', codes(batch))
        self.assertTrue(batch.orders[0].visible_coverage_complete)

    def test_component_parent_cannot_join_another_order(self):
        component=line(row_type='component',counts_as_purchase='no',line_identifier='SYN-COMP-1',parent_line_id='SYN-OTHER',component_coverage_complete='yes')
        batch=stage([summary(visible_component_rows='1',component_coverage='yes'),summary('90000002')],
                    [line(),component,line('90000002',line_identifier='SYN-OTHER')])
        self.assertIn('INVALID_COMPONENT_PARENT', codes(batch))

    def test_invalid_positive_numeric_ids_are_retained_without_join(self):
        for invalid in ('','0','-1','9e7','90000001.0','９００００００１','SYN-ORDER-1','900 00001'):
            with self.subTest(fictional_invalid_id=invalid):
                batch=stage([summary(invalid)],[])
                self.assertIn('INVALID_ORDER_ID',codes(batch))
                self.assertEqual(len(batch.summary_occurrences),1)
                self.assertIsNone(batch.summary_occurrences[0].canonical_order_id)

    def test_duplicate_and_conflicting_summary_occurrences_survive(self):
        for second,expected in ((summary(),'DUPLICATE_SUMMARY'),(summary(order_total_numeric='17'),'CONFLICTING_SUMMARY')):
            batch=stage([summary(),second])
            self.assertEqual(len(batch.summary_occurrences),2)
            self.assertEqual(len(batch.orders[0].summary_occurrences),2)
            self.assertIn(expected,codes(batch))
            self.assertFalse(batch.orders[0].evidence_complete)

    def test_duplicate_and_conflicting_line_ids_survive(self):
        batch=stage([summary(active_purchased_rows='2')],[line(),line(sku='SYN-SKU-DIFFERENT')])
        self.assertEqual(len(batch.line_occurrences),2)
        self.assertTrue({'DUPLICATE_LINE_ID','CONFLICTING_LINE'} <= codes(batch))

    def test_orphan_order_lines_and_missing_summary_remain_held(self):
        batch=stage(lines=[line('90000002')])
        self.assertTrue({'ORPHAN_LINE','MISSING_SUMMARY','MISSING_LINES'} <= codes(batch))
        self.assertEqual(len(batch.orders),2)
        self.assertTrue(all(not order.decision_eligible for order in batch.orders))

    def test_duplicate_header_and_missing_column_hold_projection(self):
        for headers,expected in ((SUMMARY_HEADERS+('order_id',),'DUPLICATE_HEADER'),(SUMMARY_HEADERS[1:],'MISSING_COLUMN')):
            batch=stage_capture_csvs(csv_text(headers,[summary()]),csv_text(LINE_HEADERS,[line()]))
            self.assertIn(expected,codes(batch))
            self.assertTrue(all(not dict(o.review_projection)['safe_projection_eligible'] for o in batch.orders))

    def test_row_width_and_malformed_quotes_are_rejected(self):
        good=csv_text(SUMMARY_HEADERS,[summary()])
        for text in (good+'short,row\r\n',good+'"unterminated'):
            batch=stage_capture_csvs(text,csv_text(LINE_HEADERS,[line()]))
            self.assertTrue({'MALFORMED_ROW_WIDTH','MALFORMED_CSV'} & codes(batch))
            self.assertTrue(all(not o.evidence_complete for o in batch.orders))

    def test_semantically_same_timestamp_offset_is_coherent(self):
        batch=stage(lines=[line(captured_at_america_new_york='2026-10-05T14:00:00Z')])
        self.assertNotIn('TIMESTAMP_MISMATCH',codes(batch))
        self.assertFalse(batch.orders[0].evidence_complete)

    def test_naive_missing_and_incoherent_timestamps_hold_evidence(self):
        for value,expected in (('','TIMESTAMP_INVALID_OR_NAIVE'),('2026-10-05T10:00:00','TIMESTAMP_INVALID_OR_NAIVE'),('2026-10-05T10:01:00-04:00','TIMESTAMP_MISMATCH')):
            with self.subTest(timestamp_kind=expected):
                batch=stage(lines=[line(captured_at_america_new_york=value)])
                self.assertIn(expected,codes(batch))
                self.assertFalse(batch.orders[0].evidence_complete)

    def test_timezone_and_declared_offset_need_coherence(self):
        self.assertIn('TIMEZONE_MISMATCH',codes(stage([summary(timezone='UTC')])))
        self.assertIn('UTC_OFFSET_MISMATCH',codes(stage([summary(utc_offset='-05:00')])))

    def test_formula_prefixes_preserved_but_global_quarantined(self):
        for value in ('=1+1',' +SUM(1,2)','-1','@fictional'):
            with self.subTest(formula_prefix=value[:1]):
                batch=stage([summary(stock_eta_exact=value)])
                self.assertEqual(dict(batch.summary_occurrences[0].raw_fields)['stock_eta_exact'],value)
                self.assertIn('CSV_FORMULA_RISK',codes(batch))
                self.assertIn('GLOBAL_INPUT_HOLD',batch.orders[0].holds)
                self.assertFalse(dict(batch.orders[0].review_projection)['safe_projection_eligible'])

    def test_unknown_quantity_ds_and_currency_are_not_zero_or_false(self):
        for unknown in ('','UNKNOWN','N/A','unknown'):
            with self.subTest(unknown_sentinel=unknown):
                batch=stage([summary(currency_code=unknown)], [line(remaining_quantity=unknown,drop_ship=unknown)])
                tags={t.field:t for t in batch.orders[0].tags}
                for field in ('currency','line:2:remaining_quantity','line:2:drop_ship','readiness'):
                    self.assertEqual(tags[field].state,'UNKNOWN')
                    self.assertIsNone(tags[field].value)
                self.assertEqual(dict(batch.line_occurrences[0].raw_fields)['remaining_quantity'],unknown)

    def test_negative_quantity_remains_unknown_and_quarantined(self):
        batch=stage(lines=[line(remaining_quantity='-3')])
        tag=next(t for t in batch.orders[0].tags if t.field=='line:2:remaining_quantity')
        self.assertEqual(tag.state,'UNKNOWN')
        self.assertIn('CSV_FORMULA_RISK',codes(batch))

    def test_mixed_ds_is_included_for_review_without_evaluation(self):
        order=stage([summary(active_purchased_rows='2')],[line(drop_ship='yes'),line(line_identifier='SYN-LINE-2',drop_ship='no')]).orders[0]
        self.assertTrue(dict(order.review_projection)['review_included'])
        self.assertFalse(order.decision_eligible)
        self.assertNotIn('DS_SEPARATION',order.holds)
        self.assertFalse(hasattr(order,'evaluation'))
        self.assertFalse(hasattr(order,'action_export'))

    def test_multiline_raw_field_preserves_logical_and_physical_provenance(self):
        batch=stage([summary(snapshot_change_note='fictional line one\nfictional line two')])
        row=batch.summary_occurrences[0]
        self.assertEqual(row.row_number,2)
        self.assertGreater(row.physical_line_end,row.physical_line_start)
        self.assertEqual(dict(row.raw_fields)['snapshot_change_note'],'fictional line one\nfictional line two')

    def test_exact_placeholder_preserves_purchased_coverage_separate_from_evidence(self):
        placeholder=line(row_type='Component coverage gap - not a merchandise line',counts_as_purchase='no',
                         line_identifier='',parent_line_id='SYN-LINE-1',order_capture_complete='no')
        order=stage([summary(capture_complete='no')],[line(order_capture_complete='no'),placeholder]).orders[0]
        self.assertTrue(order.visible_coverage_complete)
        self.assertFalse(order.evidence_complete)
        self.assertFalse(order.decision_eligible)

    def test_resolved_historical_change_note_is_not_timestamp_incoherence(self):
        batch=stage([summary(snapshot_change_note='Earlier fictional observation reconciled; current snapshot stable')])
        self.assertNotIn('SNAPSHOT_EVIDENCE_INCOMPLETE',codes(batch))
        self.assertNotIn('TIMESTAMP_MISMATCH',codes(batch))

    def test_huge_count_is_fail_closed_without_exception(self):
        batch=stage([summary(active_purchased_rows='9'*5000)])
        self.assertFalse(batch.orders[0].visible_coverage_complete)
        self.assertIn('SUMMARY_LINE_COUNT_MISMATCH',codes(batch))

    def test_timestamp_submicrosecond_difference_is_not_truncated(self):
        batch=stage([summary(captured_at_america_new_york='2026-10-05T10:00:00.1234567-04:00')],
                    [line(captured_at_america_new_york='2026-10-05T10:00:00.1234568-04:00')])
        self.assertIn('TIMESTAMP_MISMATCH',codes(batch))

    def test_malformed_rfc3339_and_offset_do_not_normalize_to_valid(self):
        for invalid in ('20261005T100000-04:00','2026-10-05X10:00:00-04:00','2026-10-05T10:00:00-03:60'):
            batch=stage([summary(captured_at_america_new_york=invalid)])
            self.assertIn('TIMESTAMP_INVALID_OR_NAIVE',codes(batch))

    def test_purchase_role_conflicts_and_self_parent_are_rejected(self):
        for row in (line(row_type='component'),line(row_type='placeholder'),line(parent_line_id='SYN-LINE-1')):
            batch=stage(lines=[row])
            self.assertFalse(batch.orders[0].visible_coverage_complete)
            self.assertFalse(batch.orders[0].decision_eligible)
            self.assertTrue(codes(batch))

    def test_full_raw_csv_retained_privately_even_malformed_tail(self):
        raw_summary=csv_text(SUMMARY_HEADERS,[summary()])+'"fictional unterminated tail'
        raw_lines=csv_text(LINE_HEADERS,[line()])
        batch=stage_capture_csvs(raw_summary,raw_lines)
        self.assertEqual(batch.raw_summary_csv,raw_summary)
        self.assertEqual(batch.raw_lines_csv,raw_lines)
        self.assertNotIn('fictional unterminated tail',repr(batch))
        with self.assertRaises(FrozenInstanceError):
            batch.raw_summary_csv='changed'

    def test_arbitrary_private_sales_credit_text_not_in_projection_or_repr(self):
        private='Fictional Person fictional-private@example.test'
        batch=stage([summary(displayed_sales_credit_value=private)])
        self.assertEqual(dict(batch.summary_occurrences[0].raw_fields)['displayed_sales_credit_value'],private)
        self.assertNotIn(private,str(batch.orders[0].review_projection))
        self.assertNotIn(private,repr(batch))
        self.assertNotIn(private,repr(batch.orders[0]))

    def test_native_merchandise_aliases_and_zero_pagination_preserve_visible_coverage(self):
        order=stage([summary(pagination_controls_displayed='0')],
                    [line(row_type='Purchased merchandise line',physical_or_service='Physical merchandise')]).orders[0]
        self.assertTrue(order.visible_coverage_complete)
        self.assertFalse(order.evidence_complete)
        self.assertFalse(order.decision_eligible)

    def test_ds_coverage_words_are_unknown_not_boolean_evidence(self):
        for value in ('complete','verified','complete verified'):
            with self.subTest(fictional_ds_value=value):
                order=stage(lines=[line(drop_ship=value)]).orders[0]
                ds=next(t for t in order.tags if t.field=='line:2:drop_ship')
                self.assertEqual(ds.state,'UNKNOWN')
                self.assertIsNone(ds.value)

    def test_purchase_flag_coverage_word_is_not_purchase_evidence(self):
        batch=stage(lines=[line(counts_as_purchase='complete')])
        self.assertFalse(batch.orders[0].visible_coverage_complete)
        self.assertFalse(batch.orders[0].decision_eligible)
        self.assertIn('LINE_STRUCTURE_UNRESOLVED',codes(batch))

    def test_unknown_physical_service_role_does_not_count_as_physical(self):
        for role in ('','UNKNOWN','mystery'):
            batch=stage(lines=[line(physical_or_service=role)])
            self.assertFalse(batch.orders[0].visible_coverage_complete)
            self.assertFalse(batch.orders[0].decision_eligible)
            self.assertNotIn('SUMMARY_LINE_COUNT_MISMATCH',codes(batch))
            self.assertIn('LINE_NATURE_UNKNOWN',codes(batch))
            self.assertIn('STRUCTURAL_COVERAGE_INCOMPLETE',codes(batch))

    def test_native_purchased_kit_parent_counts_once_without_bom_inference(self):
        order=stage(lines=[line(row_type='Purchased kit parent',product_name='SYN fictional kit parent')]).orders[0]
        self.assertTrue(order.visible_coverage_complete)
        self.assertEqual(len(order.line_occurrences),1)
        self.assertFalse(order.evidence_complete)
        self.assertFalse(order.decision_eligible)
        self.assertTrue(any(t.field=='readiness' and t.state=='UNKNOWN' for t in order.tags))
        self.assertFalse(hasattr(order,'native_bom'))

    def test_native_unknown_not_displayed_quantity_preserves_raw_unknown(self):
        sentinel='Unknown - not displayed'
        batch=stage(lines=[line(ordered_quantity_displayed=sentinel,fulfilled_quantity=sentinel,
                              remaining_quantity=sentinel,component_quantity_per_parent=sentinel,
                              component_quantity_required=sentinel)])
        self.assertNotIn('INVALID_QUANTITY',codes(batch))
        raw=dict(batch.line_occurrences[0].raw_fields)
        for field in ('ordered_quantity_displayed','fulfilled_quantity','remaining_quantity',
                      'component_quantity_per_parent','component_quantity_required'):
            self.assertEqual(raw[field],sentinel)
        for tag in batch.orders[0].tags:
            if tag.field.startswith('line:2:') and 'quantity' in tag.field:
                self.assertEqual(tag.state,'UNKNOWN')
                self.assertIsNone(tag.value)
        self.assertFalse(batch.orders[0].evidence_complete)

    def test_unresolved_extra_nonpurchase_row_invalidates_visible_coverage(self):
        extra=line(row_type='unresolved fictional role',counts_as_purchase='no',line_identifier='SYN-EXTRA')
        batch=stage(lines=[line(),extra])
        self.assertIn('LINE_STRUCTURE_UNRESOLVED',codes(batch))
        self.assertFalse(batch.orders[0].visible_coverage_complete)

    def test_duplicate_purchased_ids_invalidate_coverage_even_matching_counts(self):
        batch=stage([summary(active_purchased_rows='2')],[line(),line()])
        self.assertIn('DUPLICATE_LINE_ID',codes(batch))
        self.assertNotIn('SUMMARY_LINE_COUNT_MISMATCH',codes(batch))
        self.assertFalse(batch.orders[0].visible_coverage_complete)

    def test_invalid_orphan_and_self_component_parent_invalidate_coverage(self):
        for parent in ('SYN-NONEXISTENT','SYN-COMP-1',''):
            with self.subTest(fictional_parent_kind=parent):
                component=line(row_type='component',counts_as_purchase='no',line_identifier='SYN-COMP-1',
                               parent_line_id=parent,component_coverage_complete='yes')
                batch=stage([summary(visible_component_rows='1',component_coverage='yes')],[line(),component])
                self.assertNotIn('SUMMARY_LINE_COUNT_MISMATCH',codes(batch))
                self.assertTrue({'INVALID_COMPONENT_PARENT','MISSING_COMPONENT_PARENT'} & codes(batch))
                self.assertFalse(batch.orders[0].visible_coverage_complete)

    def test_missing_native_purchased_id_invalidates_visible_coverage(self):
        batch=stage(lines=[line(line_identifier='')])
        self.assertIn('MISSING_LINE_ID',codes(batch))
        self.assertFalse(batch.orders[0].visible_coverage_complete)

    def test_valid_placeholder_and_unknown_facts_preserve_purchase_coverage(self):
        placeholder=line(row_type='Component coverage gap - not a merchandise line',counts_as_purchase='no',
                         line_identifier='',parent_line_id='SYN-LINE-1',order_capture_complete='no')
        purchase=line(remaining_quantity='Unknown - not displayed',drop_ship='UNKNOWN',order_capture_complete='no')
        order=stage([summary(capture_complete='no')],[purchase,placeholder]).orders[0]
        self.assertTrue(order.visible_coverage_complete)
        self.assertFalse(order.evidence_complete)
        self.assertFalse(order.decision_eligible)

    def test_extreme_timestamp_timezone_conversion_is_held_not_raised(self):
        for timestamp,offset in (('0001-01-01T00:00:00+23:00','+23:00'),
                                 ('9999-12-31T23:59:59-23:00','-23:00')):
            with self.subTest(fictional_boundary_year=timestamp[:4]):
                batch=stage([summary(captured_at_america_new_york=timestamp,utc_offset=offset)],
                            [line(captured_at_america_new_york=timestamp)])
                self.assertIn('TIMESTAMP_RANGE_UNSUPPORTED',codes(batch))
                self.assertFalse(batch.orders[0].evidence_complete)
                self.assertFalse(batch.orders[0].decision_eligible)


if __name__=='__main__':
    unittest.main()
