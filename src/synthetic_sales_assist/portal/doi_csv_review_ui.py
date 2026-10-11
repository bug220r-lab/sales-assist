"""The existing portal frame with a closed, in-memory DOI CSV review flow.

No customer or source CSV fields are accepted by the renderer. The browser sends
the chosen pair once, then renders only the server's minimized projection.
"""

from __future__ import annotations

from pathlib import Path

from synthetic_sales_assist.portal.dashboard_rendering import _page
from synthetic_sales_assist.portal.alternate_draft_ui import ALTERNATE_DRAFT_PANEL
from doi_csv_staging.review import MAX_RESPONSE_BYTES as DOI_REVIEW_RESPONSE_BYTES


def render_doi_csv_review_page(csrf_token: str, *, review_only: bool = True) -> bytes:
    return _page(
        route_name="doi_csv_review",
        heading="DOI split review",
        lede=(
            "Review ready/waiting evidence beside each full captured order total. "
            "Verify source facts before taking action."
        ),
        csrf_token=csrf_token,
        presentation=False,
        review_only=review_only,
        body=(
            '<div class="doi-review dashboard-stack">\n'
            '<p><a href="/doi-draft-transfer">Import and review drafts for Help Scout</a></p>'
            '<section class="dashboard-panel doi-scope" aria-label="Review '
            'scope">\n'
            "  <h2>Split-review worklist</h2>\n"
            "  <p>Full order totals provide captured order context, not split value or "
            "a revenue forecast. Confirmed patterns remain human-review evidence; they "
            "do not authorize splitting or fulfillment.</p>\n"
            "  <details><summary>Evidence scope and limits</summary>\n"
            "  <p>An apparent split pattern requires distinct physical purchase "
            "records on the apparent ready and waiting sides. Stock labels alone do "
            "not establish FULL allocation or verified outstanding quantity. Confirmed "
            "split criteria are not available from these captures.</p>\n"
            "  <p>Future ETA dates and relative lead-time labels are signals for "
            "lead-time / availability research. Overdue status and lateness remain "
            "unknown without captured promise chronology. Stock-status observations "
            "require outstanding-quantity verification before any fulfillment "
            "conclusion.</p>\n"
            "  <p>A snapshot older than 24 hours is marked stale as a review-refresh "
            "heuristic. This threshold is not an ECS business rule or a fulfillment "
            "service-level agreement.</p>\n"
            "  <p>The default worklist includes only orders with an eligible captured "
            "sales-rep scope. Confirmed other-rep assignments are excluded; missing, "
            "conflicting or unmapped rep values are held for verification. DOI "
            "reviewer assignment is separate from the order-level ECS Sales Rep. Mixed "
            "and non-drop-ship orders remain supported. Rep scope does not determine "
            "fulfillment readiness, shipping dates or sales-credit entitlement.</p>\n"
            "  <p>Unknown fields remain unknown. Product ETA and current stock are "
            "distinct captured fields. Stock at order time and order date have not "
            "been verified or captured. Service/charge purchases are counted "
            "separately from physical merchandise. Component gap placeholders are not "
            "purchases.</p>\n"
            "  <p>Capture scope: the Details inventory fields and customer email only. "
            "Do not add names, addresses, phone numbers, payment details or Notes. "
            "Customer contact details and unrestricted capture text are omitted from "
            "the retained review. Only bounded, validated stock, date and status "
            "observations appear in source references.</p>\n"
            "  </details>\n"
            "</section>\n"
            '<section class="dashboard-panel" aria-labelledby="doi-load-heading">\n'
            '  <h2 id="doi-load-heading">Load a file pair</h2>\n'
            '  <details class="doi-session-help"><summary>Session and saved checks</summary>\n'
            "  <p>The session is shared by tabs of this local service. Start a new "
            "pair to clear the prior review before choosing files. Clear removes the "
            "retained review; stopping the service removes the session. It expires "
            "after 10 hours from loading. Refreshing or sorting does not extend this "
            "window.</p>\n"
            "  <p>Saved Reviewed for split checks stay on this computer across Clear, "
            "expiry and restart. Reload the same capture to restore them. Uncheck an "
            "order to remove its saved check. A check means reviewed, never approved "
            "to split or fulfill.</p>\n"
            "  <p>Hiding, closing or leaving this page does not clear the shared "
            "review. A load already accepted can remain available and be restored "
            "until Clear session, expiry or service shutdown. Aborting the page's "
            "request does not undo an accepted load.</p>\n"
            "  </details>\n"
            '  <div class="dashboard-actions">\n'
            '    <button type="button" id="doi-new-pair">Start a new file '
            "pair</button>\n"
            '    <button type="button" id="doi-clear">Clear session</button>\n'
            "  </div>\n"
            '  <form id="doi-load-form" class="dashboard-form doi-file-pair">\n'
            '    <label class="dashboard-field"><span>Order summary CSV</span>\n'
            '      <input type="file" id="doi-summary-file" accept=".csv,text/csv" '
            "disabled required>\n"
            "    </label>\n"
            '    <label class="dashboard-field"><span>Lines and components CSV</span>\n'
            '      <input type="file" id="doi-lines-file" accept=".csv,text/csv" '
            "disabled required>\n"
            "    </label>\n"
            '    <p class="dashboard-field-hint">UTF-8 CSV only. Up to 1 MiB and 5,000 '
            "records per file, with up to 500 joined order keys. "
            f"Review data is limited to {DOI_REVIEW_RESPONSE_BYTES // (1024 * 1024)} MiB; "
            "unusually large pairs may need smaller batches. File names are not "
            "sent to the service.</p>\n"
            '    <button type="submit" id="doi-load" disabled>Load and review</button>\n'
            "  </form>\n"
            '  <p id="doi-message" role="status" aria-live="polite">Checking the local '
            "session…</p>\n"
            "  <noscript><p>JavaScript is needed to load a file pair. No review has "
            "been loaded by this page.</p></noscript>\n"
            "</section>\n"
            '<section id="doi-results" class="dashboard-panel" hidden '
            'aria-labelledby="doi-results-heading">\n'
            '  <h2 id="doi-results-heading">Current session review</h2>\n'
            '  <p id="doi-session-label" class="dashboard-meta"></p>\n'
            '  <p id="doi-batch-holds" class="dashboard-warning"></p>\n'
            '  <p id="doi-ownership-summary" class="dashboard-meta"></p>\n'
            "  <details><summary>Capture counts and review context</summary>\n"
            '  <p id="doi-currency-summary" class="dashboard-meta"></p><dl '
            'id="doi-counts"></dl>\n'
            '  <p id="doi-triage-context" class="dashboard-meta"></p>\n'
            '  <dl id="doi-triage-counts"></dl></details>\n'
            '  <div class="dashboard-filter doi-filters"><label '
            'class="dashboard-field"><span>Captured rep scope</span>\n'
            '    <select id="doi-rep-scope">\n'
            '      <option value="eligible">Eligible for my review</option>\n'
            '      <option value="other">Excluded: confirmed other rep</option>\n'
            '      <option value="held">Held: verify rep assignment</option>\n'
            '      <option value="all">All captured orders for reconciliation</option>\n'
            "    </select>\n"
            '  </label><label class="dashboard-field"><span>Review group</span>\n'
            '    <select id="doi-group">\n'
            '      <option value="APPARENT_SPLIT_CANDIDATE">Apparent ready/waiting '
            "pattern</option>\n"
            '      <option value="all">All split statuses</option>\n'
            '      <option value="INSUFFICIENT_SPLIT_EVIDENCE">Insufficient split '
            "evidence</option>\n"
            '      <option value="NO_SPLIT_PATTERN">No observed split pattern</option>\n'
            '      <option value="CAPTURE_HELD">Capture held</option>\n'
            '      <option value="currency_conflict">Currency conflicts (review '
            "held)</option>\n"
            '      <option value="missing_evidence">Missing evidence / evaluation '
            "held</option>\n"
            '      <option value="coverage_held">Visible coverage held</option>\n'
            '      <option value="batch_quarantine">Batch quarantine</option>\n'
            "    </select>\n"
            '  </label><label class="dashboard-field"><span>Worklist '
            'order</span><select id="doi-sort"><option value="total">Full order total, '
            'highest first</option><option value="priority">Split status, then full '
            'order total</option><option value="source">Capture '
            "order</option></select></label>\n"
            '  <label class="doi-review-check doi-hide-reviewed"><input type="checkbox" '
            'id="doi-hide-reviewed"> Hide reviewed</label></div>\n'
            '  <p id="doi-reviewed-count" class="doi-review-progress" '
            'role="status" aria-live="polite"></p>\n'
            '  <p id="doi-group-count" role="status"></p>\n'
            '  <div class="dashboard-table-wrap doi-worklist" tabindex="0" role="region" '
            'aria-label="Scrollable captured orders">\n'
            "    <table><caption>Captured order split-review worklist</caption>\n"
            '    <thead><tr><th scope="col">Order</th><th scope="col">Reviewed for split</th>'
            '<th scope="col">Full captured '
            'total</th><th scope="col">Split status</th><th scope="col">Ready / '
            'waiting</th><th scope="col">Next verification and '
            "evidence</th></tr></thead>\n"
            '    <tbody id="doi-orders"></tbody></table>\n'
            "  </div>\n"
            '  <p class="dashboard-meta">Source references are logical CSV record '
            "numbers, including the header as record 1. They identify the original "
            "capture records without displaying customer details or source URLs. "
            "Invalid and orphan records are counted above even when they cannot appear "
            "as a joined order.</p>\n"
            "</section>" + ALTERNATE_DRAFT_PANEL + "</div>"
        ),
    )


DOI_CSV_REVIEW_JS = (
    Path(__file__).with_name("doi-review.js").read_text(encoding="utf-8")
).replace("__DOI_RESPONSE_LIMIT_BYTES__", str(DOI_REVIEW_RESPONSE_BYTES))
