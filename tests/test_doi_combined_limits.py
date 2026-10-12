"""Bounded larger DOI capture inputs; reserved synthetic fixtures only."""

import json
import unittest

from doi_csv_staging import LINE_HEADERS, SUMMARY_HEADERS, review
from synthetic_sales_assist.portal.doi_csv_review_ui import (
    DOI_CSV_REVIEW_JS,
    render_doi_csv_review_page,
)
from tests.test_csv_staging_independent import csv_text, line, summary


class CombinedLimitTests(unittest.TestCase):
    def test_one_thousand_and_one_orders_are_rejected(self):
        order_ids = [str(90000000 + number) for number in range(1001)]
        state = review.DOIReviewSession().load(
            csv_text(SUMMARY_HEADERS, [summary(order_id) for order_id in order_ids]),
            csv_text(LINE_HEADERS, [line(order_id) for order_id in order_ids]),
            0,
        )
        self.assertEqual(state["error_code"], "REVIEW_ORDER_LIMIT")
        self.assertEqual(state["orders"], [])

    def test_exact_csv_byte_boundary_is_not_file_size_rejected(self):
        # Malformed data fails closed after the byte gate accepts its exact bound.
        for value in ["x" * review.MAX_CSV_BYTES, "\u00e9" * (review.MAX_CSV_BYTES // 2)]:
            state = review.DOIReviewSession().load(value, "", 0)
            self.assertNotEqual(state["error_code"], "REVIEW_CSV_TOO_LARGE")
            self.assertEqual(state["status"], "quarantined")
            self.assertTrue(state["batch_holds"])

    def test_one_byte_over_csv_bound_is_rejected_for_either_file(self):
        cases = [
            ("x" * (review.MAX_CSV_BYTES + 1), ""),
            ("", "x" * (review.MAX_CSV_BYTES + 1)),
            ("\u00e9" * (review.MAX_CSV_BYTES // 2) + "x", ""),
        ]
        for left, right in cases:
            state = review.DOIReviewSession().load(left, right, 0)
            self.assertEqual(state["error_code"], "REVIEW_CSV_TOO_LARGE")
            self.assertEqual(state["orders"], [])

    def test_request_exact_bound_and_one_byte_over(self):
        base = json.dumps({"revision": 0, "summary_csv": "", "lines_csv": ""}).encode()
        exact = base + b" " * (review.MAX_BODY_BYTES - len(base))
        self.assertEqual(review.parse_review_request(exact)["revision"], 0)
        with self.assertRaisesRegex(review.DOIReviewError, "REVIEW_BODY_TOO_LARGE"):
            review.parse_review_request(exact + b" ")

    def test_record_limit_remains_five_thousand(self):
        rows = [line(line_identifier=f"SYN-{number}") for number in range(5001)]
        state = review.DOIReviewSession().load(
            csv_text(SUMMARY_HEADERS, [summary()]), csv_text(LINE_HEADERS, rows), 0
        )
        self.assertEqual(state["error_code"], "REVIEW_RECORD_LIMIT")

    def test_invalid_request_forms_still_rejected(self):
        for raw in [
            b"\xff",
            b"{",
            b'{"revision":0,"revision":0}',
            b'{"revision":true}',
            b'{"revision":0,"summary_csv":false,"lines_csv":""}',
        ]:
            with self.assertRaises(review.DOIReviewError):
                review.parse_review_request(raw)

    def test_frontend_and_backend_limits_share_values(self):
        html = render_doi_csv_review_page("a" * 64).decode()
        self.assertIn("Up to 4 MiB and 5,000", html)
        self.assertIn("1,000 joined order keys", html)
        self.assertIn("s.orders.length <= 1000", DOI_CSV_REVIEW_JS)
        self.assertIn("left.size > 4194304 || right.size > 4194304", DOI_CSV_REVIEW_JS)
        self.assertNotIn("__DOI_", DOI_CSV_REVIEW_JS)
        self.assertEqual(review.MAX_BODY_BYTES, 16 * 1024 * 1024)
