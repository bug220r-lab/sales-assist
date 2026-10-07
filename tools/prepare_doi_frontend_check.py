"""Build synthetic-only frontend validation input; never launch a service."""

import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT), str(ROOT / 'src'), str(ROOT / 'tests')]
from tests.test_csv_staging_independent import summary, line, csv_text
from doi_csv_staging import SUMMARY_HEADERS, LINE_HEADERS
from doi_csv_staging.review import DOIReviewSession
from synthetic_sales_assist.portal.doi_csv_review_ui import (
    DOI_CSV_REVIEW_JS,
    render_doi_csv_review_page,
)
from synthetic_sales_assist.portal.dashboard_rendering import render_doi_queue


def pair(stamp='2026-10-05T10:00:00-04:00', waiting='Back Ordered'):
    return [
        summary(
            active_purchased_rows='2',
            order_status='Active',
            captured_at_america_new_york=stamp,
            order_total_numeric='1234.50',
            order_total_displayed='$1,234.50',
            currency_symbol_displayed='$',
        )
    ], [
        line(current_stock_icon_exact='In Stock', captured_at_america_new_york=stamp),
        line(
            line_identifier='SYN-LINE-2',
            current_stock_icon_exact=waiting,
            captured_at_america_new_york=stamp,
        ),
    ]


def state(stamp='2026-10-05T10:00:00-04:00', waiting='Back Ordered'):
    summaries, lines = pair(stamp, waiting)
    session = DOIReviewSession(as_of=lambda: '2026-10-05T23:01:00Z')
    return session.load(csv_text(SUMMARY_HEADERS, summaries), csv_text(LINE_HEADERS, lines), 0)


normal = render_doi_csv_review_page('a' * 64, review_only=False).decode('utf-8')
restricted = render_doi_csv_review_page('a' * 64, review_only=True).decode('utf-8')
shell = {
    'overview_navigation': 'href="/overview"' in normal,
    'sales_credit_navigation': 'href="/sales-credit"' in normal,
    'doi_navigation': 'href="/doi"' in normal,
    'restricted_navigation': 'href="/overview"' not in restricted,
    'full_total_heading': 'Full captured total' in normal,
    'split_worklist_heading': 'Split-review worklist' in normal,
    'currency_conflict_option': '<option value="currency_conflict">'
    'Currency conflicts (review held)</option>'
    in normal
    and 'value="currency_conflict"' in restricted,
    'currency_conflict_counter': 'id="doi-currency-summary"' in normal
    and 'id="doi-currency-summary"' in restricted,
}
assert all(shell.values())
payload = {
    'js': DOI_CSV_REVIEW_JS,
    'state': state(),
    'empty': DOIReviewSession().snapshot(),
    'utc_cross_midnight': state('2026-10-06T00:30:00Z', 'Ships on Oct 5, 2026'),
    'shell_checks': shell,
}
# Future capture would be held. Keep this synthetic clock after both captures.
session = DOIReviewSession(as_of=lambda: '2026-10-06T01:00:00Z')
summaries, lines = pair('2026-10-06T00:30:00Z', 'Ships on Oct 5, 2026')
payload['utc_cross_midnight'] = session.load(
    csv_text(SUMMARY_HEADERS, summaries), csv_text(LINE_HEADERS, lines), 0
)
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    '--output',
    required=True,
    type=Path,
    help='Explicit scratch path for generated synthetic input.',
)
args = parser.parse_args()
args.output.write_text(json.dumps(payload, ensure_ascii=True), encoding='utf-8')
print(
    json.dumps(
        {
            'synthetic_states': 3,
            'shell_render_checks': len(shell),
            'all_shell_checks_passed': True,
            'browser_launched': False,
        }
    )
)
