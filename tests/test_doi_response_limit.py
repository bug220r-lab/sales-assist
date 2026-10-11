"""Synthetic-only response bounds; original capture validation lives outside source."""

import json
import unittest
from functools import lru_cache
from unittest.mock import patch
from doi_csv_staging import SUMMARY_HEADERS, LINE_HEADERS
from doi_csv_staging import review
from doi_csv_staging.review import DOIReviewSession, DOIReviewError, review_response_bytes
from synthetic_sales_assist.portal import server
from synthetic_sales_assist.portal.doi_csv_review_ui import (
    DOI_CSV_REVIEW_JS,
    render_doi_csv_review_page,
)
from tests.test_csv_staging_independent import summary, line, csv_text
from tests.test_doi_csv_review_ui import fictional_csvs, ReviewHTTPTests
from tests.test_doi_review_marks import MemoryMarks


@lru_cache(maxsize=1)
def maximum_shape_csvs():
    summaries = []
    lines = []
    for index in range(500):
        order = str(90000000 + index)
        # Keep legitimate CSV bytes below 1 MiB while exercising both count maxima.
        summaries.append(
            summary(
                order,
                active_purchased_rows="10",
                customer_info_email="",
                queue_source_url="",
                order_admin_url="",
            )
        )
        for number in range(10):
            lines.append(
                line(
                    order,
                    line_identifier=f"SYN-L{number}",
                    sku="",
                    queue_source_url="",
                    order_admin_url="",
                    current_stock_icon_exact="In Stock" if number % 2 else "Back Ordered",
                )
            )
    result = csv_text(SUMMARY_HEADERS, summaries), csv_text(LINE_HEADERS, lines)
    assert all(len(text.encode()) <= review.MAX_CSV_BYTES for text in result)
    return result


class DOIResponseLimitTests(unittest.TestCase):
    def test_limits_and_frontend_bound_are_consistent(self):
        self.assertEqual(review.MAX_RESPONSE_BYTES, 4 * 1024 * 1024)
        self.assertEqual(review.MAX_CSV_BYTES, 1024 * 1024)
        self.assertEqual((review.MAX_ORDERS, review.MAX_RECORDS), (500, 5000))
        self.assertEqual(server.MAX_RESPONSE_BODY_BYTES, 512 * 1024)
        self.assertEqual(server.DOI_REVIEW_MAX_RESPONSE_BYTES, review.MAX_RESPONSE_BYTES)
        self.assertIn("const maxReviewResponseBytes = 4194304;", DOI_CSV_REVIEW_JS)
        self.assertIn("4 MiB", render_doi_csv_review_page("a" * 64).decode())
        self.assertIn("saved checkboxes were not deleted", DOI_CSV_REVIEW_JS)

    def test_maximum_input_count_shape_fits_bounded_review(self):
        state = DOIReviewSession().load(*maximum_shape_csvs(), 0)
        self.assertNotEqual(state["status"], "error")
        self.assertEqual((state["counts"]["orders"], state["counts"]["line_records"]), (500, 5000))
        encoded = review_response_bytes(state)
        self.assertGreater(len(encoded), 512 * 1024)
        self.assertLessEqual(len(encoded), review.MAX_RESPONSE_BYTES)

    def test_serializer_exact_boundary_and_one_byte_over(self):
        state = DOIReviewSession().load(*fictional_csvs(), 0)
        size = len(review_response_bytes(state))
        with patch.object(review, "MAX_RESPONSE_BYTES", size):
            self.assertEqual(len(review_response_bytes(state)), size)
        with patch.object(review, "MAX_RESPONSE_BYTES", size - 1):
            with self.assertRaisesRegex(DOIReviewError, "REVIEW_RESPONSE_LIMIT"):
                review_response_bytes(state)

    def test_failed_bounded_load_clears_display_but_preserves_checks(self):
        store = MemoryMarks()
        session = DOIReviewSession(review_mark_store=store)
        session.load(*fictional_csvs(), 0)
        state = session.reviewed_snapshot()
        record = state["orders"][0]
        session.set_reviewed(
            dict(
                revision=state["revision"],
                storage_revision=state["storage_revision"],
                order_id=record["order_id"],
                evidence_key=record["evidence_key"],
                reviewed=True,
            )
        )
        saved = dict(store.records)
        with patch.object(review, "MAX_RESPONSE_BYTES", 1000):
            failed = session.load(*fictional_csvs(), session.snapshot()["revision"])
        self.assertEqual(failed["error_code"], "REVIEW_RESPONSE_LIMIT")
        self.assertEqual(failed["orders"], [])
        self.assertEqual(store.records, saved)
        session.load(*fictional_csvs(), session.snapshot()["revision"])
        self.assertEqual(session.reviewed_snapshot()["orders"][0]["status"], "REVIEWED")


class DOIResponseHTTPTests(unittest.TestCase):
    setUp = ReviewHTTPTests.setUp
    tearDown = ReviewHTTPTests.tearDown
    request = ReviewHTTPTests.request

    def test_large_valid_post_and_get_cross_both_server_boundaries(self):
        left, right = maximum_shape_csvs()
        # Maximum-count input can exceed the small-fixture 3s socket timeout on Windows.
        code, _, body = self.request(
            "POST",
            "/api/v1/doi-csv-review/load",
            json.dumps(dict(revision=0, summary_csv=left, lines_csv=right)),
            timeout=10,
        )
        self.assertEqual(code, 200)
        self.assertGreater(len(body), 512 * 1024)
        self.assertEqual(json.loads(body)["counts"]["orders"], 500)
        code, _, body = self.request("GET", "/api/v1/doi-csv-review/state")
        self.assertEqual(code, 200)
        self.assertGreater(len(body), 512 * 1024)
        self.assertLessEqual(len(body), 4 * 1024 * 1024)

    def test_transport_still_rejects_over_four_mib(self):
        with patch.object(
            server, "review_response_bytes", return_value=b" " * (4 * 1024 * 1024 + 1)
        ):
            code, _, body = self.request("GET", "/api/v1/doi-csv-review/state")
        self.assertEqual(code, 500)
        self.assertIn(b"RESPONSE_BODY_TOO_LARGE", body)
        self.assertEqual(self.server.doi_review_session.snapshot()["revision"], 0)

    def test_larger_transport_flag_cannot_expand_unrelated_routes(self):
        def other(handler, path):
            handler._send(
                200, b" " * (512 * 1024 + 1), "application/json", doi_review_response=True
            )

        with patch.object(server.PortalRequestHandler, "_get", other):
            code, _, body = self.request("GET", "/doi-csv-review")
        self.assertEqual(code, 500)
        self.assertIn(b"RESPONSE_BODY_TOO_LARGE", body)
