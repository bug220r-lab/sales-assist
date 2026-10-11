"""Synthetic CSV, concurrency, journal, and closed API boundary regressions."""

from __future__ import annotations

import copy
import csv
import io
import json
import os
import tempfile
import threading
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from doi_draft_transfer.contract import (
    CHECKS,
    CTA_TEXT,
    CTA_URL,
    HEADERS,
    MAX_CELL,
    MAX_CSV,
    MAILBOX_ID,
    SCHEMA,
    SIGNATURE,
    USER_ID,
    TransferError,
    approval_binding,
    cart_components,
    cart_holds,
    digest,
    fresh_review,
    parse_csv,
    rendered_body,
    review_holds,
    row_holds,
    subject_for,
    template_csv,
    text_hash,
    valid_email,
    validate_review,
)
from doi_draft_transfer.helpscout import HelpScoutDraftClient, body_text, payload_for, safe_web_link
from doi_draft_transfer.service import DraftTransferService
from doi_draft_transfer.store import DraftTransferStore, FILENAME


def synthetic_row(oid="90000001"):
    """Reserved dummy order/product values and example.test recipient; never fetched."""
    url = (
        "https://www.ecstuning.com/Cart/?add1=99000001&qty1=2&utm_source=jlewis"
        "&utm_medium=email&utm_content=link2cart&salesrep=jlewis"
    )
    components = [{"es": "99000001", "sku": "SYN-DUMMY-BRACKET", "sale_quantity": 2}]
    body = (
        'Hello!\n\nSynthetic fixture — café, 日本語, "quoted" alternative.\n'
        + url
        + "\n\n"
        + SIGNATURE
        + "\n"
        + CTA_TEXT
        + "\n"
        + CTA_URL
    )
    row = {key: "" for key in HEADERS}
    row.update(source_days_json='["SYN-DAY"]', source_provenance_json='{"kind":"SYN"}')
    row.update(
        schema_version=SCHEMA,
        order_id=oid,
        subject=subject_for(oid),
        selected_body_text=body,
        preserved_original_body_text=body,
        source_body_sha256=text_hash(body),
        selected_body_sha256=text_hash(body),
        preserved_original_rich_text_runs_json="[]",
        copy_version="SYN-COPY-1",
        recipient_email="synthetic.recipient@example.test",
        recipient_verified="true",
        draft_status="PENDING",
        review_approval="APPROVED",
        send_ready="true",
        review_holds_json='["SYN explicit review required"]',
        review_gate_state_json="{}",
        source_order_lines_json='[{"line_id":"SYN-LINE-1","source_quantity":"2"}]',
        alternates_json=json.dumps(
            [
                {
                    "option_id": "SYN-OPTION-1",
                    "label": "Synthetic option",
                    "cart_url": url,
                    "components": components,
                    "mapping_status": "SYN-MAPPED",
                    "content_status": "UNVERIFIED_SCHEMA_MAPPED_CART",
                    "validated_at_utc": None,
                }
            ]
        ),
        alternate_relationship="SINGLE_OPTION",
        complete_recipe_json="null",
        cart_links_json=json.dumps(
            [
                {
                    "option_id": "SYN-OPTION-1",
                    "url": url,
                    "components": components,
                    "content_status": "UNVERIFIED_SCHEMA_MAPPED_CART",
                }
            ]
        ),
        cart_validation_status="UNVERIFIED_SCHEMA_MAPPED_CART",
        current_rep="jlewis",
        current_order_status="Open",
        observed_at_utc="2026-10-11T00:00:00Z",
    )
    return row


def csv_text(rows, headers=HEADERS):
    out = io.StringIO(newline="")
    writer = csv.writer(out, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    writer.writerow(headers)
    for row in rows:
        writer.writerow([row[key] for key in headers])
    return out.getvalue()


def verified_review():
    review = fresh_review()
    review.update(
        recipient_verified=True,
        recipient_provenance="SYN manually verified example.test",
        holds_reviewed=True,
        holds_review_note="SYN holds explicitly reviewed",
        duplicate_status="no_existing_draft",
        duplicate_evidence="SYN local duplicate check found no existing draft",
    )
    review["checks"] = {
        key: {"resolved": True, "evidence": "SYN reviewer evidence"} for key in CHECKS
    }
    review["checks"]["customer_approval"] = {
        "decision": "approval_recorded",
        "conditional_copy_reviewed": False,
        "evidence": "SYN recorded customer approval evidence",
    }
    review["carts"] = {
        "SYN-OPTION-1": {
            "verified": True,
            "evidence": "SYN exact cart mapping evidence",
            "observed_at_utc": "2026-10-11T00:00:00Z",
        }
    }
    return review


def large_synthetic_csv():
    """Generate the producer-sized shape in memory, never using private source data."""
    rows = [synthetic_row(str(90000001 + i)) for i in range(492)]
    base = json.dumps({"synthetic": "SYN \u03a9\n", "unknown": None}, indent=2, ensure_ascii=False)

    def provenance(length):
        return json.dumps(
            {"synthetic": "SYN \u03a9\n" + "x" * (length - len(base)), "unknown": None},
            indent=2,
            ensure_ascii=False,
        )

    for index, row in enumerate(rows):
        row.update(
            recipient_email="",
            recipient_verified="false",
            send_ready="false",
            review_approval="PENDING",
            source_provenance_json=base,
        )
        if index >= 150:
            row.update(
                selected_body_text="", selected_body_sha256=text_hash(""), draft_status="HELD"
            )
    rows[0]["source_provenance_json"] = provenance(262905)
    remaining = 15400000 - len(csv_text(rows).encode("utf-8-sig"))
    increment, remainder = divmod(remaining, len(rows) - 1)
    for index, row in enumerate(rows[1:]):
        row["source_provenance_json"] = provenance(len(base) + increment + (index < remainder))
    value = "\ufeff" + csv_text(rows)
    assert len(value.encode("utf-8")) == 15400000
    assert max(len(row["source_provenance_json"]) for row in rows) == 262905
    return rows, value


class MockClient:
    def __init__(self):
        self.calls = []
        self.result = {
            "state": "CREATED",
            "code": "DRAFT_CREATED_VERIFIED",
            "retry_allowed": False,
            "conversation_id": "99000001",
            "web_link": "https://secure.helpscout.net/conversation/99000001/1",
        }

    def create_draft(self, row):
        self.calls.append(payload_for(row))
        return dict(self.result)

    def verify_draft(self, row, result):
        return {**result, "state": "CREATED"}

    def check_destination(self):
        return {"verified": True}


class ContractTests(unittest.TestCase):
    def test_customer_decision_requires_explicit_path_and_conditional_copy_review(self):
        row, review = synthetic_row(), verified_review()
        customer = review["checks"]["customer_approval"]
        customer.update(decision="pending_conditional_outreach", conditional_copy_reviewed=False)
        self.assertIn("CONDITIONAL_OUTREACH_COPY_REVIEW_REQUIRED", review_holds(row, review))
        customer.update(
            conditional_copy_reviewed=True, evidence="SYN pending; exact copy asks for consent"
        )
        self.assertEqual(review_holds(row, review), [])
        customer["evidence"] = ""
        self.assertIn("CUSTOMER_DECISION_EVIDENCE_REQUIRED", review_holds(row, review))
        review["checks"]["customer_approval"] = {"resolved": True, "evidence": "SYN old review"}
        self.assertIn("REVIEW_CUSTOMER_DECISION_REQUIRED", review_holds(row, review))
        with self.assertRaisesRegex(TransferError, "CUSTOMER_DECISION_REVIEW_INVALID"):
            validate_review(review)
        review["checks"]["customer_approval"] = {
            "decision": "automatically_approved",
            "evidence": "SYN",
            "conditional_copy_reviewed": True,
        }
        with self.assertRaisesRegex(TransferError, "CUSTOMER_DECISION_REVIEW_INVALID"):
            validate_review(review)

    def test_pending_customer_decision_preserves_hard_gates(self):
        row, review = synthetic_row(), verified_review()
        review["checks"]["customer_approval"].update(
            decision="pending_conditional_outreach",
            conditional_copy_reviewed=True,
            evidence="SYN pending customer choice; exact conditional wording reviewed",
        )
        cases = (
            (
                "identity",
                lambda r, v: v["checks"]["identity"].update(resolved=False),
                "REVIEW_IDENTITY",
            ),
            (
                "recipient",
                lambda r, v: v.update(recipient_verified=False),
                "RECIPIENT_REVIEW_REQUIRED",
            ),
            ("blank recipient", lambda r, v: r.update(recipient_email=""), "RECIPIENT_REQUIRED"),
            ("status", lambda r, v: r.update(current_order_status="Shipped"), "ORDER_STATUS_HELD"),
            ("withheld", lambda r, v: r.update(draft_status="HELD"), "SOURCE_COPY_HELD"),
            ("cart", lambda r, v: r.update(cart_links_json="[]"), "NO_VERIFIED_CART"),
            (
                "scope",
                lambda r, v: v["checks"]["kit_scope"].update(resolved=False),
                "REVIEW_KIT_SCOPE",
            ),
        )
        for label, mutate, expected in cases:
            with self.subTest(gate=label):
                candidate, evidence = copy.deepcopy(row), copy.deepcopy(review)
                mutate(candidate, evidence)
                self.assertIn(expected, review_holds(candidate, evidence))

    def test_large_multiline_provenance_and_exact_body_hashes(self):
        row = synthetic_row()
        row["source_provenance_json"] = json.dumps(
            {"synthetic": "SYN\u03a9\n" * 60000, "unknown": None},
            ensure_ascii=False,
            indent=2,
        )
        self.assertGreater(len(row["source_provenance_json"]), 262905)
        row["selected_body_text"] += "\r\nSYN \u03a9"
        row["selected_body_sha256"] = text_hash(row["selected_body_text"])
        parsed, errors = parse_csv("\ufeff" + csv_text([row]))
        self.assertEqual(errors, [])
        self.assertEqual(parsed, [row])
        self.assertEqual(text_hash(parsed[0]["selected_body_text"]), row["selected_body_sha256"])
        row["source_provenance_json"] = json.dumps({"synthetic": "x" * MAX_CELL})
        self.assertTrue(parse_csv(csv_text([row]))[1])

    def test_final_contract_optional_sku_and_no_selected_alternate(self):
        row = synthetic_row()
        for field in ("alternates_json", "cart_links_json"):
            value = json.loads(row[field])
            for option in value:
                for component in option["components"]:
                    component.pop("sku")
                option.update(browser_restoration_verified=None, validation_evidence=None)
            row[field] = json.dumps(value)
        self.assertEqual(parse_csv(csv_text([row]))[1], [])
        self.assertEqual(cart_holds(row), [])
        row["alternate_relationship"] = "NO_SELECTED_ALTERNATE"
        self.assertIn("NO_SELECTED_ALTERNATE", cart_holds(row))
        review = fresh_review()
        review["duplicate_status"] = []
        with self.assertRaisesRegex(TransferError, "DUPLICATE_REVIEW_INVALID"):
            validate_review(review)

    def test_final_contract_history_fields_and_empty_selected_hash_roundtrip(self):
        row = synthetic_row()
        row.update(
            selected_body_text="",
            selected_body_sha256=text_hash(""),
            pre_cart_requirement_body_text='SYN history\r\n"quoted", Unicode \u03a9',
            source_alternate_relationship="SYN source relationship",
            existing_help_scout_reference="SYN untrusted prior-reference",
            help_scout_draft_id="99000009",
            current_rep_eligibility="SYN claim only",
            source_provenance_json='{"source":"SYN","reviewed":false,"unknown":null}',
        )
        parsed, errors = parse_csv("\ufeff" + csv_text([row]))
        self.assertEqual(errors, [])
        self.assertEqual(parsed, [row])
        self.assertIn("NO_SELECTED_COPY", review_holds(row, fresh_review()))
        self.assertIn("DUPLICATE_RECONCILIATION_REQUIRED", review_holds(row, fresh_review()))
        row["selected_body_sha256"] = ""
        self.assertIn("EXACT_BODY_SHA256_MISMATCH", str(parse_csv(csv_text([row]))[1]))

    def test_final_contract_types_unknown_header_and_malformed_cart_fail_closed(self):
        row = synthetic_row()
        row["source_days_json"] = "{}"
        self.assertTrue(parse_csv(csv_text([row]))[1])
        row = synthetic_row()
        row["unexpected_column"] = "SYN"
        self.assertTrue(parse_csv(csv_text([row], HEADERS + ("unexpected_column",)))[1])
        row = synthetic_row()
        row["cart_links_json"] = '[null,{"option_id":[],"url":null}]'
        self.assertTrue(review_holds(row, fresh_review()))

    def test_final_contract_492_rows_150_selected_fit_import_bounds(self):
        self.assertEqual(len(HEADERS), 34)
        rows = [synthetic_row(str(90000001 + i)) for i in range(492)]
        rows[0]["source_provenance_json"] = json.dumps(
            {"synthetic": "SYN\u03a9\n" * 60000}, ensure_ascii=False, indent=2
        )
        self.assertGreater(len(rows[0]["source_provenance_json"]), 262905)
        for index, row in enumerate(rows):
            row.update(recipient_email="", recipient_verified="false", send_ready="false")
            if index >= 150:
                row.update(selected_body_text="", selected_body_sha256=text_hash(""))
        parsed, errors = parse_csv("\ufeff" + csv_text(rows))
        self.assertEqual(errors, [])
        self.assertEqual(parsed, rows)
        self.assertEqual(sum(bool(row["selected_body_text"]) for row in parsed), 150)
        self.assertEqual(sum(not row["selected_body_text"] for row in parsed), 342)

    def test_imported_help_scout_reference_requires_local_duplicate_resolution(self):
        row = synthetic_row()
        row.update(existing_help_scout_reference="SYN reference", help_scout_draft_id="99000009")
        review = verified_review()
        review["duplicate_status"] = "unresolved"
        self.assertIn("DUPLICATE_RECONCILIATION_REQUIRED", review_holds(row, review))
        review["duplicate_status"] = "existing_draft_found"
        self.assertIn("DUPLICATE_RECONCILIATION_REQUIRED", review_holds(row, review))
        review["duplicate_status"] = "no_existing_draft"
        self.assertNotIn("DUPLICATE_RECONCILIATION_REQUIRED", review_holds(row, review))

    def test_multiline_unicode_urls_quotes_and_crlf_exact_hashes(self):
        row = synthetic_row()
        for field in ("selected_body_text", "preserved_original_body_text"):
            row[field] = row[field].replace("\n", "\r\n")
        row["source_body_sha256"] = text_hash(row["preserved_original_body_text"])
        row["selected_body_sha256"] = text_hash(row["selected_body_text"])
        parsed, errors = parse_csv("\ufeff" + csv_text([row]))
        self.assertEqual(errors, [])
        self.assertEqual(parsed, [row])
        self.assertNotEqual(
            text_hash(row["selected_body_text"].replace("\r\n", "\n")), row["selected_body_sha256"]
        )

    def test_header_template_exact_required_columns_and_order_independence(self):
        self.assertEqual(len(HEADERS), 34)
        self.assertTrue(template_csv().startswith("\ufeff"))
        self.assertEqual(
            next(csv.reader(io.StringIO(template_csv().lstrip("\ufeff")))), list(HEADERS)
        )
        self.assertEqual(parse_csv(csv_text([synthetic_row()], tuple(reversed(HEADERS))))[1], [])
        self.assertTrue(parse_csv(csv_text([synthetic_row()], HEADERS[:-1]))[1])
        self.assertTrue(parse_csv(csv_text([synthetic_row()], HEADERS[:-1] + (HEADERS[0],)))[1])

    def test_duplicate_rows_and_malformed_json_reject_without_echo(self):
        row = synthetic_row()
        _, errors = parse_csv(csv_text([row, row]))
        self.assertIn("DUPLICATE_ORDER_ID", str(errors))
        row["alternates_json"] = '{"secret":"SYN","secret":"SYN2"}'
        _, errors = parse_csv(csv_text([row]))
        self.assertIn("JSON_ARRAY_OR_OBJECT_REQUIRED", str(errors))
        self.assertNotIn("SYN2", str(errors))

    def test_malformed_csv_utf8_surrogate_and_oversize(self):
        self.assertTrue(parse_csv(template_csv() + '"unterminated')[1])
        with self.assertRaises(TransferError):
            parse_csv("\ud800")
        with self.assertRaises(TransferError):
            parse_csv("x" * (MAX_CSV + 1))

    def test_hashes_bind_exact_body_and_no_original_fallback(self):
        row = synthetic_row()
        row["selected_body_text"] = ""
        row["selected_body_sha256"] = text_hash("")
        self.assertEqual(parse_csv(csv_text([row]))[1], [])
        self.assertIn("NO_SELECTED_COPY", row_holds(row))
        row["preserved_original_body_text"] += " "
        self.assertIn("EXACT_BODY_SHA256_MISMATCH", str(parse_csv(csv_text([row]))[1]))

    def test_nullable_json_and_original_allowed_but_unknown_scope_held(self):
        row = synthetic_row()
        row.update(
            preserved_original_body_text="",
            source_body_sha256="",
            source_order_lines_json="null",
            review_gate_state_json="null",
            observed_at_utc="",
        )
        self.assertEqual(parse_csv(csv_text([row]))[1], [])
        self.assertIn("SOURCE_LINE_SCOPE_UNKNOWN", row_holds(row))
        self.assertIn("CURRENT_ORDER_OBSERVATION_REQUIRED", row_holds(row))

    def test_imported_approval_claims_never_resolve_review(self):
        row = synthetic_row()
        self.assertEqual(row_holds(row), [])
        self.assertIn("RECIPIENT_REVIEW_REQUIRED", review_holds(row, fresh_review()))
        self.assertEqual(review_holds(row, verified_review()), [])

    def test_ownership_and_closed_status_hard_gates(self):
        for rep in ("jlewis", "jlewis_web", "customer-web"):
            row = synthetic_row()
            row["current_rep"] = rep
            self.assertNotIn("REP_ELIGIBILITY_HELD", row_holds(row))
        for rep in ("", "another-rep", "jlewis, another-rep", "unknown"):
            row = synthetic_row()
            row["current_rep"] = rep
            self.assertIn("REP_ELIGIBILITY_HELD", row_holds(row))
        for status in ("Shipped", "Canceled", "DS Pending Cancel", "canceled "):
            row = synthetic_row()
            row["current_order_status"] = status
            self.assertIn("ORDER_STATUS_HELD", row_holds(row))

    def test_cart_exact_numeric_components_scope_tags_and_no_variants_inferred(self):
        row = synthetic_row()
        url = json.loads(row["cart_links_json"])[0]["url"]
        self.assertEqual(cart_components(url), {"99000001": 2})
        for bad in (
            url.replace("add1=99000001", "add1=ES99000001"),
            url + "&qty1=2",
            url.replace("salesrep=jlewis", "salesrep=someone"),
            url.replace("https://", "http://"),
            url + "#fragment",
            url.replace("www.ecstuning.com", "evil.example.test"),
        ):
            with self.subTest(url=bad), self.assertRaises((ValueError, TransferError)):
                cart_components(bad)
        carts = json.loads(row["cart_links_json"])
        carts[0]["url"] = url.replace("qty1=2", "qty1=3")
        row["cart_links_json"] = json.dumps(carts)
        self.assertIn("CART_COMPONENT_MISMATCH", cart_holds(row))

    def test_mutually_exclusive_options_remain_separate(self):
        row = synthetic_row()
        options = json.loads(row["alternates_json"])
        second = copy.deepcopy(options[0])
        second["option_id"] = "SYN-OPTION-2"
        second["cart_url"] = second["cart_url"].replace("99000001", "99000002")
        second["components"][0]["es"] = "99000002"
        options.append(second)
        row["alternates_json"] = json.dumps(options)
        carts = [
            {
                "option_id": o["option_id"],
                "url": o["cart_url"],
                "components": o["components"],
                "content_status": "UNVERIFIED_SCHEMA_MAPPED_CART",
            }
            for o in options
        ]
        row["cart_links_json"] = json.dumps(carts)
        row["alternate_relationship"] = "MUTUALLY_EXCLUSIVE_OPTIONS"
        self.assertEqual(cart_holds(row), [])
        row["cart_links_json"] = json.dumps(carts[:1])
        self.assertIn("CART_OPTION_MISSING", cart_holds(row))

    def test_joint_recipe_requires_all_components_and_scope_basis(self):
        row = synthetic_row()
        components = json.loads(row["alternates_json"])[0]["components"]
        row["alternate_relationship"] = "JOINT_COMPLETE_RECIPE"
        self.assertIn("INCOMPLETE_RECIPE", cart_holds(row))
        recipe = {
            "kind": "SYN-DUMMY-KIT",
            "options": [{"option_id": "SYN-OPTION-1", "components": components}],
            "scope_basis": "SYN full-kit review",
            "holds": [],
        }
        row["complete_recipe_json"] = json.dumps(recipe)
        self.assertEqual(cart_holds(row), [])
        recipe["options"][0]["components"][0]["sale_quantity"] = 3
        row["complete_recipe_json"] = json.dumps(recipe)
        self.assertIn("RECIPE_COMPONENT_MISMATCH", cart_holds(row))

    def test_recipient_header_injection_and_html_escape(self):
        for email in (
            "",
            "x@example.test\r\nBcc:x@example.test",
            "Name <x@example.test>",
            "a@-example.test",
            "a@example..test",
        ):
            self.assertFalse(valid_email(email))
        body = '<script>alert("SYN")</script>\n' + synthetic_row()["selected_body_text"]
        rendered = rendered_body(body)
        self.assertNotIn("<script>", rendered)
        self.assertEqual(body_text(rendered), body)


class StoreTests(unittest.TestCase):
    def setUp(self):
        root = Path(os.environ.get("SSA_TRANSFER_TEST_ROOT", tempfile.gettempdir()))
        self.folder = root / ("ssa-synthetic-transfer-" + uuid.uuid4().hex)
        self.folder.mkdir(parents=True)
        self.path = self.folder / FILENAME
        self.store = DraftTransferStore(self.path)
        self.client = MockClient()
        self.service = DraftTransferService(self.store, self.client)

    def tearDown(self):
        for path in self.folder.iterdir():
            self.assertIn(
                path.name, {FILENAME, FILENAME + "-journal", FILENAME + "-wal", FILENAME + "-shm"}
            )
            path.unlink()
        self.folder.rmdir()

    def imported(self, row=None):
        preview = self.service.preview_import(csv_text([row or synthetic_row()]))
        self.assertEqual(preview["errors"], [])
        self.service.commit_import(preview["preview_token"], preview["revision"])
        return self.service.detail("90000001")

    def reviewed(self):
        item = self.imported()
        self.service.edit(
            item["order_id"],
            item["version"],
            {
                k: item["row"][k]
                for k in ("selected_body_text", "recipient_email", "reviewer_notes")
            },
            verified_review(),
        )
        return self.service.detail(item["order_id"])

    def approved(self):
        item = self.reviewed()
        self.service.approve(
            item["order_id"],
            item["version"],
            item["approval_binding"],
            "I_APPROVE_THIS_EXACT_HELP_SCOUT_DRAFT",
        )
        return self.service.detail(item["order_id"])

    def test_preview_and_cancel_are_non_persistent(self):
        preview = self.service.preview_import(csv_text([synthetic_row()]))
        self.assertFalse(self.path.exists())
        self.service.cancel_import(preview["preview_token"])
        with self.assertRaisesRegex(TransferError, "EXPIRED"):
            self.service.commit_import(preview["preview_token"], 0)
        self.assertFalse(self.path.exists())

    def test_conditional_outreach_approval_and_decision_edit_invalidation(self):
        row = synthetic_row()
        row["selected_body_text"] = (
            "Would you like this synthetic alternate? Your decision is still pending; "
            "no order change has been made.\n\n" + row["selected_body_text"]
        )
        row["selected_body_sha256"] = text_hash(row["selected_body_text"])
        row["review_gate_state_json"] = '{"customer_order_change_approval":"PENDING"}'
        item = self.imported(row)
        review = verified_review()
        review["checks"]["customer_approval"].update(
            decision="pending_conditional_outreach",
            conditional_copy_reviewed=True,
            evidence=(
                "SYN customer has not approved; exact copy asks for consent without changing order"
            ),
        )
        fields = {
            key: row[key] for key in ("selected_body_text", "recipient_email", "reviewer_notes")
        }
        self.service.edit(item["order_id"], item["version"], fields, review)
        item = self.service.detail(item["order_id"])
        with self.assertRaisesRegex(TransferError, "EXPLICIT_APPROVAL_REQUIRED"):
            self.service.approve(item["order_id"], item["version"], item["approval_binding"], "")
        self.service.approve(
            item["order_id"],
            item["version"],
            item["approval_binding"],
            "I_APPROVE_THIS_EXACT_HELP_SCOUT_DRAFT",
        )
        self.assertTrue(self.service.detail(item["order_id"])["approved"])
        self.assertEqual(self.client.calls, [])
        review["checks"]["customer_approval"].update(
            decision="approval_recorded",
            conditional_copy_reviewed=False,
            evidence="SYN later customer consent recorded",
        )
        self.service.edit(item["order_id"], item["version"], fields, review)
        changed = self.service.detail(item["order_id"])
        self.assertFalse(changed["approved"])
        self.assertNotEqual(changed["approval_binding"], item["approval_binding"])
        with self.assertRaisesRegex(TransferError, "CURRENT_EXACT_APPROVAL_REQUIRED"):
            self.service.transfer(
                changed["order_id"], changed["version"], changed["approval_binding"]
            )
        self.assertEqual(self.client.calls, [])

    def test_legacy_customer_checkbox_cannot_reuse_old_approval(self):
        item = self.approved()
        old = copy.deepcopy(item["review"])
        old["checks"]["customer_approval"] = {"resolved": True, "evidence": "SYN legacy"}
        with self.store.transaction(write=True) as con:
            self.store.put(
                con, item["order_id"], item["version"] + 1, item["row"], old, item["approval"]
            )
        legacy = self.service.detail(item["order_id"])
        self.assertFalse(legacy["approved"])
        self.assertIn("REVIEW_CUSTOMER_DECISION_REQUIRED", legacy["holds"])
        with self.assertRaisesRegex(TransferError, "CURRENT_EXACT_APPROVAL_REQUIRED"):
            self.service.transfer(legacy["order_id"], legacy["version"], legacy["approval_binding"])
        self.assertEqual(self.client.calls, [])

    def test_failed_reverification_persists_unverified_without_creating_again(self):
        item = self.approved()
        created = self.service.transfer(item["order_id"], item["version"], item["approval_binding"])
        self.assertEqual(created["state"], "CREATED")
        adapter = HelpScoutDraftClient("SYN-DUMMY-NOT-A-CREDENTIAL")
        self.service.client = adapter
        with patch.object(adapter, "_request", return_value=(404, {}, b"")) as requests:
            outcome = self.service.verify_transfer(item["order_id"], item["version"])
            self.assertEqual(outcome["state"], "CREATED_UNVERIFIED")
            self.assertEqual(outcome["conversation_id"], created["conversation_id"])
            self.assertFalse(outcome["retry_allowed"])
            reopened = DraftTransferService(DraftTransferStore(self.path), adapter)
            for retry in (False, True):
                result = reopened.transfer(
                    item["order_id"], item["version"], item["approval_binding"], retry
                )
                self.assertEqual(result["state"], "CREATED_UNVERIFIED")
            self.assertEqual(requests.call_count, 1)
            self.assertEqual(requests.call_args.args[0], "GET")
        self.assertEqual(len(self.client.calls), 1)

    def test_import_claims_do_not_approve_or_contact_api(self):
        item = self.imported()
        self.assertFalse(item["approved"])
        self.assertFalse(item["send_ready"])
        self.assertFalse(item["review"]["recipient_verified"])
        self.assertEqual(self.client.calls, [])

    def test_stale_preview_merge_conflict_retains_local_edit(self):
        item = self.reviewed()
        preview = self.service.preview_import(csv_text([synthetic_row()]))
        fields = {
            k: item["row"][k] for k in ("selected_body_text", "recipient_email", "reviewer_notes")
        }
        fields["reviewer_notes"] = "SYN newer note"
        self.service.edit(item["order_id"], item["version"], fields, item["review"])
        with self.assertRaisesRegex(TransferError, "REVISION_CONFLICT"):
            self.service.commit_import(preview["preview_token"], preview["revision"])
        incoming = synthetic_row()
        incoming["preserved_original_body_text"] += "\nSYN different original"
        incoming["source_body_sha256"] = text_hash(incoming["preserved_original_body_text"])
        preview = self.service.preview_import(csv_text([incoming]))
        conflict = preview["rows"][0]
        self.assertEqual(conflict["action"], "CONFLICT_KEEP_LOCAL")
        self.assertEqual(conflict["incoming_hash"], incoming["selected_body_sha256"])
        self.assertEqual(conflict["local_hash"], item["row"]["selected_body_sha256"])
        self.assertEqual(conflict["incoming_source_hash"], incoming["source_body_sha256"])
        self.assertEqual(conflict["local_source_hash"], item["row"]["source_body_sha256"])
        self.assertNotEqual(conflict["incoming_source_hash"], conflict["local_source_hash"])
        self.service.commit_import(preview["preview_token"], preview["revision"])
        self.assertEqual(
            self.service.detail(item["order_id"])["row"]["reviewer_notes"], "SYN newer note"
        )

    def test_edit_invalidates_approval_recipient_and_body_verification(self):
        item = self.approved()
        fields = {
            k: item["row"][k] for k in ("selected_body_text", "recipient_email", "reviewer_notes")
        }
        fields["selected_body_text"] += "\nSYN edited copy"
        self.service.edit(item["order_id"], item["version"], fields, item["review"])
        newer = self.service.detail(item["order_id"])
        self.assertIsNone(newer["approval"])
        self.assertEqual(newer["review"], fresh_review())
        with self.assertRaisesRegex(TransferError, "VERSION_CONFLICT"):
            self.service.transfer(item["order_id"], item["version"], item["approval_binding"])
        self.assertEqual(self.client.calls, [])

    def test_exact_hash_recipient_mailbox_version_binding(self):
        item = self.reviewed()
        binding = item["approval_binding"]
        row = dict(item["row"])
        row["recipient_email"] = "other.synthetic@example.test"
        self.assertNotEqual(binding, approval_binding(row, item["version"], item["review"]))
        self.assertNotEqual(
            binding, approval_binding(item["row"], item["version"] + 1, item["review"])
        )
        with self.assertRaisesRegex(TransferError, "CONTENT_CONFLICT"):
            self.service.approve(
                item["order_id"], item["version"], "0" * 64, "I_APPROVE_THIS_EXACT_HELP_SCOUT_DRAFT"
            )

    def test_holds_and_missing_recipient_cannot_approve(self):
        row = synthetic_row()
        row["recipient_email"] = ""
        self.imported(row)
        item = self.service.detail(row["order_id"])
        with self.assertRaisesRegex(TransferError, "UNRESOLVED"):
            self.service.approve(
                item["order_id"],
                item["version"],
                item["approval_binding"],
                "I_APPROVE_THIS_EXACT_HELP_SCOUT_DRAFT",
            )

    def test_held_copy_cannot_be_replaced_from_original(self):
        row = synthetic_row()
        row.update(selected_body_text="", selected_body_sha256=text_hash(""), draft_status="HELD")
        item = self.imported(row)
        with self.assertRaisesRegex(TransferError, "HELD_COPY"):
            self.service.edit(
                row["order_id"],
                1,
                {
                    "selected_body_text": row["preserved_original_body_text"],
                    "recipient_email": row["recipient_email"],
                    "reviewer_notes": "",
                },
                verified_review(),
            )
        self.assertEqual(self.service.detail(row["order_id"])["row"]["selected_body_text"], "")

    def test_duplicate_click_and_restart_have_one_write(self):
        item = self.approved()
        first = self.service.transfer(item["order_id"], item["version"], item["approval_binding"])
        second = self.service.transfer(item["order_id"], item["version"], item["approval_binding"])
        restarted = DraftTransferService(DraftTransferStore(self.path), self.client)
        third = restarted.transfer(
            item["order_id"], item["version"], item["approval_binding"], True
        )
        self.assertEqual(first, second)
        self.assertEqual(first, third)
        self.assertEqual(len(self.client.calls), 1)
        self.assertTrue(self.client.calls[0]["threads"][0]["draft"])

    def test_concurrent_duplicate_clicks_reserve_before_network(self):
        item = self.approved()
        started, release = threading.Event(), threading.Event()
        original = self.client.create_draft

        def blocked(row):
            started.set()
            release.wait(5)
            return original(row)

        self.client.create_draft = blocked
        results = []
        thread = threading.Thread(
            target=lambda: results.append(
                self.service.transfer(item["order_id"], item["version"], item["approval_binding"])
            )
        )
        thread.start()
        self.assertTrue(started.wait(5))
        other = DraftTransferService(DraftTransferStore(self.path), self.client)
        duplicate = other.transfer(item["order_id"], item["version"], item["approval_binding"])
        self.assertEqual(duplicate["state"], "IN_FLIGHT")
        release.set()
        thread.join(5)
        self.assertEqual(len(self.client.calls), 1)

    def test_uncertain_response_never_retries(self):
        item = self.approved()
        self.client.result = {
            "state": "UNKNOWN",
            "code": "WRITE_OUTCOME_UNKNOWN",
            "retry_allowed": False,
        }
        for retry in (False, True, True):
            result = self.service.transfer(
                item["order_id"], item["version"], item["approval_binding"], retry
            )
            self.assertEqual(result["state"], "UNKNOWN")
        self.assertEqual(len(self.client.calls), 1)

    def test_auth_rejection_requires_explicit_retry_same_operation(self):
        item = self.approved()
        self.client.result = {"state": "AUTH_REQUIRED", "code": "AUTH", "retry_allowed": True}
        first = self.service.transfer(item["order_id"], item["version"], item["approval_binding"])
        with self.assertRaisesRegex(TransferError, "EXPLICIT_RETRY"):
            self.service.transfer(item["order_id"], item["version"], item["approval_binding"])
        self.client.result = MockClient().result
        second = self.service.transfer(
            item["order_id"], item["version"], item["approval_binding"], True
        )
        self.assertEqual(first["operation_id"], second["operation_id"])
        self.assertEqual(len(self.client.calls), 2)

    def test_rate_limit_cooldown_and_readback_never_writes(self):
        item = self.approved()
        self.client.result = {
            "state": "RATE_LIMITED",
            "code": "RATE",
            "retry_allowed": True,
            "retry_after_seconds": 60,
        }
        self.service.transfer(item["order_id"], item["version"], item["approval_binding"])
        with self.assertRaisesRegex(TransferError, "WAIT_REQUIRED"):
            self.service.transfer(item["order_id"], item["version"], item["approval_binding"], True)
        self.assertEqual(len(self.client.calls), 1)

    def test_reserved_crash_state_locks_write_and_history_is_immutable(self):
        item = self.approved()
        with self.store.transaction(write=True) as con:
            self.store.transfer(
                con, item["order_id"], {"state": "IN_FLIGHT", "retry_allowed": False}
            )
        result = self.service.transfer(
            item["order_id"], item["version"], item["approval_binding"], True
        )
        self.assertEqual(result["state"], "IN_FLIGHT")
        with self.store.transaction() as con:
            versions = con.execute(
                "SELECT version,row_json FROM versions ORDER BY version"
            ).fetchall()
            self.assertEqual(json.loads(versions[0][1]), synthetic_row())
            events = con.execute(
                "SELECT event_json,event_hash FROM audit ORDER BY sequence"
            ).fetchall()
            previous = ""
            for raw, hashed in events:
                event = json.loads(raw)
                self.assertEqual(event["previous_hash"], previous)
                self.assertEqual(digest(event), hashed)
                previous = hashed
        self.assertEqual(self.client.calls, [])

    def test_corrupt_storage_preserved_and_no_external_write(self):
        self.path.write_bytes(b"SYN corrupt fixture")
        with self.assertRaises(TransferError):
            self.service.index()
        self.assertEqual(self.path.read_bytes(), b"SYN corrupt fixture")
        self.assertEqual(self.client.calls, [])


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.row = synthetic_row()
        self.client = HelpScoutDraftClient("SYN-DUMMY-NOT-A-CREDENTIAL")

    def test_payload_has_only_draft_reply_and_exact_destination_body(self):
        payload = payload_for(self.row)
        self.assertEqual(payload["mailboxId"], MAILBOX_ID)
        self.assertEqual(payload["assignTo"], USER_ID)
        self.assertFalse(payload["autoReply"])
        self.assertEqual(len(payload["threads"]), 1)
        self.assertEqual(payload["threads"][0]["type"], "reply")
        self.assertIs(payload["threads"][0]["draft"], True)
        self.assertNotIn("cc", str(payload))
        self.assertNotIn("bcc", str(payload))
        self.assertEqual(body_text(payload["threads"][0]["text"]), self.row["selected_body_text"])

    def test_no_auto_retry_on_timeout_5xx_redirect_missing_id(self):
        cases = [
            (500, {}, b""),
            (302, {"location": "https://evil.example.test"}, b""),
            (201, {}, b""),
            (408, {}, b""),
        ]
        for response in cases:
            with (
                self.subTest(status=response[0]),
                patch.object(self.client, "_request", return_value=response) as call,
            ):
                result = self.client.create_draft(self.row)
                self.assertEqual(result["state"], "UNKNOWN")
                self.assertFalse(result["retry_allowed"])
                self.assertEqual(call.call_count, 1)
        with patch.object(self.client, "_request", side_effect=TimeoutError()) as call:
            self.assertEqual(self.client.create_draft(self.row)["state"], "UNKNOWN")
            self.assertEqual(call.call_count, 1)

    def test_success_requires_verified_draft_readback_and_preserves_returned_link(self):
        ident = "99000001"
        result = {
            "id": int(ident),
            "state": "draft",
            "mailboxId": MAILBOX_ID,
            "subject": self.row["subject"],
            "assignee": {"id": USER_ID},
            "primaryCustomer": {"email": self.row["recipient_email"]},
            "_embedded": {
                "threads": [
                    {
                        "id": 99000002,
                        "type": "message",
                        "state": "draft",
                        "createdBy": {"id": USER_ID},
                        "to": [self.row["recipient_email"]],
                        "body": rendered_body(self.row["selected_body_text"]),
                    }
                ]
            },
        }
        replies = [
            (
                201,
                {
                    "resource-id": ident,
                    "web-location": f"https://secure.helpscout.net/conversation/{ident}/1",
                },
                b"",
            ),
            (200, {}, json.dumps(result).encode()),
        ]
        with patch.object(self.client, "_request", side_effect=replies) as call:
            outcome = self.client.create_draft(self.row)
            self.assertEqual(outcome["state"], "CREATED")
            self.assertTrue(outcome["web_link"].endswith("/1"))
            self.assertEqual(call.call_args_list[1].args[0], "GET")
        result["_embedded"]["threads"][0]["to"] = ["other.synthetic@example.test"]
        replies[1] = (200, {}, json.dumps(result).encode())
        with patch.object(self.client, "_request", side_effect=replies):
            self.assertEqual(self.client.create_draft(self.row)["state"], "CREATED_UNVERIFIED")
        result["_embedded"]["threads"][0]["to"] = [self.row["recipient_email"]]
        original_html = result["_embedded"]["threads"][0]["body"]
        changed_href = original_html.replace("add1=99000001", "add1=99000002", 1)
        self.assertEqual(body_text(changed_href), self.row["selected_body_text"])
        result["_embedded"]["threads"][0]["body"] = changed_href
        replies[1] = (200, {}, json.dumps(result).encode())
        with patch.object(self.client, "_request", side_effect=replies):
            self.assertEqual(self.client.create_draft(self.row)["state"], "CREATED_UNVERIFIED")
        result["_embedded"]["threads"][0]["body"] = original_html
        result["state"] = "published"
        replies[1] = (200, {}, json.dumps(result).encode())
        with patch.object(self.client, "_request", side_effect=replies):
            self.assertEqual(self.client.create_draft(self.row)["state"], "CREATED_UNVERIFIED")

    def test_reverification_resets_prior_success_for_mismatch_published_deleted_and_errors(self):
        good = {
            "id": 99000001,
            "state": "draft",
            "mailboxId": MAILBOX_ID,
            "subject": self.row["subject"],
            "assignee": {"id": USER_ID},
            "primaryCustomer": {"email": self.row["recipient_email"]},
            "_embedded": {
                "threads": [
                    {
                        "type": "message",
                        "state": "draft",
                        "createdBy": {"id": USER_ID},
                        "to": [self.row["recipient_email"]],
                        "body": rendered_body(self.row["selected_body_text"]),
                    }
                ]
            },
        }
        published_conversation = copy.deepcopy(good)
        published_conversation["state"] = "published"
        published_message = copy.deepcopy(good)
        published_message["_embedded"]["threads"][0]["state"] = "published"
        changed = copy.deepcopy(good)
        changed["_embedded"]["threads"][0]["body"] += "SYN changed body"
        cases = [
            (name, (200, {}, json.dumps(value).encode()))
            for name, value in (
                ("conversation published", published_conversation),
                ("message published", published_message),
                ("body changed", changed),
            )
        ]
        cases += [
            ("deleted", (404, {}, b"")),
            ("server error", (500, {}, b"")),
            ("malformed", (200, {}, b"not JSON")),
            ("timeout", TimeoutError()),
        ]
        for name, later_response in cases:
            with (
                self.subTest(case=name),
                patch.object(
                    self.client,
                    "_request",
                    side_effect=[(200, {}, json.dumps(good).encode()), later_response],
                ) as call,
            ):
                initial = {
                    "conversation_id": "99000001",
                    "operation_id": "SYN-OPERATION",
                    "retry_allowed": False,
                    "state": "CREATED_UNVERIFIED",
                }
                verified = self.client.verify_draft(self.row, initial)
                self.assertEqual(verified["code"], "DRAFT_CREATED_VERIFIED")
                current = self.client.verify_draft(self.row, verified)
                self.assertEqual(current["state"], "CREATED_UNVERIFIED")
                self.assertEqual(current["code"], "DRAFT_READBACK_REQUIRED")
                self.assertEqual(current["conversation_id"], "99000001")
                self.assertEqual(current["operation_id"], "SYN-OPERATION")
                self.assertFalse(current["retry_allowed"])
                self.assertEqual(verified["state"], "CREATED")
                self.assertEqual(call.call_count, 2)
                self.assertTrue(all(item.args[0] == "GET" for item in call.call_args_list))

    def test_no_token_in_auth_or_rate_limit_results(self):
        for status, state in (
            (401, "AUTH_REQUIRED"),
            (403, "AUTH_REQUIRED"),
            (429, "RATE_LIMITED"),
        ):
            with patch.object(
                self.client,
                "_request",
                return_value=(status, {"x-ratelimit-retry-after": "7"}, b"SYN secret"),
            ):
                result = self.client.create_draft(self.row)
                self.assertEqual(result["state"], state)
                self.assertNotIn("secret", json.dumps(result))

    def test_destination_auth_expiry_and_malformed_response_fail_closed(self):
        with patch.object(self.client, "_request", return_value=(401, {}, b"SYN private")):
            with self.assertRaisesRegex(TransferError, "AUTH_EXPIRED"):
                self.client.check_destination()
        with patch.object(self.client, "_request", return_value=(200, {}, b"[]")):
            with self.assertRaisesRegex(TransferError, "DESTINATION_UNVERIFIED"):
                self.client.check_destination()

    def test_prohibited_operation_redirect_link_and_configuration_off(self):
        with self.assertRaisesRegex(TransferError, "PROHIBITED"):
            self.client._request("PATCH", "/v2/conversations/99000001")
        for link in (
            "https://evil.example.test/",
            "javascript:alert(1)",
            "https://secure.helpscout.net@evil.example.test/conversation/99000001",
        ):
            self.assertIsNone(safe_web_link(link, "99000001"))
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(HelpScoutDraftClient.from_environment())


if __name__ == "__main__":
    unittest.main()
