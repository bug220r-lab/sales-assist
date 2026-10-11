"""Generated fictional orders only; exact service metadata never proves availability."""

import unittest

from tests.test_csv_staging_independent import codes, csv_text, line, stage, summary
from doi_csv_staging import LINE_HEADERS, SUMMARY_HEADERS
from doi_csv_staging.review import DOIReviewSession
from doi_csv_staging.split_review import classify_split_order
from doi_csv_staging.staging import purchase_nature
from doi_csv_staging.triage import classify_order

SERVICE = "Service/charge based on explicit Service availability"
AS_OF = "2026-10-05T15:00:00Z"


def service(**changes):
    fields = dict(
        row_type="Purchased service/charge line",
        physical_or_service=SERVICE,
        line_identifier="SYN-SERVICE-1",
        current_stock_icon_exact="Service",
        product_name="Fictional service",
        each_price_displayed="19.95",
        purchased_line_total_displayed="19.95",
    )
    fields.update(changes)
    return line(**fields)


def review(summaries, rows):
    session = DOIReviewSession(as_of=lambda: AS_OF)
    result = session.load(csv_text(SUMMARY_HEADERS, summaries), csv_text(LINE_HEADERS, rows), 0)
    session.close()
    return result


class ServiceCaptureMappingTests(unittest.TestCase):
    def test_exact_alias_counts_service_subset_and_preserves_every_raw_field(self):
        rows = [
            line(current_stock_icon_exact="In Stock"),
            service(OH_displayed="7", OS_displayed="-3"),
        ]
        summaries = [
            summary(
                active_purchased_rows="2",
                separate_service_rows_displayed="1",
                order_total_displayed="$123.45",
                order_total_numeric="123.45",
                currency_symbol_displayed="$",
                currency_code="USD",
            )
        ]
        batch = stage(summaries, rows)
        self.assertTrue(batch.orders[0].visible_coverage_complete)
        self.assertNotIn("LINE_NATURE_UNKNOWN", codes(batch))
        self.assertNotIn("SUMMARY_LINE_COUNT_MISMATCH", codes(batch))
        self.assertEqual(dict(batch.line_occurrences[1].raw_fields), rows[1])
        self.assertEqual(batch.raw_lines_csv, csv_text(LINE_HEADERS, rows))
        state = review(summaries, rows)
        self.assertEqual(state["counts"]["purchased_records"], 2)
        self.assertEqual(state["counts"]["physical_purchased_records"], 1)
        self.assertEqual(state["counts"]["service_purchased_records"], 1)
        self.assertEqual(state["counts"]["component_records"], 0)
        self.assertEqual(state["orders"][0]["split"]["total"]["amount"], "123.45")
        self.assertEqual(state["orders"][0]["split"]["total"]["displayed"], "$123.45")
        self.assertFalse(state["orders"][0]["decision_eligible"])

    def test_only_exact_new_alias_is_accepted(self):
        for value in (
            SERVICE.lower(),
            SERVICE.upper(),
            " " + SERVICE,
            SERVICE + " ",
            SERVICE + "\n",
            SERVICE.replace("Service availability", "service availability"),
            SERVICE + "; physical merchandise",
            "Service availability",
            "Unknown",
            "",
        ):
            with self.subTest(value=value):
                self.assertIsNone(purchase_nature("Purchased service/charge line", value))
                batch = stage(
                    [summary(separate_service_rows_displayed="1")],
                    [service(physical_or_service=value)],
                )
                self.assertIn("LINE_NATURE_UNKNOWN", codes(batch))
                self.assertFalse(batch.orders[0].visible_coverage_complete)
                self.assertEqual(
                    dict(batch.line_occurrences[0].raw_fields)["physical_or_service"], value
                )

    def test_existing_service_contract_is_unchanged(self):
        for nature in (
            "service",
            "SERVICE",
            " service line ",
            "Explicit service/charge line",
            SERVICE,
        ):
            for role in (
                "purchased",
                "purchase",
                "purchased line",
                "service",
                "Purchased service/charge line",
            ):
                with self.subTest(nature=nature, role=role):
                    self.assertEqual(purchase_nature(role, nature), "service")

    def test_merchandise_kit_and_unknown_purchase_roles_remain_held(self):
        for role in (
            "Purchased merchandise line",
            "Purchased kit parent",
            "kit",
            "packaged product",
            "component",
            "kit component",
            "mystery",
        ):
            with self.subTest(role=role):
                rows = [service(row_type=role)]
                state = review([summary(separate_service_rows_displayed="1")], rows)
                self.assertIsNone(purchase_nature(role, SERVICE))
                self.assertEqual(state["counts"]["physical_purchased_records"], 0)
                self.assertEqual(state["counts"]["service_purchased_records"], 0)
                self.assertEqual(state["counts"]["component_records"], 0)
                self.assertFalse(state["orders"][0]["visible_coverage_complete"])
                self.assertEqual(state["orders"][0]["split"]["status"], "CAPTURE_HELD")

    def test_service_ready_or_waiting_labels_never_form_a_split_side(self):
        for service_stock, physical_stock in (
            ("In Stock", "Back Ordered"),
            ("Back Ordered", "In Stock"),
            ("Ships Today", "NLA"),
            ("Ships in 2 days", "In Stock"),
        ):
            with self.subTest(service_stock=service_stock):
                batch = stage(
                    [summary(active_purchased_rows="2", separate_service_rows_displayed="1")],
                    [
                        line(current_stock_icon_exact=physical_stock),
                        service(current_stock_icon_exact=service_stock),
                    ],
                )
                split = classify_split_order(batch.orders[0], as_of=AS_OF)
                self.assertNotEqual(split["status"], "APPARENT_SPLIT_CANDIDATE")
                self.assertEqual([item["record_ordinal"] for item in split["line_items"]], [2])
                for key in (
                    "ready_line_ordinals",
                    "waiting_line_ordinals",
                    "unresolved_line_ordinals",
                ):
                    self.assertNotIn(3, split[key])

    def test_service_only_has_no_merchandise_availability_or_split_signal(self):
        for stock in ("In Stock", "Back Ordered", "Ships on Jan 1, 2028", "Service"):
            batch = stage(
                [summary(separate_service_rows_displayed="1")],
                [
                    service(
                        current_stock_icon_exact=stock, product_eta_exact=stock, OH_displayed="999"
                    )
                ],
            )
            triage = classify_order(batch.orders[0], as_of=AS_OF)
            split = classify_split_order(batch.orders[0], as_of=AS_OF)
            self.assertFalse(
                set(triage["flags"])
                & {
                    "APPARENT_STOCK_PROGRESS_REVIEW",
                    "STOCK_TRANSFER_REVIEW",
                    "LEAD_TIME_AVAILABILITY_RESEARCH",
                }
            )
            self.assertEqual(split["line_items"], [])
            self.assertEqual(split["status"], "NO_SPLIT_PATTERN")
            self.assertFalse(split["decision_eligible"])

    def test_service_does_not_change_real_merchandise_split_or_order_total(self):
        rows = [
            line(current_stock_icon_exact="In Stock"),
            line(line_identifier="SYN-LINE-2", current_stock_icon_exact="Back Ordered"),
            service(current_stock_icon_exact="In Stock", ordered_quantity_displayed="999"),
        ]
        state = review(
            [
                summary(
                    active_purchased_rows="3",
                    separate_service_rows_displayed="1",
                    order_total_displayed="$219.95",
                    order_total_numeric="219.95",
                    currency_code="USD",
                    currency_symbol_displayed="$",
                )
            ],
            rows,
        )
        split = state["orders"][0]["split"]
        self.assertEqual(split["status"], "APPARENT_SPLIT_CANDIDATE")
        self.assertEqual(split["ready_line_ordinals"], [2])
        self.assertEqual(split["waiting_line_ordinals"], [3])
        self.assertEqual(split["total"]["amount"], "219.95")
        self.assertFalse(split["quantity_verified"])

    def test_service_does_not_supply_missing_kit_components(self):
        rows = [
            line(row_type="Purchased kit parent", current_stock_icon_exact="In Stock"),
            line(line_identifier="SYN-LINE-2", current_stock_icon_exact="Back Ordered"),
            service(current_stock_icon_exact="In Stock"),
        ]
        state = review(
            [summary(active_purchased_rows="3", separate_service_rows_displayed="1")], rows
        )
        self.assertEqual(state["counts"]["component_records"], 0)
        split = state["orders"][0]["split"]
        self.assertNotEqual(split["status"], "APPARENT_SPLIT_CANDIDATE")
        self.assertEqual(split["ready_line_ordinals"], [])
        self.assertIn("KIT_EVIDENCE_UNRESOLVED", split["reason_codes"])

    def test_service_linked_to_kit_is_invalid_purchase_not_component(self):
        rows = [
            line(row_type="Purchased kit parent", current_stock_icon_exact="In Stock"),
            service(parent_line_id="SYN-LINE-1", current_stock_icon_exact="In Stock"),
        ]
        state = review(
            [summary(active_purchased_rows="2", separate_service_rows_displayed="1")], rows
        )
        self.assertEqual(state["counts"]["component_records"], 0)
        self.assertEqual(state["counts"]["service_purchased_records"], 0)
        self.assertIn("LINE_STRUCTURE_CONFLICT", state["orders"][0]["holds"])
        self.assertEqual(state["orders"][0]["split"]["status"], "CAPTURE_HELD")

    def test_real_kit_components_remain_separate_from_services(self):
        rows = [
            line(row_type="Purchased kit parent", current_stock_icon_exact="In Stock"),
            line(line_identifier="SYN-LINE-2", current_stock_icon_exact="Back Ordered"),
            service(current_stock_icon_exact="In Stock"),
            line(
                row_type="component",
                counts_as_purchase="no",
                line_identifier="SYN-COMP-1",
                parent_line_id="SYN-LINE-1",
                component_coverage_complete="yes",
                component_quantity_required="1",
                current_stock_icon_exact="In Stock",
            ),
        ]
        state = review(
            [
                summary(
                    active_purchased_rows="3",
                    separate_service_rows_displayed="1",
                    visible_component_rows="1",
                    component_coverage="yes",
                )
            ],
            rows,
        )
        self.assertEqual(state["counts"]["physical_purchased_records"], 2)
        self.assertEqual(state["counts"]["service_purchased_records"], 1)
        self.assertEqual(state["counts"]["component_records"], 1)
        self.assertEqual(state["orders"][0]["split"]["ready_line_ordinals"], [2])
        self.assertEqual(state["orders"][0]["split"]["waiting_line_ordinals"], [3])

    def test_unknown_metadata_is_not_inferred_from_stock_or_product(self):
        row = service(
            physical_or_service="Unknown", product_name=SERVICE, current_stock_icon_exact="Service"
        )
        state = review([summary(separate_service_rows_displayed="1")], [row])
        self.assertEqual(state["counts"]["service_purchased_records"], 0)
        self.assertIn("LINE_NATURE_UNKNOWN", state["orders"][0]["holds"])
        self.assertEqual(state["orders"][0]["split"]["status"], "CAPTURE_HELD")

    def test_mapping_does_not_remove_incomplete_or_date_anomaly_holds(self):
        state = review(
            [
                summary(
                    active_purchased_rows="2",
                    separate_service_rows_displayed="1",
                    capture_complete="no",
                    missing_evidence_reason="Fictional missing kit evidence",
                    expected_arrival_date_exact="1999-09-14",
                )
            ],
            [
                line(order_capture_complete="no", current_stock_icon_exact="In Stock"),
                service(order_capture_complete="no"),
            ],
        )
        order = state["orders"][0]
        self.assertEqual(state["counts"]["service_purchased_records"], 1)
        self.assertEqual(order["rep_scope"], "CAPTURE_UNVERIFIED")
        self.assertEqual(order["split"]["status"], "CAPTURE_HELD")
        self.assertIn("ORDER_CAPTURE_INCOMPLETE", order["holds"])
        self.assertIn("ETA_YEAR_ANOMALY", order["evidence"]["reason_codes"])
        self.assertFalse(order["decision_eligible"])


if __name__ == "__main__":
    unittest.main()
