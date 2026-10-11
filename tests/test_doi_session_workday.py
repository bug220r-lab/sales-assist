"""Ten-hour app sessions using fictional CSVs, fake time, and loopback sockets."""

import unittest
from unittest.mock import patch

from doi_csv_staging.review import DOIReviewError, DOIReviewSession
from synthetic_sales_assist.portal import server as portal
from synthetic_sales_assist.portal.doi_csv_review_ui import render_doi_csv_review_page
from tests.test_doi_csv_review_ui import fictional_csvs
from tests.test_csv_staging_independent import line, summary


class WorkdayReviewTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000.0
        self.as_of = "2026-10-05T15:00:00Z"

    def app(self, review_only=False):
        def session_factory(**kwargs):
            return DOIReviewSession(clock=lambda: self.now, as_of=lambda: self.as_of, **kwargs)

        with patch.object(portal, "DOIReviewSession", side_effect=session_factory):
            app = portal.PortalHTTPServer(
                None,
                portal.PortalServerConfig("127.0.0.1", 0),
                csrf_token="a" * 64,
                shutdown_token="b" * 64,
                doi_csv_review_only=review_only,
            )
        self.addCleanup(app.server_close)
        return app.doi_review_session

    def load(self, session, order="90000001"):
        left, right = fictional_csvs([summary(order)], [line(order)])
        return session.load(left, right, session.snapshot()["revision"])

    def test_default_and_review_only_application_sessions_use_ten_hours(self):
        for review_only in (False, True):
            with self.subTest(review_only=review_only):
                state = self.load(self.app(review_only))
                self.assertEqual(state["expires_in_seconds"], 36000)
                self.assertEqual(state["counts"]["orders"], 1)

    def test_live_immediately_before_deadline_and_empty_at_exact_deadline(self):
        session = self.app()
        loaded = self.load(session)
        self.now += 35999.999
        before = session.snapshot()
        self.assertEqual(before["status"], loaded["status"])
        self.assertEqual(before["counts"]["orders"], 1)
        self.now = 37000.0
        expired = session.snapshot()
        self.assertEqual(expired["status"], "expired")
        self.assertEqual(expired["revision"], loaded["revision"] + 1)
        self.assertEqual(expired["orders"], [])
        self.assertEqual(expired["expires_in_seconds"], 0)

    def test_refresh_poll_and_revision_reads_never_extend_deadline(self):
        session = self.app()
        loaded = self.load(session)
        for elapsed in (1, 1800, 18000, 35999):
            self.now = 1000.0 + elapsed
            session.assert_revision(loaded["revision"])
            for _ in range(3):
                state = session.snapshot()
                self.assertEqual(state["expires_in_seconds"], 36000 - elapsed)
                self.assertEqual(state["split_review"]["as_of"], loaded["split_review"]["as_of"])
        self.now = 37000.0
        self.assertEqual(session.snapshot()["status"], "expired")

    def test_loading_a_new_pair_starts_a_new_fixed_deadline(self):
        session = self.app()
        first = self.load(session)
        self.now += 18000
        second = self.load(session, "90000002")
        self.assertEqual(second["revision"], first["revision"] + 1)
        self.assertEqual(second["expires_in_seconds"], 36000)
        self.assertEqual(second["orders"][0]["order_id"], "90000002")
        self.now = 37000.0
        self.assertEqual(session.snapshot()["expires_in_seconds"], 18000)
        self.now = 55000.0
        self.assertEqual(session.snapshot()["status"], "expired")

    def test_expired_revision_cannot_reload_or_restore_the_previous_review(self):
        session = self.app()
        loaded = self.load(session)
        self.now += 36000
        left, right = fictional_csvs()
        with self.assertRaisesRegex(DOIReviewError, "REVISION_MISMATCH"):
            session.load(left, right, loaded["revision"])
        self.assertEqual(session.snapshot()["orders"], [])

    def test_longer_session_preserves_stale_capture_warning_and_reference_time(self):
        self.as_of = "2026-10-07T15:00:00Z"
        session = self.app()
        loaded = self.load(session)
        evidence = loaded["orders"][0]["evidence"]
        self.assertIn("CAPTURE_STALE", evidence["reason_codes"])
        self.assertEqual(evidence["snapshot_age_status"], "STALE")
        self.assertGreater(evidence["snapshot_age_seconds"], 86400)
        self.now += 35999
        self.as_of = "2026-10-08T15:00:00Z"
        refreshed = session.snapshot()
        self.assertEqual(refreshed["orders"][0]["evidence"], evidence)
        self.assertEqual(refreshed["split_review"]["as_of"], loaded["split_review"]["as_of"])
        self.assertFalse(refreshed["orders"][0]["decision_eligible"])

    def test_both_rendered_modes_explain_ten_hours_without_changing_stale_warning(self):
        for review_only in (False, True):
            page = render_doi_csv_review_page("a" * 64, review_only=review_only).decode()
            self.assertIn("10 hours from loading", page)
            self.assertIn("Refreshing or sorting does not extend this window", page)
            self.assertNotIn("after 30 minutes", page)
            self.assertIn("A snapshot older than 24 hours is marked stale", page)
