"""Real local persistence with hash-only fictional data; no application data access."""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

from doi_csv_staging.review import DOIReviewSession
from doi_csv_staging.review_marks import ReviewMarkError, ReviewMarkStore, SCHEMA
from tests.test_doi_csv_review_ui import fictional_csvs


class ReviewMarkStoreTests(unittest.TestCase):
    def setUp(self):
        root = Path(
            os.environ.get(
                "SSA_REVIEW_MARK_TEST_ROOT",
                str(Path(tempfile.gettempdir()) / "ssa-synthetic-review-marks"),
            )
        )
        root.mkdir(parents=True, exist_ok=True)
        self.directory = root / ("synthetic-" + uuid.uuid4().hex)
        self.directory.mkdir()
        self.path = self.directory / "doi-reviewed-split.json"
        self.store = ReviewMarkStore(self.path)

    def tearDown(self):
        # Only these known test artifacts are ours; never repair permissions.
        if self.path.exists():
            self.path.unlink()
        self.directory.rmdir()

    def test_real_file_reopen_reloads_same_evidence_and_contains_only_hashes(self):
        session = DOIReviewSession(review_mark_store=self.store)
        left, right = fictional_csvs()
        session.load(left, right, 0)
        state = session.reviewed_snapshot()
        item = state["orders"][0]
        session.set_reviewed(
            {
                "revision": state["revision"],
                "storage_revision": 0,
                "order_id": item["order_id"],
                "evidence_key": item["evidence_key"],
                "reviewed": True,
            }
        )
        saved = self.path.read_text()
        value = json.loads(saved)
        self.assertEqual(set(value), {"schema", "revision", "records"})
        self.assertEqual(value["schema"], SCHEMA)
        self.assertNotIn("90000001", saved)
        self.assertNotIn("example.test", saved)
        self.assertNotIn("SYN-", saved)
        self.assertEqual(len(value["records"]), 1)
        self.assertTrue(all(len(k) == len(v) == 64 for k, v in value["records"].items()))
        session.close()
        reopened = DOIReviewSession(review_mark_store=ReviewMarkStore(self.path))
        reopened.load(left, right, 0)
        self.assertEqual(reopened.reviewed_snapshot()["orders"][0]["status"], "REVIEWED")

    def test_atomic_replace_failure_preserves_prior_file_and_removes_own_temp(self):
        self.store.set("a" * 64, "b" * 64, True, 0)
        before = self.path.read_bytes()
        with patch("doi_csv_staging.review_marks.os.replace", side_effect=PermissionError()):
            with self.assertRaisesRegex(ReviewMarkError, "UNAVAILABLE"):
                self.store.set("c" * 64, "d" * 64, True, 1)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.directory.iterdir()), [self.path])

    def test_stale_independent_store_is_rejected_and_uncheck_persists(self):
        second = ReviewMarkStore(self.path)
        self.assertEqual(second.read(), (0, {}))
        self.store.set("a" * 64, "b" * 64, True, 0)
        with self.assertRaisesRegex(ReviewMarkError, "REVISION_MISMATCH"):
            second.set("a" * 64, "c" * 64, True, 0)
        second.set("a" * 64, "b" * 64, False, 1)
        self.assertEqual(self.store.read(), (2, {}))

    def test_corrupt_oversized_or_duplicate_key_store_fails_without_rewrite(self):
        cases = [
            "not JSON",
            '{"schema":"x","schema":"x"}',
            json.dumps({"schema": SCHEMA, "revision": True, "records": {}}),
            json.dumps({"schema": SCHEMA, "revision": 0, "records": {"raw-id": "raw-text"}}),
            " " * (2 * 1024 * 1024 + 1),
        ]
        for raw in cases:
            self.path.write_text(raw)
            with self.assertRaisesRegex(ReviewMarkError, "UNAVAILABLE"):
                self.store.read()
            with self.assertRaisesRegex(ReviewMarkError, "UNAVAILABLE"):
                self.store.set("a" * 64, "b" * 64, True, 0)
            self.assertEqual(self.path.read_text(), raw)

    def test_store_bounds_and_invalid_requests_do_not_create_file(self):
        with patch("doi_csv_staging.review_marks.MAX_MARKS", 0):
            with self.assertRaisesRegex(ReviewMarkError, "FULL"):
                self.store.set("a" * 64, "b" * 64, True, 0)
        for args in (
            ("raw-id", "b" * 64, True, 0),
            ("a" * 64, "b" * 64, 1, 0),
            ("a" * 64, "b" * 64, True, True),
        ):
            with self.assertRaisesRegex(ReviewMarkError, "REQUEST_INVALID"):
                self.store.set(*args)
        self.assertFalse(self.path.exists())

    def test_nonlocal_relative_wrong_filename_and_reparse_paths_are_rejected(self):
        for path in (
            Path("doi-reviewed-split.json"),
            self.directory / "other.json",
            self.directory / ".." / "doi-reviewed-split.json",
            Path(r"\\example.test\share\doi-reviewed-split.json"),
        ):
            with self.assertRaisesRegex(ReviewMarkError, "UNAVAILABLE"):
                ReviewMarkStore(path).read()
        with patch("doi_csv_staging.review_marks.stat.S_ISLNK", return_value=True):
            with self.assertRaisesRegex(ReviewMarkError, "UNAVAILABLE"):
                self.store.read()
