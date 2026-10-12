"""Synthetic discovery integration, response boundaries and unchanged saved attention."""

import copy
import tempfile
import unittest
from pathlib import Path

from doi_csv_staging.review import DOIReviewError, DOIReviewSession, review_response_bytes
from doi_csv_staging.review_marks import ReviewMarkStore, evidence_key
from tests.test_csv_staging_independent import line, stage, summary
from tests.test_doi_csv_review_ui import fictional_csvs


def held_pair():
    return fictional_csvs(
        [
            summary(active_purchased_rows="2", doi_source_assignment_conflict="yes"),
            summary("90000002", doi_source_assignment_conflict="yes"),
        ],
        [
            line(current_stock_icon_exact="In Stock"),
            line(line_identifier="SYN-LINE-2", current_stock_icon_exact="Back Ordered"),
            line("90000002", ordered_quantity_displayed="3", OH_displayed="1"),
        ],
    )


class DiscoverySessionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="SYN-discovery-")
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "doi-reviewed-split.json"
        self.now = 1000.0
        self.store = ReviewMarkStore(self.path)
        self.session = self.new_session()

    def new_session(self):
        return DOIReviewSession(
            clock=lambda: self.now,
            ttl_seconds=36000,
            as_of=lambda: "2026-10-07T15:00:00Z",
            review_mark_store=self.store,
        )

    def load(self):
        return self.session.load(*held_pair(), self.session.snapshot()["revision"])

    def test_discovery_keeps_original_scope_holds_and_fulfillment_projection(self):
        state = self.load()
        self.assertEqual(state["schema"], "doi-csv-review/v6")
        pattern, stock = state["orders"]
        self.assertEqual(pattern["discovery"]["category"], "HELD_MIXED_LABELS")
        self.assertEqual(stock["discovery"]["category"], "STOCK_COUNTER_CLUE")
        for order in state["orders"]:
            self.assertEqual(order["rep_scope"], "CAPTURE_UNVERIFIED")
            self.assertEqual(order["split"]["status"], "CAPTURE_HELD")
            self.assertIn("SOURCE_ASSIGNMENT_CONFLICT_OR_UNKNOWN", order["holds"])
            self.assertFalse(order["decision_eligible"])
            self.assertFalse(order["discovery"]["decision_eligible"])
            self.assertFalse(order["discovery"]["quantity_verified"])
            self.assertFalse(order["split"]["quantity_verified"])
            self.assertEqual(order["split"]["ready_line_ordinals"], [])
            self.assertEqual(order["split"]["waiting_line_ordinals"], [])
        self.assertEqual(state["ownership_review"]["held_count"], 2)
        self.assertEqual(state["ownership_review"]["eligible_count"], 0)
        self.assertEqual(state["split_review"]["confirmed_split_count"], 0)
        self.assertEqual(state["split_review"]["status_counts"]["CAPTURE_HELD"], 2)
        self.assertNotIn(b"fictional@example.test", review_response_bytes(state))

    def test_discovery_reads_and_reload_preserve_real_saved_store_bytes_and_bindings(self):
        self.load()
        before = self.session.reviewed_snapshot()
        for item in before["orders"]:
            current = self.session.reviewed_snapshot()
            self.session.set_reviewed(
                {
                    "revision": current["revision"],
                    "storage_revision": current["storage_revision"],
                    "order_id": item["order_id"],
                    "evidence_key": item["evidence_key"],
                    "reviewed": True,
                }
            )
        saved = self.path.read_bytes()
        bindings = {o["order_id"]: o["evidence_key"] for o in before["orders"]}
        self.now += 100
        snapshot = self.session.snapshot()
        for _ in range(3):
            review_response_bytes(self.session.snapshot())
            self.assertEqual(self.session.snapshot(), snapshot)
            self.assertEqual(self.path.read_bytes(), saved)
        self.assertEqual(snapshot["expires_in_seconds"], 35900)
        self.session.clear(snapshot["revision"])
        self.assertEqual(self.path.read_bytes(), saved)
        self.session.close()
        self.store = ReviewMarkStore(self.path)
        self.session = self.new_session()
        self.load()
        restored = self.session.reviewed_snapshot()
        self.assertTrue(all(o["status"] == "REVIEWED" for o in restored["orders"]))
        self.assertEqual({o["order_id"]: o["evidence_key"] for o in restored["orders"]}, bindings)
        self.assertEqual(self.path.read_bytes(), saved)

    def test_discovery_never_changes_raw_evidence_key(self):
        raw = stage(
            [summary(active_purchased_rows="2", doi_source_assignment_conflict="yes")],
            [
                line(current_stock_icon_exact="In Stock"),
                line(line_identifier="SYN-LINE-2", current_stock_icon_exact="Back Ordered"),
            ],
        ).orders[0]
        state = self.load()
        marks = self.session.reviewed_snapshot()
        self.assertEqual(marks["orders"][0]["evidence_key"], evidence_key(raw))
        # The existing configured USD policy removes only this source currency hold.
        self.assertEqual(state["orders"][0]["holds"], sorted(set(raw.holds) - {"CURRENCY_UNKNOWN"}))

    def test_closed_serializer_rejects_forged_discovery_authority_and_references(self):
        original = self.load()
        cases = [
            lambda o: o["discovery"].update(decision_eligible=True),
            lambda o: o["discovery"].update(quantity_verified=True),
            lambda o: o["discovery"].update(customer_email="synthetic@example.test"),
            lambda o: o["discovery"].update(ready_line_ordinals=[5001]),
            lambda o: o["discovery"].update(waiting_line_ordinals=[2]),
            lambda o: o["holds"].remove("SOURCE_ASSIGNMENT_CONFLICT_OR_UNKNOWN"),
            lambda o: o["holds"].append("DISPLAYED_ORDER_ID_UNVERIFIED"),
            lambda o: o["holds"].append("ORDER_CAPTURE_INCOMPLETE"),
            lambda o: o["split"]["reason_codes"].append("TERMINAL_ORDER_OBSERVED"),
            lambda o: o["split"]["line_items"][0].update(ds="YES"),
            lambda o: o["split"]["line_items"][0].update(current_stock="Back Ordered"),
        ]
        for change in cases:
            state = copy.deepcopy(original)
            change(state["orders"][0])
            with (
                self.subTest(change=change),
                self.assertRaisesRegex(DOIReviewError, "REVIEW_RESPONSE_INVALID"),
            ):
                review_response_bytes(state)

    def test_stock_clue_is_bounded_observation_and_cannot_be_upgraded_by_payload(self):
        original = self.load()
        clue = original["orders"][1]["discovery"]["stock_clues"][0]
        self.assertEqual(clue, {"record_ordinal": 4, "ordered": "3", "oh": "1"})
        for field, value in (
            ("oh", "3"),
            ("ordered", "0"),
            ("oh", "1e2"),
            ("oh", "-1"),
            ("record_ordinal", True),
            ("allocated", "1"),
        ):
            state = copy.deepcopy(original)
            state["orders"][1]["discovery"]["stock_clues"][0][field] = value
            with (
                self.subTest(field=field, value=value),
                self.assertRaisesRegex(DOIReviewError, "REVIEW_RESPONSE_INVALID"),
            ):
                review_response_bytes(state)
