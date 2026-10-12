"""Synthetic discovery views and saved-check behavior, without a browser or server."""

import json
import shutil
import subprocess
import unittest
from pathlib import Path

from doi_csv_staging.ownership import RepScopePolicy
from doi_csv_staging.review import DOIReviewSession
from synthetic_sales_assist.portal.doi_csv_review_ui import (
    DOI_CSV_REVIEW_JS,
    render_doi_csv_review_page,
)
from tests.test_csv_staging_independent import line, summary
from tests.test_doi_csv_review_ui import fictional_csvs
from tests.test_doi_review_marks import MemoryMarks


def discovery_fixture():
    """Different fictional orders exercise independent view and hold conditions."""
    summaries, lines = [], []
    kinds = {
        "90000101": "apparent",
        "90000102": "held",
        "90000103": "stock",
        "90000104": "other",
        "90000105": "held_reviewed",
        "90000106": "stock_reviewed",
        "90000107": "currency_held",
        "90000108": "kit_held",
        "90000109": "currency_apparent",
    }
    for order_id, kind in kinds.items():
        stock = kind.startswith("stock")
        held = "held" in kind
        kit = kind == "kit_held"
        summaries.append(
            summary(
                order_id,
                order_status="Active",
                active_purchased_rows="1" if stock else "2",
                visible_component_rows="1" if kit else "0",
                doi_source_assignment_conflict="yes" if held else "no",
                displayed_sales_credit_value=(
                    "synthetic_other_rep" if kind == "other" else "synthetic_owner_rep"
                ),
                currency_code="EUR" if kind.startswith("currency") else "USD",
                currency_symbol_displayed="$",
                order_total_displayed="$100",
                order_total_numeric="100",
            )
        )
        if stock:
            lines.append(line(order_id, current_stock_icon_exact="Back Ordered",
                              ordered_quantity_displayed="5", OH_displayed="2"))
            continue
        lines.extend([
            line(order_id, current_stock_icon_exact="In Stock"),
            line(order_id, line_identifier="SYN-LINE-2",
                 row_type="purchased kit parent" if kit else "purchased",
                 current_stock_icon_exact="Back Ordered"),
        ])
        if kit:
            lines.append(line(order_id, line_identifier="SYN-COMPONENT-1",
                              row_type="component", counts_as_purchase="no",
                              parent_line_id="SYN-LINE-2", component_coverage_complete="yes",
                              current_stock_icon_exact="Back Ordered"))
    store = MemoryMarks()
    session = DOIReviewSession(
        clock=lambda: 1000.0,
        as_of=lambda: "2026-10-05T23:01:00Z",
        rep_policy=RepScopePolicy(frozenset({"synthetic_owner_rep"}),
                                 frozenset({"synthetic_unassigned_web"}),
                                 frozenset({"synthetic_other_rep"})),
        review_mark_store=store,
    )
    left, right = fictional_csvs(summaries, lines)
    session.load(left, right, 0)
    for order_id in ("90000105", "90000106"):
        marks = session.reviewed_snapshot()
        record = next(item for item in marks["orders"] if item["order_id"] == order_id)
        session.set_reviewed({
            "revision": marks["revision"], "storage_revision": marks["storage_revision"],
            "order_id": order_id, "evidence_key": record["evidence_key"], "reviewed": True,
        })
    return {"state": session.snapshot(), "reviewed": session.reviewed_snapshot()}


class DiscoveryFrontendTests(unittest.TestCase):
    def test_shell_defaults_distinguish_patterns_from_stock_clues(self):
        for restricted in (False, True):
            html = render_doi_csv_review_page("a" * 64, review_only=restricted).decode()
            for select in ("doi-rep-scope", "doi-group"):
                options = html.split(f'<select id="{select}">', 1)[1].split("</select>", 1)[0]
                self.assertTrue(options.lstrip().startswith('<option value="review_leads">'))
            self.assertIn("Eligible and held for verification", html)
            self.assertIn("Held ready/waiting patterns", html)
            self.assertIn("Stock-counter clues only", html)
            self.assertIn('value="eligible">Eligible for my review', html)
            self.assertIn('id="doi-hide-reviewed"', html)
            self.assertNotIn("default worklist includes only", html)

    def test_shipped_js_filters_and_dom_preserve_holds_and_saved_checks(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node is required for the synthetic DOM checks")
        script = Path(__file__).resolve().parents[1] / "tools/check_doi_discovery_frontend.mjs"
        result = subprocess.run(
            [node, str(script)],
            input=json.dumps({"js": DOI_CSV_REVIEW_JS, "discovery": discovery_fixture()}),
            text=True, capture_output=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report["success"])
        self.assertFalse(report["network_accessed"])
        self.assertFalse(report["browser_interaction_tested"])
        self.assertGreaterEqual(report["assertions"], 40)
