"""Generated rep/order fixtures only; no captured customer data or actual order IDs."""

import copy
import unittest

from tests.test_csv_staging_independent import summary, line, stage, csv_text
from doi_csv_staging import SUMMARY_HEADERS, LINE_HEADERS
from doi_csv_staging.ownership import RepScopePolicy, classify_rep_scope, ELIGIBLE_REP_SCOPES, DEFAULT_REP_POLICY
from doi_csv_staging.review import DOIReviewSession, DOIReviewError, review_response_bytes


POLICY = RepScopePolicy(frozenset({"synthetic_owner_rep"}), frozenset({"customer-web"}),
                        frozenset({"synthetic_other_rep"}))


def rep_summary(order="90000001", rep="synthetic_owner_rep", **changes):
    return summary(order, displayed_sales_credit_field="ECS Sales Rep",
                   displayed_sales_credit_value=rep, **changes)


def scope(rep="synthetic_owner_rep", **changes):
    return classify_rep_scope(stage([rep_summary(rep=rep, **changes)]).orders[0], policy=POLICY)


def session(summaries, lines):
    return DOIReviewSession(as_of=lambda: "2026-10-05T22:25:59Z", rep_policy=POLICY).load(
        csv_text(SUMMARY_HEADERS, summaries), csv_text(LINE_HEADERS, lines), 0)


class OwnershipReviewTests(unittest.TestCase):
    def test_explicit_owner_is_in_scope_without_credit_or_fulfillment_decision(self):
        state = session([rep_summary()], [line(current_stock_icon_exact="In Stock")])
        order = state["orders"][0]
        self.assertEqual(order["rep_scope"], "OWNER")
        self.assertEqual(state["ownership_review"]["eligible_count"], 1)
        self.assertEqual(order["sales_credit_entitlement"], "UNINTERPRETED")
        self.assertFalse(order["decision_eligible"])
        self.assertFalse(order["split"]["quantity_verified"])

    def test_confirmed_other_rep_is_excluded_even_when_doi_reviewer_is_jude(self):
        state = session([rep_summary(rep="synthetic_other_rep", doi_review_assignment="Jude")], [line()])
        self.assertEqual(state["orders"][0]["rep_scope"], "OTHER_REP")
        self.assertEqual(state["orders"][0]["reviewer_assignment"], "Jude")
        self.assertEqual(state["ownership_review"]["excluded_count"], 1)
        self.assertEqual(state["ownership_review"]["eligible_count"], 0)

    def test_bare_customer_web_is_eligible_only_with_an_explicit_confirmed_mapping(self):
        order = stage([rep_summary(rep="customer-web")]).orders[0]
        self.assertEqual(classify_rep_scope(order, policy=POLICY), "UNASSIGNED_WEB")
        unconfirmed = RepScopePolicy(POLICY.owner_aliases, frozenset(), POLICY.known_other_aliases)
        self.assertEqual(classify_rep_scope(order, policy=unconfirmed), "REP_UNMAPPED")

    def test_approved_default_policy_is_exact_and_never_confirms_sales_credit(self):
        for value, expected in (("jlewis", "OWNER"), ("jlewis_web", "OWNER"), ("customer-web", "UNASSIGNED_WEB"),
                                ("akeesy", "OTHER_REP")):
            with self.subTest(value=value):
                state = DOIReviewSession(as_of=lambda: "2026-10-05T22:25:59Z").load(
                    csv_text(SUMMARY_HEADERS, [rep_summary(rep=value)]),
                    csv_text(LINE_HEADERS, [line()]), 0)
                self.assertEqual(state["orders"][0]["rep_scope"], expected)
                self.assertEqual(state["orders"][0]["sales_credit_entitlement"], "UNINTERPRETED")
                self.assertFalse(state["orders"][0]["decision_eligible"])

    def test_source_values_are_not_whitespace_normalized_or_case_folded(self):
        for value in (" customer-web", "customer-web ", "\tcustomer-web", "customer-web\r\n",
                      "Customer-Web", "CUSTOMER-WEB", " jlewis ", "AKEESY"):
            order = stage([rep_summary(rep=value)]).orders[0]
            self.assertEqual(classify_rep_scope(order, policy=DEFAULT_REP_POLICY), "REP_UNMAPPED")

    def test_multiline_and_lookalike_web_values_are_never_unassigned(self):
        for value in ("customer-web\nsynthetic_other_rep", "customer-web\r\nsynthetic_other_rep",
                      "customer-websynthetic_other_rep", "customer-web_synthetic_other_rep",
                      "customer-web/synthetic_other_rep", "customer\u2010web", "customer-web\u00a0"):
            order = stage([rep_summary(rep=value)]).orders[0]
            self.assertEqual(classify_rep_scope(order, policy=DEFAULT_REP_POLICY), "REP_UNMAPPED")

    def test_missing_summary_cannot_be_promoted_by_line_evidence(self):
        order = stage([], [line()]).orders[0]
        self.assertEqual(classify_rep_scope(order), "CAPTURE_UNVERIFIED")

    def test_owner_web_alias_does_not_authorize_any_near_match_or_combination(self):
        self.assertEqual(DEFAULT_REP_POLICY.owner_aliases, frozenset({"jlewis", "jlewis_web"}))
        for value in ("jlewisweb", "jlewis_web2", "customer-webjlewis", "jlewis-web",
                      "JLEWIS_WEB", " jlewis_web", "jlewis_web ", "jlewis\njlewis_web",
                      "customer-web\njlewis_web", "jlewis_web\nsynthetic_other_rep"):
            order = stage([rep_summary(rep=value)]).orders[0]
            self.assertEqual(classify_rep_scope(order), "REP_UNMAPPED")

    def test_no_prefix_suffix_case_or_friendly_name_alias_is_guessed(self):
        for value in ("customer-websynthetic_other_rep", "synthetic_owner_rep_web",
                      "SYNTHETIC_OWNER_REP", " synthetic_owner_rep", "Synthetic Owner", "Customer / Web"):
            with self.subTest(value=value):
                self.assertEqual(scope(value), "REP_UNMAPPED")

    def test_blank_rep_is_held_and_never_unassigned(self):
        self.assertEqual(scope(""), "REP_MISSING")
        self.assertEqual(scope(" "), "REP_UNMAPPED")

    def test_missing_or_wrong_field_is_held_even_with_owner_value(self):
        for field in ("", "Line Sales Rep", "ecs sales rep"):
            row = rep_summary()
            row["displayed_sales_credit_field"] = field
            self.assertEqual(classify_rep_scope(stage([row]).orders[0], policy=POLICY), "FIELD_UNVERIFIED")

    def test_unknown_and_ambiguous_rep_values_are_held(self):
        for value in ("synthetic_unknown_rep", "synthetic_owner_rep/synthetic_other_rep",
                      "synthetic_owner_rep;synthetic_other_rep", "unassigned_web"):
            self.assertEqual(scope(value), "REP_UNMAPPED")

    def test_conflicting_summary_rep_values_hold_the_order(self):
        order = stage([rep_summary(), rep_summary(rep="synthetic_other_rep")], [line()]).orders[0]
        self.assertEqual(classify_rep_scope(order, policy=POLICY), "REP_CONFLICT")

    def test_duplicate_summary_observation_is_not_promoted(self):
        order = stage([rep_summary(), rep_summary()], [line()]).orders[0]
        self.assertEqual(classify_rep_scope(order, policy=POLICY), "CAPTURE_UNVERIFIED")

    def test_unverified_capture_and_global_input_are_held(self):
        for changes in ({"capture_complete":"no"}, {"order_id_matches_queue":"no"},
                        {"snapshot_consistency_verified":"no"}, {"doi_source_assignment_conflict":"yes"}):
            self.assertEqual(scope(**changes), "CAPTURE_UNVERIFIED")
        order = stage([rep_summary()]).orders[0]
        self.assertEqual(classify_rep_scope(order, policy=POLICY, global_input_held=True), "CAPTURE_UNVERIFIED")

    def test_overlapping_or_malformed_policy_is_rejected(self):
        for args in ((frozenset({"synthetic_owner"}), frozenset({"synthetic_owner"}), frozenset()),
                     (frozenset({"<script>synthetic_owner"}), frozenset(), frozenset()),
                     ({"synthetic_owner"}, frozenset(), frozenset())):
            with self.assertRaisesRegex(ValueError, "REP_SCOPE_POLICY_INVALID"):
                RepScopePolicy(*args)

    def test_reconciliation_retains_every_eligible_excluded_and_held_order(self):
        summaries = [rep_summary("90000001"), rep_summary("90000002", "customer-web"),
                     rep_summary("90000003", "synthetic_other_rep"), rep_summary("90000004", "")]
        state = session(summaries, [line(str(90000000+i)) for i in range(1,5)])
        counts = state["ownership_review"]
        self.assertEqual((counts["order_count"], counts["eligible_count"], counts["excluded_count"], counts["held_count"]), (4,2,1,1))
        self.assertEqual(sum(counts["status_counts"].values()), 4)
        self.assertEqual(sum(counts["eligible_split_counts"].values()), 2)
        self.assertEqual(len(state["orders"]), 4)

    def test_full_total_ordering_after_ownership_filter_is_exact_and_cross_status(self):
        specs = [("90000001","synthetic_owner_rep","100.010001"),
                 ("90000002","synthetic_other_rep","9999"),
                 ("90000003","customer-web","100.010002"),
                 ("90000004","synthetic_unknown_rep","8888"),
                 ("90000005","synthetic_owner_rep","200")]
        summaries = [rep_summary(oid, rep, order_total_numeric=amount, order_total_displayed="$"+amount,
                                currency_symbol_displayed="$") for oid,rep,amount in specs]
        state = session(summaries, [line(oid, current_stock_icon_exact="In Stock" if oid=="90000001" else "") for oid,_,_ in specs])
        eligible = [o["order_id"] for o in state["orders"] if o["rep_scope"] in ELIGIBLE_REP_SCOPES]
        self.assertEqual(eligible, ["90000005","90000003","90000001"])

    def test_unknown_totals_sort_last_within_eligible_worklist(self):
        state = session([rep_summary("90000001"), rep_summary("90000002", order_total_numeric="1", order_total_displayed="$1", currency_symbol_displayed="$")],
                        [line("90000001"), line("90000002")])
        self.assertEqual([o["order_id"] for o in state["orders"]], ["90000002","90000001"])

    def test_mixed_ds_quantity_and_stock_unknowns_remain_unverified(self):
        state = session([rep_summary(active_purchased_rows="2")],
                        [line(drop_ship="yes", current_stock_icon_exact="In Stock"),
                         line(line_identifier="SYN-LINE-2", current_stock_icon_exact="Back Ordered")])
        order = state["orders"][0]
        self.assertEqual(order["rep_scope"], "OWNER")
        self.assertFalse(order["split"]["decision_eligible"])
        self.assertFalse(order["split"]["quantity_verified"])
        self.assertIn("ACTIVE_QUANTITY_UNVERIFIED", order["split"]["missing_fact_codes"])
        self.assertIn("FULL_ALLOCATION_NOT_CAPTURED", order["split"]["missing_fact_codes"])

    def test_customer_and_raw_rep_strings_do_not_enter_projection(self):
        marker = "SYN-PRIVATE-CUSTOMER <img src=x onerror=alert(1)>"
        state = session([rep_summary(rep=marker, customer_info_email=marker)], [line(product_name=marker)])
        encoded = review_response_bytes(state).decode("utf-8")
        self.assertNotIn(marker, encoded)
        self.assertNotIn("displayed_sales_credit_value", encoded)
        self.assertEqual(state["orders"][0]["rep_scope"], "REP_UNMAPPED")

    def test_closed_projection_rejects_scope_and_reconciliation_forgery(self):
        original = session([rep_summary()], [line()])
        for change in (lambda s:s["orders"][0].update(rep_scope="synthetic_owner_rep"),
                       lambda s:s["ownership_review"].update(eligible_count=True),
                       lambda s:s["ownership_review"].update(excluded_count=1),
                       lambda s:s["ownership_review"]["status_counts"].update(OWNER=0)):
            state = copy.deepcopy(original)
            change(state)
            with self.assertRaises(DOIReviewError):
                review_response_bytes(state)
