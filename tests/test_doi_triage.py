"""Independent triage evidence tests; only generated fictional captures."""

import json
import copy
import unittest
from unittest.mock import patch
from tests.test_csv_staging_independent import summary, line, stage, csv_text
from doi_csv_staging import SUMMARY_HEADERS, LINE_HEADERS
from doi_csv_staging.triage import (
    classify_order,
    aggregate_triage,
    validate_triage_projection,
    TriageError,
    PRIMARY_BUCKETS,
    TRIAGE_FLAGS,
)
from doi_csv_staging.review import DOIReviewSession, DOIReviewError, review_response_bytes

AS_OF = '2026-10-05T14:00:00Z'


def triage(summaries=None, lines=None, **kwargs):
    return classify_order(
        stage(summaries, lines).orders[0], as_of=kwargs.pop('as_of', AS_OF), **kwargs
    )


class TriageEvidenceTests(unittest.TestCase):
    def test_apparent_stock_is_review_without_readiness_or_action_eligibility(self):
        result = triage(lines=[line(current_stock_icon_exact='In Stock')])
        self.assertIn('APPARENT_STOCK_PROGRESS_REVIEW', result['flags'])
        self.assertFalse(result['readiness_verified'])
        self.assertFalse(result['decision_eligible'])
        self.assertIn('AT_ORDER_STOCK_NOT_CAPTURED', result['missing_fact_codes'])
        self.assertIn('ORDER_DATE_NOT_CAPTURED', result['missing_fact_codes'])

    def test_negative_os_is_opaque_transfer_review_not_shortage(self):
        result = triage(lines=[line(OS_displayed='-3', current_stock_icon_exact='Ships Today')])
        self.assertIn('STOCK_TRANSFER_REVIEW', result['flags'])
        self.assertIn('NEGATIVE_OPAQUE_OS_CURRENT_STOCK', result['reason_codes'])
        self.assertNotIn('shortage', json.dumps(result).lower())
        self.assertFalse(result['readiness_verified'])

    def test_negative_os_without_current_stock_does_not_create_transfer(self):
        result = triage(lines=[line(OS_displayed='-3')])
        self.assertNotIn('STOCK_TRANSFER_REVIEW', result['flags'])

    def test_negative_signed_zero_os_is_not_negative_transfer_signal(self):
        for value in ('-0', '-0.0'):
            result = triage(lines=[line(OS_displayed=value, current_stock_icon_exact='In Stock')])
            self.assertNotIn('NEGATIVE_OPAQUE_OS_CURRENT_STOCK', result['reason_codes'])
            self.assertNotIn('STOCK_TRANSFER_REVIEW', result['flags'])
            self.assertIn('APPARENT_STOCK_PROGRESS_REVIEW', result['flags'])

    def test_different_product_and_current_labels_overlap_transfer_and_delay(self):
        result = triage(
            lines=[line(product_eta_exact='Back Ordered', current_stock_icon_exact='In Stock')]
        )
        self.assertTrue(
            {
                'STOCK_TRANSFER_REVIEW',
                'APPARENT_STOCK_PROGRESS_REVIEW',
                'LEAD_TIME_AVAILABILITY_RESEARCH',
            }
            <= set(result['flags'])
        )
        self.assertEqual(result['primary_bucket'], 'STOCK_TRANSFER_REVIEW')
        self.assertEqual(result['attention_priority'], 2)

    def test_vendor_stock_never_becomes_warehouse_apparent_stock(self):
        result = triage(lines=[line(current_stock_icon_exact='In Stock at Vendor')])
        self.assertNotIn('APPARENT_STOCK_PROGRESS_REVIEW', result['flags'])
        self.assertFalse(result['readiness_verified'])

    def test_vendor_product_current_warehouse_contrast_is_review_signal_only(self):
        result = triage(
            lines=[line(product_eta_exact='Vendor Stock', current_stock_icon_exact='In Stock')]
        )
        self.assertIn('STOCK_TRANSFER_REVIEW', result['flags'])
        self.assertFalse(result['decision_eligible'])

    def test_services_and_invalid_roles_do_not_generate_inventory_candidates(self):
        service = triage(
            [summary(separate_service_rows_displayed='1')],
            [
                line(
                    row_type='Purchased service/charge line',
                    physical_or_service='Explicit service/charge line',
                    current_stock_icon_exact='In Stock',
                    product_eta_exact='Back Ordered',
                )
            ],
        )
        self.assertFalse(
            {
                'STOCK_TRANSFER_REVIEW',
                'APPARENT_STOCK_PROGRESS_REVIEW',
                'LEAD_TIME_AVAILABILITY_RESEARCH',
            }
            & set(service['flags'])
        )
        invalid = triage(lines=[line(row_type='mystery', current_stock_icon_exact='In Stock')])
        self.assertEqual(invalid['primary_bucket'], 'INPUT_QUARANTINED')

    def test_kit_parent_unknown_components_suppresses_apparent_without_missing_bom_claim(self):
        result = triage(
            lines=[line(row_type='Purchased kit parent', current_stock_icon_exact='In Stock')]
        )
        self.assertIn('KIT_COMPONENT_EVIDENCE_UNRESOLVED', result['missing_fact_codes'])
        self.assertNotIn('APPARENT_STOCK_PROGRESS_REVIEW', result['flags'])
        self.assertNotIn('BOM', json.dumps(result))

    def test_kit_component_gap_is_not_new_purchase_signal(self):
        gap = line(
            row_type='Component coverage gap - not a merchandise line',
            counts_as_purchase='no',
            line_identifier='',
            parent_line_id='SYN-LINE-1',
            current_stock_icon_exact='In Stock',
        )
        result = triage(lines=[line(row_type='Purchased kit parent'), gap])
        self.assertNotIn('APPARENT_STOCK_PROGRESS_REVIEW', result['flags'])
        self.assertIn('KIT_COMPONENT_EVIDENCE_UNRESOLVED', result['reason_codes'])

    def test_valid_complete_component_evidence_allows_parent_review_not_readiness(self):
        component = line(
            row_type='component',
            counts_as_purchase='no',
            line_identifier='SYN-COMP-1',
            parent_line_id='SYN-LINE-1',
            component_coverage_complete='yes',
            component_quantity_required='1',
            current_stock_icon_exact='In Stock',
        )
        result = triage(
            [summary(visible_component_rows='1', component_coverage='yes')],
            [line(row_type='Purchased kit parent', current_stock_icon_exact='In Stock'), component],
        )
        self.assertIn('APPARENT_STOCK_PROGRESS_REVIEW', result['flags'])
        self.assertFalse(result['readiness_verified'])

    def test_mixed_ds_and_unknown_quantities_do_not_suppress_positive_review(self):
        result = triage(
            [summary(active_purchased_rows='2')],
            [
                line(drop_ship='yes', current_stock_icon_exact='In Stock'),
                line(
                    line_identifier='SYN-LINE-2',
                    drop_ship='UNKNOWN',
                    remaining_quantity='Unknown - not displayed',
                    product_eta_exact='NLA',
                ),
            ],
        )
        self.assertIn('APPARENT_STOCK_PROGRESS_REVIEW', result['flags'])
        self.assertIn('LEAD_TIME_AVAILABILITY_RESEARCH', result['flags'])
        self.assertIn('DS_NOT_CONFIRMED', result['missing_fact_codes'])
        self.assertIn('QUANTITY_NOT_CONFIRMED', result['missing_fact_codes'])

    def test_arrival_1999_never_corrected_or_usable_even_with_future_line_eta(self):
        result = triage(
            [summary(expected_arrival_date_exact='Ships on Oct 20, 1999')],
            [line(product_eta_exact='2026-10-20')],
        )
        self.assertIn('ETA_YEAR_ANOMALY', result['reason_codes'])
        self.assertFalse(result['usable_eta'])
        self.assertEqual(result['attention_priority'], 1)

    def test_past_eta_and_arrival_before_ship_are_conflicts(self):
        past = triage(lines=[line(product_eta_exact='2026-10-04')])
        self.assertIn('ETA_BEFORE_CAPTURE', past['reason_codes'])
        conflict = triage(
            [
                summary(
                    current_expected_ship_date_exact='2026-10-20',
                    expected_arrival_date_exact='2026-10-19',
                )
            ]
        )
        self.assertIn('ETA_DATE_CONFLICT', conflict['reason_codes'])
        self.assertFalse(conflict['usable_eta'])

    def test_future_valid_eta_and_relative_labels_have_distinct_usable_date(self):
        for date in ('2026-10-20', '20-Oct-2026 (1)', 'Ships on Oct 20, 2026'):
            result = triage(lines=[line(product_eta_exact=date)])
            self.assertIn('LEAD_TIME_AVAILABILITY_RESEARCH', result['flags'])
            self.assertTrue(result['usable_eta'])
        relative = triage(lines=[line(product_eta_exact='Ships in 1-2 business days')])
        self.assertIn('LEAD_TIME_AVAILABILITY_RESEARCH', relative['flags'])
        self.assertFalse(relative['usable_eta'])

    def test_capture_age_and_timezone_same_instant_are_exact(self):
        known = triage(as_of='2026-10-05T10:00:00-04:00')
        self.assertEqual(known['snapshot_age_status'], 'KNOWN')
        self.assertEqual(known['snapshot_age_seconds'], 0)
        future = triage(as_of='2026-10-05T13:59:59Z')
        self.assertEqual(future['snapshot_age_status'], 'FUTURE_CAPTURE')
        self.assertIn('CAPTURE_TIME_FUTURE', future['reason_codes'])
        stale = triage(as_of='2026-10-06T14:00:01Z')
        self.assertEqual(stale['snapshot_age_status'], 'STALE')
        self.assertIn('CAPTURE_STALE', stale['reason_codes'])

    def test_as_of_requires_strict_aware_valid_date_without_unsafe_echo(self):
        for invalid in ('', '2026-10-05T14:00:00', 'SYN-PRIVATE @ invalid-time'):
            with self.assertRaises(TriageError) as caught:
                triage(as_of=invalid)
            self.assertEqual(caught.exception.code, 'TRIAGE_AS_OF_INVALID')
            self.assertNotIn(invalid, str(caught.exception)) if invalid else None

    def test_priority_independent_of_money_currency_and_source_position(self):
        first = triage(
            [summary(order_total_numeric='1', currency_code='USD', queue_position='1')],
            [line(current_stock_icon_exact='In Stock')],
        )
        second = triage(
            [summary(order_total_numeric='999999', currency_code='EUR', queue_position='999')],
            [line(current_stock_icon_exact='In Stock', queue_position='999')],
        )
        self.assertEqual(first['attention_priority'], second['attention_priority'])
        self.assertEqual(first['primary_bucket'], second['primary_bucket'])

    def test_global_hold_and_failed_capture_exclude_positive_review_flags(self):
        held = triage(lines=[line(current_stock_icon_exact='In Stock')], global_input_held=True)
        self.assertEqual(held['primary_bucket'], 'INPUT_QUARANTINED')
        self.assertEqual(held['attention_priority'], 0)
        self.assertFalse(set(held['flags']) - {'EVIDENCE_REVIEW'})
        failed = triage(lines=[])
        self.assertEqual(failed['primary_bucket'], 'FAILED_CAPTURE')
        self.assertEqual(failed['flags'], [])
        self.assertEqual(failed['attention_priority'], 7)

    def test_terminal_backorder_suppresses_all_positive_review_without_closure(self):
        for status in ('Shipped', 'Canceled'):
            result = triage(
                [summary(order_status=status)],
                [
                    line(
                        current_stock_icon_exact='In Stock',
                        product_eta_exact='Back Ordered',
                        OS_displayed='-3',
                    )
                ],
            )
            self.assertFalse(
                {
                    'STOCK_TRANSFER_REVIEW',
                    'APPARENT_STOCK_PROGRESS_REVIEW',
                    'LEAD_TIME_AVAILABILITY_RESEARCH',
                }
                & set(result['flags'])
            )
            self.assertIn('OBSERVED_TERMINAL_PROGRESS_SUPPRESSED', result['reason_codes'])
            self.assertFalse(result['decision_eligible'])
            self.assertNotIn('closed', json.dumps(result).lower())

    def test_source_join_timestamp_and_coverage_gates_positive_candidates(self):
        rows = (
            line(queue_source_url='http://127.0.0.1/SYN-different'),
            line(captured_at_america_new_york='2026-10-05T10:01:00-04:00'),
            line(line_coverage_complete='no'),
        )
        for row in rows:
            with self.subTest(
                fictional_gate=next(
                    field
                    for field in (
                        'queue_source_url',
                        'captured_at_america_new_york',
                        'line_coverage_complete',
                    )
                    if row[field] != line()[field]
                )
            ):
                row.update(current_stock_icon_exact='In Stock', product_eta_exact='Back Ordered')
                result = triage(lines=[row])
                self.assertFalse(
                    {
                        'STOCK_TRANSFER_REVIEW',
                        'APPARENT_STOCK_PROGRESS_REVIEW',
                        'LEAD_TIME_AVAILABILITY_RESEARCH',
                    }
                    & set(result['flags'])
                )
                self.assertFalse(result['usable_eta'])
        mismatch = triage(
            [summary(active_purchased_rows='2')], [line(current_stock_icon_exact='In Stock')]
        )
        self.assertNotIn('APPARENT_STOCK_PROGRESS_REVIEW', mismatch['flags'])

    def test_failed_displayed_id_placeholder_has_failed_primary_not_structural_mask(self):
        result = triage(
            [summary(order_id_matches_queue='no')],
            [
                line(
                    row_type='placeholder',
                    counts_as_purchase='no',
                    line_identifier='',
                    parent_line_id='',
                )
            ],
        )
        self.assertEqual(result['primary_bucket'], 'FAILED_CAPTURE')
        self.assertEqual(result['flags'], [])

    def test_incomplete_kit_gap_is_evidence_review_and_not_capture_failure(self):
        gap = line(
            row_type='Component coverage gap - not a merchandise line',
            counts_as_purchase='no',
            line_identifier='',
            parent_line_id='SYN-LINE-1',
            order_capture_complete='no',
        )
        result = triage(
            [summary(capture_complete='no')],
            [
                line(
                    row_type='Purchased kit parent',
                    current_stock_icon_exact='In Stock',
                    order_capture_complete='no',
                ),
                gap,
            ],
        )
        self.assertEqual(result['primary_bucket'], 'EVIDENCE_REVIEW')
        self.assertIn('KIT_COMPONENT_EVIDENCE_UNRESOLVED', result['missing_fact_codes'])
        self.assertFalse(
            {
                'STOCK_TRANSFER_REVIEW',
                'APPARENT_STOCK_PROGRESS_REVIEW',
                'LEAD_TIME_AVAILABILITY_RESEARCH',
            }
            & set(result['flags'])
        )

    def test_year_anomaly_trigger_survives_bounded_evidence_selection(self):
        result = triage(
            [
                summary(
                    expected_arrival_date_exact='1999-10-20',
                    current_expected_ship_date_exact='2026-10-20',
                    revised_ship_date_exact='2026-10-21',
                    stock_eta_exact='2026-10-22',
                )
            ],
            [line(product_eta_exact='2026-10-23', current_stock_icon_exact='In Stock')],
        )
        self.assertTrue(
            any(
                ref['field'] == 'expected_arrival_date_exact'
                and ref['observed_value'] == '1999-10-20'
                for ref in result['evidence_references']
            )
        )
        self.assertFalse(result['usable_eta'])

    def test_minimized_evidence_redacts_malicious_private_fields_and_bounds_refs(self):
        private = 'SYN-PRIVATE <img src=x onerror=alert(1)> @ raw-private-token'
        result = triage(
            [summary(customer_info_email=private, stock_eta_exact=private)],
            [
                line(
                    product_name=private,
                    product_eta_exact=private,
                    current_stock_icon_exact='In Stock',
                )
            ],
        )
        self.assertNotIn(private, json.dumps(result))
        self.assertNotIn('raw-private-token', json.dumps(result))
        for ref in result['evidence_references']:
            self.assertEqual(
                set(ref), {'scope', 'record_ordinal', 'field', 'observed_value', 'redacted'}
            )
            self.assertIn(ref['scope'], ('summary', 'lines'))
            self.assertLessEqual(len(ref['observed_value'] or ''), 64)
        self.assertLessEqual(len(result['evidence_references']), 6)

    def test_many_evidence_signals_have_bounded_refs_and_truthful_omission_count(self):
        lines = [
            line(
                line_identifier=f'SYN-LINE-{i}',
                current_stock_icon_exact='In Stock',
                product_eta_exact='Back Ordered',
                OS_displayed='-3',
            )
            for i in range(8)
        ]
        result = triage([summary(active_purchased_rows='8')], lines)
        self.assertEqual(len(result['evidence_references']), 6)
        self.assertGreater(result['evidence_omitted_count'], 0)
        self.assertFalse(result['decision_eligible'])

    def test_primary_counts_are_exclusive_and_flags_overlap(self):
        order = stage(
            lines=[line(current_stock_icon_exact='In Stock', product_eta_exact='Back Ordered')]
        ).orders[0]
        result = aggregate_triage([order], as_of=AS_OF)
        self.assertEqual(set(result['bucket_counts']), set(PRIMARY_BUCKETS))
        self.assertEqual(sum(result['bucket_counts'].values()), 1)
        self.assertGreater(sum(result['flag_counts'].values()), 1)
        self.assertEqual(set(result['flag_counts']), set(TRIAGE_FLAGS))
        self.assertEqual(result['decision_eligible_count'], 0)

    def test_v2_session_response_limit_is_closed_error_not_unchecked_raise(self):
        session = DOIReviewSession(as_of=lambda: AS_OF)
        with patch('doi_csv_staging.review.MAX_RESPONSE_BYTES', 1):
            state = session.load(
                csv_text(SUMMARY_HEADERS, [summary()]), csv_text(LINE_HEADERS, [line()]), 0
            )
        self.assertEqual(state['status'], 'error')
        self.assertEqual(state['error_code'], 'REVIEW_RESPONSE_LIMIT')
        self.assertEqual(state['orders'], [])
        self.assertEqual(state['schema'], 'doi-csv-review/v6')

    def test_closed_response_rejects_forged_reference_ordinal_and_scope(self):
        session = DOIReviewSession(as_of=lambda: AS_OF)
        state = session.load(
            csv_text(SUMMARY_HEADERS, [summary()]),
            csv_text(LINE_HEADERS, [line(current_stock_icon_exact='In Stock')]),
            0,
        )
        for ordinal, scope, field in (
            (999, 'summary', 'captured_at_america_new_york'),
            (2, 'lines', 'expected_arrival_date_exact'),
        ):
            forged = copy.deepcopy(state)
            ref = next(
                r
                for r in forged['orders'][0]['evidence']['evidence_references']
                if r['field'] == 'captured_at_america_new_york'
            )
            ref['record_ordinal'] = ordinal
            ref['scope'] = scope
            ref['field'] = field
            with self.assertRaises(DOIReviewError):
                review_response_bytes(forged)

    def test_closed_response_rejects_capture_age_tampered_against_as_of(self):
        session = DOIReviewSession(as_of=lambda: AS_OF)
        state = session.load(
            csv_text(SUMMARY_HEADERS, [summary()]), csv_text(LINE_HEADERS, [line()]), 0
        )
        state['orders'][0]['evidence']['snapshot_age_seconds'] = 17
        with self.assertRaises(DOIReviewError):
            review_response_bytes(state)

    def test_triage_validator_rejects_duplicate_flags_reasons_and_references(self):
        result = triage(lines=[line(current_stock_icon_exact='In Stock')])
        for field in ('flags', 'reason_codes', 'evidence_references'):
            forged = copy.deepcopy(result)
            self.assertTrue(forged[field])
            forged[field].append(copy.deepcopy(forged[field][0]))
            with self.assertRaises(TriageError):
                validate_triage_projection(forged)

    def test_valid_kit_component_delay_contributes_review_without_second_purchase(self):
        component = line(
            row_type='component',
            counts_as_purchase='no',
            line_identifier='SYN-COMP-1',
            parent_line_id='SYN-LINE-1',
            component_coverage_complete='yes',
            component_quantity_required='1',
            product_eta_exact='Back Ordered',
        )
        result = triage(
            [summary(visible_component_rows='1', component_coverage='yes')],
            [line(row_type='Purchased kit parent', current_stock_icon_exact='In Stock'), component],
        )
        self.assertIn('LEAD_TIME_AVAILABILITY_RESEARCH', result['flags'])
        self.assertNotIn('APPARENT_STOCK_PROGRESS_REVIEW', result['flags'])
        self.assertFalse(result['decision_eligible'])

    def test_nonkit_incomplete_capture_does_not_invent_kit_structure_reason(self):
        result = triage([summary(capture_complete='no')], [line(order_capture_complete='no')])
        self.assertNotIn('KIT_COMPONENT_EVIDENCE_UNRESOLVED', result['reason_codes'])
        self.assertNotIn('KIT_COMPONENT_EVIDENCE_UNRESOLVED', result['missing_fact_codes'])
        self.assertFalse(result['decision_eligible'])

    def test_primary_transfer_basis_retained_when_date_anomalies_compete_for_refs(self):
        result = triage(
            [
                summary(
                    expected_arrival_date_exact='1999-10-20',
                    current_expected_ship_date_exact='1999-10-21',
                    revised_ship_date_exact='1999-10-22',
                    stock_eta_exact='1999-10-23',
                )
            ],
            [
                line(
                    current_stock_icon_exact='In Stock',
                    product_eta_exact='Back Ordered',
                    OS_displayed='-3',
                )
            ],
        )
        self.assertEqual(result['primary_bucket'], 'STOCK_TRANSFER_REVIEW')
        refs = result['evidence_references']
        self.assertTrue(any(r['field'] == 'current_stock_icon_exact' for r in refs))
        self.assertTrue(any(r['field'] in ('product_eta_exact', 'OS_displayed') for r in refs))
        self.assertLessEqual(len(refs), 6)

    def test_projection_validator_rejects_terminal_reason_with_positive_flags(self):
        result = triage(lines=[line(current_stock_icon_exact='In Stock')])
        result['reason_codes'].append('OBSERVED_TERMINAL_PROGRESS_SUPPRESSED')
        with self.assertRaises(TriageError):
            validate_triage_projection(result)

    def test_verified_zero_remaining_excludes_all_positive_physical_signals(self):
        for remaining in ('0', '0.0', '000'):
            result = triage(
                lines=[
                    line(
                        remaining_quantity=remaining,
                        current_stock_icon_exact='In Stock',
                        product_eta_exact='2026-10-20',
                        OS_displayed='-3',
                    )
                ]
            )
            self.assertFalse(
                {
                    'STOCK_TRANSFER_REVIEW',
                    'APPARENT_STOCK_PROGRESS_REVIEW',
                    'LEAD_TIME_AVAILABILITY_RESEARCH',
                }
                & set(result['flags'])
            )
            self.assertFalse(result['usable_eta'])
            self.assertFalse(result['decision_eligible'])

    def test_zero_backorder_and_relative_labels_are_not_open_opportunities(self):
        for label in ('Back Ordered', 'Ships in 1-2 business days'):
            result = triage(lines=[line(remaining_quantity='0', product_eta_exact=label)])
            self.assertNotIn('LEAD_TIME_AVAILABILITY_RESEARCH', result['flags'])

    def test_mixed_zero_and_unknown_remaining_keeps_unknown_research_only(self):
        result = triage(
            [summary(active_purchased_rows='2')],
            [
                line(remaining_quantity='0', current_stock_icon_exact='In Stock'),
                line(
                    line_identifier='SYN-LINE-2',
                    remaining_quantity='Unknown - not displayed',
                    product_eta_exact='Back Ordered',
                ),
            ],
        )
        self.assertNotIn('APPARENT_STOCK_PROGRESS_REVIEW', result['flags'])
        self.assertIn('LEAD_TIME_AVAILABILITY_RESEARCH', result['flags'])
        self.assertIn('QUANTITY_NOT_CONFIRMED', result['missing_fact_codes'])

    def test_service_only_eta_does_not_create_merchandise_date_anomaly(self):
        for eta in ('1999-10-20', '2026-10-04', 'Ships on Oct 20, 1999'):
            result = triage(
                [summary(separate_service_rows_displayed='1')],
                [
                    line(
                        row_type='Purchased service/charge line',
                        physical_or_service='Explicit service/charge line',
                        product_eta_exact=eta,
                        dated_line_eta=eta,
                    )
                ],
            )
            self.assertNotIn('ETA_YEAR_ANOMALY', result['reason_codes'])
            self.assertNotIn('ETA_BEFORE_CAPTURE', result['reason_codes'])
            self.assertNotIn('LEAD_TIME_AVAILABILITY_RESEARCH', result['flags'])

    def test_physical_future_eta_not_invalidated_by_service_eta(self):
        result = triage(
            [summary(active_purchased_rows='2', separate_service_rows_displayed='1')],
            [
                line(product_eta_exact='2026-10-20'),
                line(
                    line_identifier='SYN-SERVICE-1',
                    row_type='Purchased service/charge line',
                    physical_or_service='Explicit service/charge line',
                    product_eta_exact='1999-10-20',
                ),
            ],
        )
        self.assertTrue(result['usable_eta'])
        self.assertIn('LEAD_TIME_AVAILABILITY_RESEARCH', result['flags'])
        self.assertNotIn('ETA_YEAR_ANOMALY', result['reason_codes'])

    def test_lead_time_labels_do_not_claim_overdue_or_delayed_order(self):
        for label in ('Ships in 1-2 business days', '2026-10-20', 'Back Ordered'):
            result = triage(lines=[line(product_eta_exact=label)])
            self.assertIn('LEAD_TIME_AVAILABILITY_RESEARCH', result['flags'])
            serialized = json.dumps(result)
            self.assertNotIn('DELAYED_ITEM_RESEARCH', serialized)
            self.assertNotIn('OBSERVED_DELAYED_LABEL', serialized)
            self.assertNotIn('OVERDUE', serialized)
            self.assertFalse(result['decision_eligible'])

    def test_zero_kit_parent_excludes_component_research_even_unknown_component(self):
        component = line(
            row_type='component',
            counts_as_purchase='no',
            line_identifier='SYN-COMP-1',
            parent_line_id='SYN-LINE-1',
            component_coverage_complete='yes',
            component_quantity_required='1',
            remaining_quantity='UNKNOWN',
            product_eta_exact='Back Ordered',
        )
        result = triage(
            [summary(visible_component_rows='1', component_coverage='yes')],
            [
                line(
                    row_type='Purchased kit parent',
                    remaining_quantity='0',
                    current_stock_icon_exact='In Stock',
                ),
                component,
            ],
        )
        self.assertFalse(
            {
                'STOCK_TRANSFER_REVIEW',
                'APPARENT_STOCK_PROGRESS_REVIEW',
                'LEAD_TIME_AVAILABILITY_RESEARCH',
            }
            & set(result['flags'])
        )

    def test_zero_component_does_not_create_lead_time_research(self):
        component = line(
            row_type='component',
            counts_as_purchase='no',
            line_identifier='SYN-COMP-1',
            parent_line_id='SYN-LINE-1',
            component_coverage_complete='yes',
            component_quantity_required='1',
            remaining_quantity='0',
            product_eta_exact='Back Ordered',
        )
        result = triage(
            [summary(visible_component_rows='1', component_coverage='yes')],
            [line(row_type='Purchased kit parent', remaining_quantity='1'), component],
        )
        self.assertNotIn('LEAD_TIME_AVAILABILITY_RESEARCH', result['flags'])

    def test_zero_physical_bad_eta_does_not_poison_active_unknown_future_eta(self):
        for bad_eta in ('1999-10-20', '2026-10-04'):
            result = triage(
                [summary(active_purchased_rows='2')],
                [
                    line(remaining_quantity='0', product_eta_exact=bad_eta, dated_line_eta=bad_eta),
                    line(
                        line_identifier='SYN-LINE-2',
                        remaining_quantity='Unknown - not displayed',
                        product_eta_exact='2026-10-20',
                    ),
                ],
            )
            self.assertTrue(result['usable_eta'])
            self.assertNotIn('ETA_YEAR_ANOMALY', result['reason_codes'])
            self.assertNotIn('ETA_BEFORE_CAPTURE', result['reason_codes'])
            self.assertEqual(result['attention_priority'], 4)
            self.assertIn('LEAD_TIME_AVAILABILITY_RESEARCH', result['flags'])
            self.assertFalse(result['decision_eligible'])


if __name__ == '__main__':
    unittest.main()
