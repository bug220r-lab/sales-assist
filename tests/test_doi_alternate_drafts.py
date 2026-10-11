"""Generated fictional products/orders only; no external network or live app access."""

import copy
import http.client
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import uuid

from doi_csv_staging.alternate_drafts import (
    AlternateDraftService,
    DraftStore,
    DraftError,
    empty_fields,
    validate_fields,
    validate_entry,
    generated_body,
    projection,
    parse_request,
    valid_url,
    CHECKS,
    CTA_TEXT,
    CTA_URL,
    SIGNATURE,
    STORE_SCHEMA,
)
from doi_csv_staging.review import DOIReviewSession, DOIReviewError
from doi_csv_staging.review_marks import ReviewMarkStore
from synthetic_sales_assist.portal.server import PortalHTTPServer, PortalServerConfig
from tests.test_doi_csv_review_ui import fictional_csvs
from tests.test_csv_staging_independent import summary, line


def reviewed_fields():
    f = empty_fields()
    f.update(
        original_item="SYN delayed bracket",
        alternate_name="SYN alternate bracket",
        selected_line_ids="SYN-LINE-1",
        source_quantities_exact="ordered_quantity_displayed: 1; required reviewed: 1",
        alternate_id="99000001",
        alternate_quantity="1",
        alternate_observed_at="2026-10-10T10:00:00-04:00",
        stock_wording="In Stock",
        material_differences=(
            "Different brand; reviewed steel construction and single-bracket scope."
        ),
        delay_verified=True,
        delay_note="SYN source review 2026-10-10",
        product_url="https://www.ecstuning.com/b-synthetic/SYN-99000001/",
        product_verified=True,
        product_note="SYN supported research source/reference",
        product_verifier="research_tool",
        product_observed_at="2026-10-10T10:00:00-04:00",
    )
    f["checks"] = {key: dict(status="verified", note="SYN reviewed evidence") for key in CHECKS}
    return f


class AlternateDraftTests(unittest.TestCase):
    def setUp(self):
        root = Path(
            os.environ.get(
                "SSA_DRAFT_TEST_ROOT", str(Path(tempfile.gettempdir()) / "ssa-synthetic-drafts")
            )
        )
        root.mkdir(parents=True, exist_ok=True)
        self.folder = root / ("synthetic-" + uuid.uuid4().hex)
        self.folder.mkdir()
        self.assertTrue(self.folder.resolve().is_relative_to(root.resolve()))
        self.path = self.folder / "doi-alternate-drafts.json"
        self.store = DraftStore(self.path)
        self.marks = ReviewMarkStore(self.folder / "doi-reviewed-split.json")
        self.now = 1000
        self.session = DOIReviewSession(
            clock=lambda: self.now, ttl_seconds=36000, review_mark_store=self.marks
        )
        self.session.load(*fictional_csvs(), 0)
        self.service = AlternateDraftService(self.session, self.store)

    def tearDown(self):
        for path in self.folder.iterdir():
            self.assertIn(path.name, {"doi-alternate-drafts.json", "doi-reviewed-split.json"})
            path.unlink()
        self.folder.rmdir()

    def act(self, action, **extra):
        return self.service.act(
            dict(
                action=action,
                revision=self.session.snapshot()["revision"],
                order_id="90000001",
                **extra,
            )
        )

    def generate(self, fields=None):
        return self.act("generate", fields=reviewed_fields() if fields is None else fields)

    def save(self, result):
        return self.act(
            "save",
            entry=result["draft"]["entry"],
            evidence_key=result["evidence_key"],
            storage_revision=result["storage_revision"],
        )

    def test_ready_is_review_only_exact_subject_signature_and_null_recipient(self):
        value = self.generate()
        draft = value["draft"]
        self.assertEqual(draft["status"], "READY_FOR_HUMAN_REVIEW")
        self.assertEqual(draft["subject"], "ORDER #90000001 DELAY - ECS TUNING - JUDE LEWIS")
        self.assertFalse(draft["send_ready"])
        self.assertIsNone(draft["recipient_email"])
        self.assertTrue(draft["email_text"].startswith("Hello!\n\nThis is Jude"))
        self.assertIn(SIGNATURE, draft["email_text"])
        self.assertIn(CTA_TEXT, draft["email_html"])
        self.assertIn(
            "utm_source=jlewis&amp;utm_medium=email&amp;utm_content=link2cart&amp;salesrep=jlewis",
            draft["email_html"],
        )
        self.assertNotIn("INTERNAL REVIEW", draft["email_text"])
        self.assertNotIn("cannot be split", draft["email_text"])
        self.assertIn("unknown", draft["notices"][0])
        self.assertIn("Different brand", draft["email_text"])

    def test_empty_and_each_missing_check_stay_held(self):
        self.assertEqual(self.generate(empty_fields())["draft"]["status"], "HELD_CANDIDATE")
        for key in CHECKS:
            f = reviewed_fields()
            f["checks"][key]["status"] = "unresolved"
            with self.subTest(check=key):
                self.assertEqual(self.generate(f)["draft"]["status"], "HELD_CANDIDATE")
        for key in (
            "selected_line_ids",
            "source_quantities_exact",
            "alternate_id",
            "alternate_quantity",
            "stock_wording",
            "material_differences",
            "alternate_observed_at",
        ):
            f = reviewed_fields()
            f[key] = ""
            with self.subTest(field=key):
                self.assertEqual(self.generate(f)["draft"]["status"], "HELD_CANDIDATE")

    def test_unknown_delay_never_asserted_and_unverified_product_link_omitted(self):
        f = reviewed_fields()
        f.update(delay_verified=False, product_verified=False)
        d = self.generate(f)["draft"]
        self.assertEqual(d["status"], "HELD_CANDIDATE")
        self.assertNotIn("is delayed", d["email_text"])
        self.assertNotIn(f["product_url"], d["email_text"])
        self.assertNotIn(f["product_url"], d["email_html"])

    def test_technical_conflict_and_other_rep_remain_held(self):
        f = reviewed_fields()
        f.update(technical_conflict=True, technical_note="SYN incompatible mount remains")
        d = self.generate(f)["draft"]
        self.assertEqual(d["status"], "HELD_TECHNICAL_REVIEW")
        self.assertNotIn(f["technical_note"], d["email_text"])
        self.assertIn(f["technical_note"], d["review_text"])
        self.session.load(
            *fictional_csvs([summary(displayed_sales_credit_value="akeesy")]),
            self.session.snapshot()["revision"],
        )
        d = self.generate()["draft"]
        self.assertEqual(d["status"], "HELD_CANDIDATE")
        self.assertTrue(any("ownership" in h for h in d["holds"]))

    def test_capture_conflict_and_ambiguous_identity_not_saveable(self):
        self.session.load(
            *fictional_csvs([summary(), summary()]), self.session.snapshot()["revision"]
        )
        value = self.generate()
        self.assertIsNone(value["evidence_key"])
        self.assertNotEqual(value["draft"]["status"], "READY_FOR_HUMAN_REVIEW")
        with self.assertRaisesRegex(DraftError, "EVIDENCE_MISMATCH"):
            self.save(value)
        self.assertFalse(self.path.exists())

    def test_exact_cart_contents_only_and_no_guessed_cart(self):
        self.assertEqual(self.generate()["draft"]["cart_status"], "NOT_PROVIDED")
        f = reviewed_fields()
        f.update(
            cart_url="https://www.ecstuning.com/Cart/?add1=99000001&qty1=1&utm_source=jlewis",
            cart_verified=True,
            cart_note="SYN tool observed exact one-product cart",
            cart_verifier="research_tool",
            cart_observed_at="2026-10-10T10:00:00-04:00",
        )
        d = self.generate(f)["draft"]
        self.assertEqual(d["cart_status"], "VERIFIED_CONTENTS")
        self.assertIn(f["cart_url"], d["email_text"])
        uncertain = copy.deepcopy(f)
        uncertain["checks"]["kit_scope"]["status"] = "unresolved"
        held = self.generate(uncertain)["draft"]
        self.assertIn(f["cart_url"], held["email_text"])
        self.assertEqual(held["status"], "HELD_CANDIDATE")
        for url in (
            f["cart_url"].replace("qty1=1", "qty1=2"),
            f["cart_url"] + "&add2=99000002&qty2=1",
            f["cart_url"] + "&qty1=1",
        ):
            bad = {**f, "cart_url": url}
            d = self.generate(bad)["draft"]
            self.assertEqual(d["status"], "HELD_CANDIDATE")
            self.assertNotIn(url, d["email_text"])

    def test_unsafe_links_rejected_without_network(self):
        for url in (
            "javascript:alert(1)",
            "http://www.ecstuning.com/x",
            "https://evil.example.test/x",
            "https://www.ecstuning.com.evil.example.test/x",
            "https://user@www.ecstuning.com/x",
            "https://www.ecstuning.com:443/x",
            "https://www.ecstuning.com/x%0afoo",
            "https://www.ecstuning.com/x#fragment",
            "https://www.ecstuning.com/x?a=1&amp;b=2",
        ):
            with self.subTest(url=url), self.assertRaises(DraftError):
                valid_url(url)

    def test_user_edit_requires_review_and_cannot_add_unverified_links(self):
        value = self.generate()
        entry = value["draft"]["entry"]
        entry["body"] = "Hello!\n\nSYN edited concise wording."
        d = self.act("preview", entry=entry)["draft"]
        self.assertEqual(d["status"], "HELD_CANDIDATE")
        entry["body_reviewed"] = True
        d = self.act("preview", entry=entry)["draft"]
        self.assertEqual(d["status"], "READY_FOR_HUMAN_REVIEW")
        for link in (
            "https://evil.example.test/",
            "https://www.ecstuning.com/Cart/?add1=99000002&qty1=99",
            "www.ecstuning.com/unverified",
            "javascript:alert(1)",
        ):
            entry["body"] = link
            with self.assertRaisesRegex(DraftError, "LINK_UNVERIFIED"):
                self.act("preview", entry=entry)

    def test_escaping_export_and_linked_cta(self):
        f = reviewed_fields()
        f["alternate_name"] = "<img src=x onerror=alert(1)> & SYN"
        d = self.generate(f)["draft"]
        self.assertIn("&lt;img", d["email_html"])
        self.assertNotIn("<img", d["email_html"])
        self.assertNotIn("<script", d["review_html"])
        self.assertIn("<section><h2>Internal review", d["review_html"])
        self.assertIn("CUSTOMER EMAIL\nSubject:", d["review_text"])

    def test_atomic_persistence_reopen_repeated_save_and_delete(self):
        value = self.save(self.generate())
        raw = self.path.read_bytes()
        self.assertEqual(value["storage_revision"], 1)
        again = self.save(value)
        self.assertEqual(again["storage_revision"], 1)
        self.assertEqual(self.path.read_bytes(), raw)
        self.assertEqual(again["updated_at"], value["updated_at"])
        self.service = AlternateDraftService(self.session, DraftStore(self.path))
        restored = self.act("load")
        self.assertEqual(restored["draft"]["entry"], value["draft"]["entry"])
        self.assertNotIn("fictional@example.test", self.path.read_text())
        self.act("delete", evidence_key=value["evidence_key"], storage_revision=1)
        self.assertFalse(self.act("load")["saved"])
        self.assertEqual(self.store.read(), (2, {}))

    def test_stale_tab_save_and_changed_evidence_are_rejected(self):
        value = self.generate()
        self.save(value)
        with self.assertRaisesRegex(DraftError, "REVISION_MISMATCH"):
            self.save(value)
        self.session.load(
            *fictional_csvs(lines=[line(current_stock_icon_exact="In Stock")]),
            self.session.snapshot()["revision"],
        )
        changed = self.act("load")
        self.assertTrue(changed["changed_evidence"])
        self.assertIsNotNone(changed["prior_body"])
        self.assertTrue(changed["draft"]["entry"]["fields"]["product_verified"])
        self.assertFalse(changed["draft"]["entry"]["fields"]["delay_verified"])
        self.assertEqual(changed["draft"]["entry"]["body"], value["draft"]["entry"]["body"])
        self.assertTrue(
            all(
                c["status"] == "unresolved"
                for c in changed["draft"]["entry"]["fields"]["checks"].values()
            )
        )
        self.assertEqual(changed["draft"]["status"], "HELD_CANDIDATE")
        with self.assertRaisesRegex(DraftError, "EVIDENCE_MISMATCH"):
            self.act(
                "save",
                entry=value["draft"]["entry"],
                evidence_key=value["evidence_key"],
                storage_revision=1,
            )

    def test_drafts_do_not_mutate_review_checks_or_ttl(self):
        mark = self.session.reviewed_snapshot()["orders"][0]
        self.session.set_reviewed(
            dict(
                revision=1,
                storage_revision=0,
                order_id="90000001",
                evidence_key=mark["evidence_key"],
                reviewed=True,
            )
        )
        marks = (self.folder / "doi-reviewed-split.json").read_bytes()
        before = self.session.snapshot()
        self.save(self.generate())
        self.act("load")
        self.assertEqual(self.session.snapshot(), before)
        self.assertEqual((self.folder / "doi-reviewed-split.json").read_bytes(), marks)
        raw = self.path.read_bytes()
        self.session.clear(1)
        self.assertEqual(self.path.read_bytes(), raw)
        self.session.load(*fictional_csvs(), 2)
        self.assertTrue(self.act("load")["saved"])
        self.now += 36001
        with self.assertRaises(DOIReviewError):
            self.act("load")
        self.assertEqual(self.path.read_bytes(), raw)

    def test_store_failure_preserves_previous_bytes_and_never_repairs(self):
        value = self.save(self.generate())
        raw = self.path.read_bytes()
        entry = copy.deepcopy(value["draft"]["entry"])
        entry["body"] += "\nSYN edit"
        with (
            patch("doi_csv_staging.alternate_drafts.os.replace", side_effect=PermissionError()),
            self.assertRaisesRegex(DraftError, "STORAGE_UNAVAILABLE"),
        ):
            self.act("save", entry=entry, evidence_key=value["evidence_key"], storage_revision=1)
        self.assertEqual(self.path.read_bytes(), raw)
        self.path.write_text("corrupt")
        self.assertFalse(self.act("load")["storage_available"])
        self.assertEqual(self.path.read_text(), "corrupt")

    def test_store_closed_schema_size_and_path_guards(self):
        for raw in ("{}", '{"schema":"x","schema":"x"}', " " * (4 * 1024 * 1024 + 1)):
            self.path.write_text(raw)
            with self.assertRaisesRegex(DraftError, "STORAGE_UNAVAILABLE"):
                self.store.read()
        with self.assertRaises(DraftError):
            DraftStore(Path("doi-alternate-drafts.json")).read()
        with self.assertRaises(DraftError):
            DraftStore(self.folder / "wrong.json").read()

    def test_missing_storage_is_preview_only(self):
        self.service = AlternateDraftService(self.session)
        value = self.generate()
        self.assertFalse(value["storage_available"])
        with self.assertRaisesRegex(DraftError, "STORAGE_UNAVAILABLE"):
            self.save(value)

    def test_storage_capacity_rejects_without_eviction_or_partial_write(self):
        value = self.generate()
        with (
            patch("doi_csv_staging.alternate_drafts.MAX_DRAFTS", 0),
            self.assertRaisesRegex(DraftError, "STORAGE_FULL"),
        ):
            self.save(value)
        self.assertFalse(self.path.exists())
        saved = self.save(value)
        before = self.path.read_bytes()
        edited = copy.deepcopy(saved)
        edited["draft"]["entry"]["body"] += "\nSYN changed wording"
        with (
            patch("doi_csv_staging.alternate_drafts.MAX_STORE", len(before) + 1),
            self.assertRaisesRegex(DraftError, "STORAGE_FULL"),
        ):
            self.save(edited)
        self.assertEqual(self.path.read_bytes(), before)

    def test_tool_and_human_link_evidence_need_source_and_observation_time(self):
        for verifier in ("research_tool", "human_review"):
            f = reviewed_fields()
            f["product_verifier"] = verifier
            self.assertIn(f["product_url"], self.generate(f)["draft"]["email_text"])
        for key in ("product_note", "product_observed_at", "product_verifier"):
            f = reviewed_fields()
            f[key] = ""
            value = self.generate(f)["draft"]
            self.assertEqual(value["status"], "HELD_CANDIDATE")
            self.assertNotIn(f["product_url"], value["email_text"])
        f = reviewed_fields()
        f["checks"]["price"]["status"] = "unresolved"
        self.assertEqual(self.generate(f)["draft"]["status"], "HELD_CANDIDATE")

    def test_invalid_and_oversized_requests_leave_review_intact(self):
        before = self.session.snapshot()
        for raw in (b'{"action":"load","action":"save"}', b"NaN", b"[]", b"x" * 32769, b"\xff"):
            with self.assertRaises(DraftError):
                parse_request(raw)
        for change in ({"action": []}, {"extra": True}, {"order_id": True}):
            value = dict(action="load", order_id="90000001", revision=1)
            value.update(change)
            with self.assertRaises(DraftError):
                self.service.act(value)
        self.assertEqual(before, self.session.snapshot())


class AlternateDraftHTTPTests(unittest.TestCase):
    setUp = AlternateDraftTests.setUp
    tearDown = AlternateDraftTests.tearDown

    def test_http_auth_bounds_and_persistence(self):
        server = PortalHTTPServer(
            None,
            PortalServerConfig("127.0.0.1", 0),
            csrf_token="a" * 64,
            shutdown_token="b" * 64,
            doi_csv_review_only=True,
            alternate_draft_store=self.store,
            review_mark_store=self.marks,
        )
        server.doi_review_session.load(*fictional_csvs(), 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def request(path, payload=None, token="a" * 64):
            c = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
            try:
                headers = {
                    "Origin": server.origin,
                    "Content-Type": "application/json",
                    "X-SSA-CSRF-Token": token,
                }
                c.request(
                    "GET" if payload is None else "POST",
                    path,
                    None if payload is None else json.dumps(payload),
                    headers,
                )
                r = c.getresponse()
                return r.status, r.read()
            finally:
                c.close()

        try:
            base = dict(
                action="generate", revision=1, order_id="90000001", fields=reviewed_fields()
            )
            route = "/api/v1/doi-csv-review/alternate-draft"
            code, raw = request(route, base)
            self.assertEqual(code, 200)
            value = json.loads(raw)
            self.assertEqual(value["draft"]["status"], "READY_FOR_HUMAN_REVIEW")
            self.assertEqual(request(route, base, token="c" * 64)[0], 403)
            self.assertEqual(request(route, {**base, "revision": 0})[0], 409)
            self.assertEqual(request(route, {**base, "fields": {}})[0], 400)
            self.assertEqual(request(route, {**base, "fields": {"x": "a" * 32769}})[0], 400)
            save = dict(
                action="save",
                revision=1,
                order_id="90000001",
                entry=value["draft"]["entry"],
                evidence_key=value["evidence_key"],
                storage_revision=0,
            )
            self.assertEqual(request(route, save)[0], 200)
            self.assertTrue(self.path.exists())
            self.assertEqual(request("/static/doi-alternate-draft.js")[0], 200)
            code, page = request("/doi-csv-review")
            self.assertEqual(code, 200)
            self.assertIn(b"alternate-editor", page)
            self.assertEqual(server.doi_review_session.snapshot()["counts"]["orders"], 1)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
