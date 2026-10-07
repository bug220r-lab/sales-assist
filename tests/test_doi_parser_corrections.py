"""Independent bounded parser regressions; all records are generated fiction."""
import unittest
from tests.test_csv_staging_independent import summary,line,stage,codes,csv_text
from doi_csv_staging import SUMMARY_HEADERS,LINE_HEADERS
from doi_csv_staging.review import DOIReviewSession


class ParserCorrectionTests(unittest.TestCase):
    def test_strict_negative_os_integer_decimal_ascii_edges_preserves_raw(self):
        for value in ('-3','-0','-17.25',' \t-3\r\n','-0.125'):
            with self.subTest(fictional_os_shape=value):
                batch=stage(lines=[line(OS_displayed=value)])
                self.assertNotIn('CSV_FORMULA_RISK',codes(batch))
                self.assertEqual(dict(batch.line_occurrences[0].raw_fields)['OS_displayed'],value)
                self.assertFalse(batch.orders[0].decision_eligible)

    def test_os_anchored_ascii_grammar_rejects_expressions_and_suffixes(self):
        for value in ('-3+1','-3foo','-3e2','-３','-3\u00a0','- 3','-3 4','-3\x00','-.5','-3.','--3','-3\t4','+3'):
            with self.subTest(fictional_os_shape=value):
                batch=stage(lines=[line(OS_displayed=value)])
                self.assertIn('CSV_FORMULA_RISK',codes(batch))
                self.assertEqual(dict(batch.line_occurrences[0].raw_fields)['OS_displayed'],value)

    def test_unicode_prefix_retains_existing_ascii_trim_scanner_boundary(self):
        value='\u00a0-3'
        batch=stage(lines=[line(OS_displayed=value)])
        self.assertEqual(dict(batch.line_occurrences[0].raw_fields)['OS_displayed'],value)
        self.assertNotIn('CSV_FORMULA_RISK',codes(batch))
        self.assertFalse(batch.orders[0].decision_eligible)

    def test_os_negative_length_boundaries_255_256_257(self):
        for length in (255,256,257):
            value='-'+('3'*(length-1))
            batch=stage(lines=[line(OS_displayed=value)])
            self.assertEqual('CSV_FORMULA_RISK' in codes(batch),length>256)
            self.assertEqual(dict(batch.line_occurrences[0].raw_fields)['OS_displayed'],value)

    def test_negative_values_in_other_fields_remain_quarantined(self):
        for field in ('each_price_displayed','product_name','remaining_quantity','OH_displayed','ordered_quantity_displayed'):
            batch=stage(lines=[line(**{field:'-3'})])
            self.assertIn('CSV_FORMULA_RISK',codes(batch))
            self.assertFalse(batch.orders[0].decision_eligible)

    def test_timezone_offset_exception_remains_field_specific(self):
        batch=stage([summary(utc_offset='-04:00')],[line(OS_displayed='-3')])
        self.assertNotIn('CSV_FORMULA_RISK',codes(batch))
        self.assertNotIn('UTC_OFFSET_MISMATCH',codes(batch))

    def test_total_purchases_includes_service_subset_and_native_aliases(self):
        batch=stage([summary(active_purchased_rows='2',separate_service_rows_displayed='1')],
                    [line(row_type='Purchased merchandise line',physical_or_service='Physical merchandise'),
                     line(row_type='Purchased service/charge line',physical_or_service='Explicit service/charge line',line_identifier='SYN-SERVICE-1')])
        self.assertNotIn('SUMMARY_LINE_COUNT_MISMATCH',codes(batch))
        self.assertTrue(batch.orders[0].visible_coverage_complete)
        self.assertFalse(batch.orders[0].decision_eligible)

    def test_physical_only_total_is_not_accepted_alternate_semantics(self):
        batch=stage([summary(active_purchased_rows='1',separate_service_rows_displayed='1')],
                    [line(),line(physical_or_service='service',line_identifier='SYN-SERVICE-1')])
        self.assertIn('SUMMARY_LINE_COUNT_MISMATCH',codes(batch))
        self.assertFalse(batch.orders[0].visible_coverage_complete)

    def test_zero_service_subset_and_missing_purchase_rows_are_exact(self):
        self.assertTrue(stage().orders[0].visible_coverage_complete)
        for total,service in (('2','0'),('1','1'),('0','0')):
            batch=stage([summary(active_purchased_rows=total,separate_service_rows_displayed=service)],[line()])
            self.assertIn('SUMMARY_LINE_COUNT_MISMATCH',codes(batch))
            self.assertFalse(batch.orders[0].visible_coverage_complete)

    def test_unknown_nature_not_promoted_to_physical_or_service_counts(self):
        batch=stage([summary(active_purchased_rows='1')],[line(physical_or_service='UNKNOWN')])
        self.assertIn('LINE_NATURE_UNKNOWN',codes(batch))
        self.assertFalse(batch.orders[0].visible_coverage_complete)
        session=DOIReviewSession()
        state=session.load(csv_text(SUMMARY_HEADERS,[summary()]),csv_text(LINE_HEADERS,[line(physical_or_service='UNKNOWN')]),0)
        self.assertEqual(state['counts']['purchased_records'],1)
        self.assertEqual(state['counts']['physical_purchased_records'],0)
        self.assertEqual(state['counts']['service_purchased_records'],0)

    def test_service_merchandise_role_contradictions_are_held(self):
        for role,nature in (('Purchased service/charge line','Physical merchandise'),
                            ('Purchased merchandise line','Explicit service/charge line')):
            batch=stage(lines=[line(row_type=role,physical_or_service=nature)])
            self.assertIn('LINE_STRUCTURE_CONFLICT',codes(batch))
            self.assertFalse(batch.orders[0].visible_coverage_complete)
            self.assertFalse(batch.orders[0].decision_eligible)

    def test_component_and_gap_are_nonpurchases_with_service_subset(self):
        component=line(row_type='component',counts_as_purchase='no',line_identifier='SYN-COMP-1',parent_line_id='SYN-LINE-1',component_coverage_complete='yes')
        gap=line(row_type='Component coverage gap - not a merchandise line',counts_as_purchase='no',line_identifier='',parent_line_id='SYN-LINE-1')
        service=line(physical_or_service='service',line_identifier='SYN-SERVICE-1')
        batch=stage([summary(active_purchased_rows='2',separate_service_rows_displayed='1',visible_component_rows='1',component_coverage='yes')],[line(row_type='Purchased kit parent'),service,component,gap])
        self.assertNotIn('SUMMARY_LINE_COUNT_MISMATCH',codes(batch))
        self.assertTrue(batch.orders[0].visible_coverage_complete)
        self.assertFalse(batch.orders[0].decision_eligible)

    def test_review_projection_purchase_total_and_disjoint_nature_counts(self):
        session=DOIReviewSession()
        summaries=[summary(active_purchased_rows='2',separate_service_rows_displayed='1')]
        lines=[line(),line(physical_or_service='service',line_identifier='SYN-SERVICE-1')]
        state=session.load(csv_text(SUMMARY_HEADERS,summaries),csv_text(LINE_HEADERS,lines),0)
        self.assertEqual(state['counts']['purchased_records'],2)
        self.assertEqual(state['counts']['physical_purchased_records'],1)
        self.assertEqual(state['counts']['service_purchased_records'],1)
        self.assertFalse(state['orders'][0]['decision_eligible'])

    def test_structurally_invalid_purchase_rows_not_promoted_to_nature_subsets(self):
        rows=(line(row_type='mystery'),line(row_type='component'),
              line(parent_line_id='SYN-PARENT'),
              line(row_type='Component coverage gap - not a merchandise line'))
        for row in rows:
            with self.subTest(fictional_structure=row['row_type']):
                session=DOIReviewSession()
                state=session.load(csv_text(SUMMARY_HEADERS,[summary()]),csv_text(LINE_HEADERS,[row]),0)
                self.assertEqual(state['counts']['purchased_records'],1)
                self.assertEqual(state['counts']['physical_purchased_records'],0)
                self.assertEqual(state['counts']['service_purchased_records'],0)
                self.assertFalse(state['orders'][0]['visible_coverage_complete'])
                self.assertFalse(state['orders'][0]['decision_eligible'])
                self.assertIn('STRUCTURAL_COVERAGE_INCOMPLETE',state['orders'][0]['holds'])


if __name__=='__main__':unittest.main()
