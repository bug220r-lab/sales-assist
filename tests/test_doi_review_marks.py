"""Evidence-bound attention markers, using generated fictional captures only."""

import copy
import json
import threading
import unittest

from doi_csv_staging.review import DOIReviewError, DOIReviewSession
from doi_csv_staging.review_marks import ReviewMarkError
from synthetic_sales_assist.portal.server import PortalHTTPServer, PortalServerConfig
from tests.test_csv_staging_independent import summary, line
from tests.test_doi_csv_review_ui import fictional_csvs
from tests import test_doi_csv_review_ui as review_ui_tests


class MemoryMarks:
    def __init__(self):
        self.revision, self.records, self.failed = 0, {}, False

    def read(self):
        if self.failed:
            raise ReviewMarkError("REVIEW_MARKS_UNAVAILABLE")
        return self.revision, dict(self.records)

    def set(self, key, evidence, reviewed, expected_revision):
        revision, before = self.read()
        if revision != expected_revision:
            raise ReviewMarkError("REVIEW_MARK_REVISION_MISMATCH")
        if reviewed:
            self.records[key] = evidence
        else:
            self.records.pop(key, None)
        if before != self.records:
            self.revision += 1


class ReviewMarksTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000.0
        self.store = MemoryMarks()
        self.session = self.new_session()

    def new_session(self):
        return DOIReviewSession(
            clock=lambda: self.now,
            ttl_seconds=36000,
            as_of=lambda: "2026-10-07T15:00:00Z",
            review_mark_store=self.store,
        )

    def load(self, summaries=None, lines=None):
        left, right = fictional_csvs(summaries, lines)
        self.session.load(left, right, self.session.snapshot()["revision"])
        return self.session.reviewed_snapshot()

    def request(self, index=0, reviewed=True):
        state = self.session.reviewed_snapshot()
        order = state["orders"][index]
        return {
            "revision": state["revision"],
            "storage_revision": state["storage_revision"],
            "order_id": order["order_id"],
            "evidence_key": order["evidence_key"],
            "reviewed": reviewed,
        }

    def test_check_refresh_reopen_same_pair_and_uncheck(self):
        self.load()
        before = self.session.snapshot()
        marked = self.session.set_reviewed(self.request())
        self.assertEqual(marked["orders"][0]["status"], "REVIEWED")
        self.assertEqual(self.session.snapshot(), before)
        self.assertEqual(self.session.reviewed_snapshot(), marked)
        self.session.close()
        self.session = self.new_session()
        self.assertEqual(self.load()["orders"][0]["status"], "REVIEWED")
        state = self.session.set_reviewed(self.request(reviewed=False))
        self.assertEqual(state["orders"][0]["status"], "UNREVIEWED")
        self.assertEqual(self.store.records, {})
        self.assertEqual(self.load()["orders"][0]["status"], "UNREVIEWED")

    def test_clear_expiry_and_invalid_load_do_not_erase_saved_marker(self):
        self.load()
        self.session.set_reviewed(self.request())
        saved = copy.deepcopy(self.store.records)
        self.session.clear(self.session.snapshot()["revision"])
        self.assertEqual(self.store.records, saved)
        self.assertEqual(self.load()["orders"][0]["status"], "REVIEWED")
        self.now += 36000
        self.assertEqual(self.session.reviewed_snapshot()["orders"], [])
        self.assertEqual(self.store.records, saved)
        self.session.invalidate("REVIEW_JSON_INVALID")
        self.assertEqual(self.store.records, saved)
        self.assertEqual(self.load()["orders"][0]["status"], "REVIEWED")

    def test_new_capture_and_changed_stock_require_review_again(self):
        self.load()
        self.session.set_reviewed(self.request())
        for summaries, lines in (
            ([summary(captured_at_america_new_york="2026-10-06T10:00:00-04:00")], [line()]),
            ([summary()], [line(current_stock_icon_exact="IN STOCK")]),
            ([summary(original_source_rows="8")], [line(original_source_rows="8")]),
        ):
            with self.subTest(change=(summaries, lines)):
                state = self.load(summaries, lines)
                self.assertEqual(state["orders"][0]["status"], "CHANGED")
        self.session.set_reviewed(self.request())
        self.assertEqual(self.session.reviewed_snapshot()["orders"][0]["status"], "REVIEWED")
        self.assertEqual(self.load()["orders"][0]["status"], "CHANGED")

    def test_contact_email_is_excluded_from_fingerprint_and_retained_state(self):
        self.load()
        self.session.set_reviewed(self.request())
        state = self.load([summary(customer_info_email="another-fictional@example.test")])
        self.assertEqual(state["orders"][0]["status"], "REVIEWED")
        retained = json.dumps([state, self.store.records, self.session.snapshot()])
        self.assertNotIn("@example.test", retained)

    def test_row_order_and_unrelated_order_changes_cannot_move_checks(self):
        summaries = [summary(), summary("90000002")]
        lines = [line(), line("90000002")]
        self.load(summaries, lines)
        self.session.set_reviewed(self.request())
        state = self.load(list(reversed(summaries)), list(reversed(lines)))
        self.assertEqual(
            {o["order_id"]: o["status"] for o in state["orders"]},
            {"90000001": "REVIEWED", "90000002": "UNREVIEWED"},
        )
        state = self.load([summaries[0], summary("90000002", stock_eta_exact="SYN-change")], lines)
        self.assertEqual(state["orders"][0]["status"], "REVIEWED")

    def test_line_sort_preserves_same_evidence_binding(self):
        summaries = [summary(active_purchased_rows="2")]
        lines = [line(), line(line_identifier="SYN-LINE-2")]
        self.load(summaries, lines)
        self.session.set_reviewed(self.request())
        self.assertEqual(
            self.load(summaries, list(reversed(lines)))["orders"][0]["status"], "REVIEWED"
        )

    def test_duplicate_conflicting_and_unverified_ids_disable_marking(self):
        cases = (
            ([summary(), summary()], [line()]),
            ([summary(), summary(stock_eta_exact="SYN-change")], [line()]),
            ([summary(active_purchased_rows="2")], [line(), line()]),
            ([summary(active_purchased_rows="2")], [line(), line(sku="SYN-DIFFERENT")]),
            ([summary(displayed_order_id="90000002", order_id_matches_queue="no")], [line()]),
            ([summary(stock_eta_exact="=SYN-FORMULA")], [line()]),
        )
        for summaries, lines in cases:
            with self.subTest(case=summaries):
                state = self.load(summaries, lines)
                self.assertEqual(state["orders"][0]["status"], "AMBIGUOUS")
                self.assertIsNone(state["orders"][0]["evidence_key"])
                with self.assertRaisesRegex(ReviewMarkError, "EVIDENCE_MISMATCH"):
                    self.session.set_reviewed(self.request())
        self.assertEqual(self.store.records, {})

    def test_missing_components_can_be_reviewed_without_lifting_any_hold(self):
        self.load([summary(capture_complete="no")], [line(order_capture_complete="no")])
        before = self.session.snapshot()
        self.session.set_reviewed(self.request())
        self.assertEqual(self.session.snapshot(), before)
        self.assertFalse(before["orders"][0]["decision_eligible"])

    def test_stale_tab_store_revision_and_old_capture_are_rejected(self):
        self.load()
        stale = self.request()
        self.session.set_reviewed(stale)
        with self.assertRaisesRegex(ReviewMarkError, "REVISION_MISMATCH"):
            self.session.set_reviewed({**stale, "reviewed": False})
        self.load()
        with self.assertRaisesRegex(DOIReviewError, "REVISION_MISMATCH"):
            self.session.set_reviewed(stale)
        valid = self.request()
        for change in ({"evidence_key": "0" * 64}, {"order_id": "90000002"}):
            with self.assertRaisesRegex(ReviewMarkError, "EVIDENCE_MISMATCH"):
                self.session.set_reviewed({**valid, **change})

    def test_malformed_marker_requests_never_mutate_session(self):
        self.load()
        before = self.session.snapshot()
        request = self.request()
        for changes in ({"reviewed": "true"}, {"storage_revision": True}, {"extra": 1}):
            with self.assertRaises(ReviewMarkError):
                self.session.set_reviewed({**request, **changes})
        self.assertEqual(self.session.snapshot(), before)
        self.assertEqual(self.store.records, {})

    def test_storage_failure_leaves_review_and_deadline_intact_and_visible(self):
        self.load()
        request = self.request()
        before = self.session.snapshot()
        self.store.failed = True
        unavailable = self.session.reviewed_snapshot()
        self.assertFalse(unavailable["storage_available"])
        self.assertEqual(unavailable["orders"][0]["status"], "UNAVAILABLE")
        with self.assertRaisesRegex(ReviewMarkError, "UNAVAILABLE"):
            self.session.set_reviewed(request)
        self.assertEqual(self.session.snapshot(), before)

    def test_marker_reads_and_writes_do_not_renew_ten_hour_deadline(self):
        self.load()
        self.now += 35000
        self.session.set_reviewed(self.request())
        self.session.reviewed_snapshot()
        self.assertEqual(self.session.snapshot()["expires_in_seconds"], 1000)
        stale = self.request()
        self.now += 1000
        with self.assertRaisesRegex(DOIReviewError, "REVISION_MISMATCH"):
            self.session.set_reviewed(stale)
        self.assertEqual(self.session.snapshot()["status"], "expired")


class ReviewMarksHTTPTests(unittest.TestCase):
    request = review_ui_tests.ReviewHTTPTests.request
    tearDown = review_ui_tests.ReviewHTTPTests.tearDown

    def setUp(self):
        self.store = MemoryMarks()
        self.server = PortalHTTPServer(
            None,
            PortalServerConfig("127.0.0.1", 0),
            csrf_token="a" * 64,
            shutdown_token="b" * 64,
            doi_csv_review_only=True,
            review_mark_store=self.store,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]
        self.origin = f"http://127.0.0.1:{self.port}"
        left, right = fictional_csvs()
        self.server.doi_review_session.load(left, right, 0)

    def body(self):
        state = self.server.doi_review_session.reviewed_snapshot()
        return json.dumps(
            {
                "revision": state["revision"],
                "storage_revision": state["storage_revision"],
                "order_id": state["orders"][0]["order_id"],
                "evidence_key": state["orders"][0]["evidence_key"],
                "reviewed": True,
            }
        )

    def test_get_post_stale_conflict_and_failure_preserve_review(self):
        path = "/api/v1/doi-csv-review/reviewed"
        status, headers, body = self.request("GET", path + "-state")
        self.assertEqual(status, 200)
        self.assertIn("no-store", headers["Cache-Control"])
        original = self.server.doi_review_session.snapshot()
        request = self.body()
        status, _, body = self.request("POST", path, request)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["orders"][0]["status"], "REVIEWED")
        self.assertEqual(self.request("POST", path, request)[0], 409)
        request = self.body()
        self.store.failed = True
        self.assertEqual(self.request("POST", path, request)[0], 503)
        self.assertEqual(self.server.doi_review_session.snapshot()["orders"], original["orders"])

    def test_origin_csrf_body_shape_and_methods_remain_closed(self):
        path = "/api/v1/doi-csv-review/reviewed"
        body = self.body()
        for headers in ({"Origin": "https://example.test"}, {"X-SSA-CSRF-Token": "wrong"}):
            self.assertEqual(self.request("POST", path, body, headers)[0], 403)
        self.assertEqual(self.request("GET", path)[0], 405)
        self.assertEqual(self.request("POST", path + "-state", body)[0], 405)
        self.assertEqual(self.request("POST", path, '{"revision":1,"revision":1}')[0], 400)
        self.assertEqual(self.store.records, {})
        self.assertEqual(self.server.doi_review_session.snapshot()["counts"]["orders"], 1)
