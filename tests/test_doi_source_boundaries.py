"""Authorized DOI source literals do not relax unrelated content or secret checks."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from doi_csv_staging.alternate_drafts import CTA_URL
from synthetic_sales_assist.safety.repository import (
    scan_prohibited_repository_content,
    scan_secret_material,
)


class DOISourceBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "src/doi_csv_staging/alternate_drafts.py"
        self.source.parent.mkdir(parents=True)

    def test_exact_reviewed_literal_is_allowed_only_at_its_location(self):
        self.source.write_text(repr(CTA_URL), encoding="utf-8")
        self.assertEqual(scan_prohibited_repository_content(self.root), ())
        self.source.rename(self.source.with_name("unreviewed.py"))
        self.assertIn(
            "non_localhost_url",
            {f.category for f in scan_prohibited_repository_content(self.root)},
        )

    def test_changed_query_or_hostname_still_fails(self):
        for value in (CTA_URL + "&unreviewed=1", CTA_URL.replace("www.", "new.")):
            self.source.write_text(repr(value), encoding="utf-8")
            self.assertIn(
                "non_localhost_url",
                {f.category for f in scan_prohibited_repository_content(self.root)},
            )

    def test_credential_scanning_still_covers_reviewed_source(self):
        canary = "g" + "hp_" + "A" * 36
        self.source.write_text(repr(CTA_URL) + "\n" + canary, encoding="utf-8")
        self.assertIn("source_access_token", {f.category for f in scan_secret_material(self.root)})

    def test_authored_marker_does_not_allow_customer_data_or_unknown_asset_scope(self):
        target = self.root / "src/doi_draft_transfer/ui.html"
        target.parent.mkdir(parents=True)
        marker = "<!-- SYNTHETIC-SALES-ASSIST-AUTHORED-M5 -->\n"
        target.write_text(marker + "<div>Authored UI</div>", encoding="utf-8")
        self.assertEqual(scan_prohibited_repository_content(self.root), ())
        target.write_text(marker + "canary@" + "private.invalid", encoding="utf-8")
        self.assertIn(
            "non_synthetic_email",
            {f.category for f in scan_prohibited_repository_content(self.root)},
        )
        unknown = self.root / "src/unreviewed.html"
        unknown.write_text(marker + "<div>Unreviewed</div>", encoding="utf-8")
        self.assertIn(
            "unapproved_portal_asset",
            {f.category for f in scan_prohibited_repository_content(self.root)},
        )


    def test_draft_launcher_registration_keeps_content_secret_and_unknown_script_checks(self):
        target = self.root / "scripts/start-drafts.ps1"
        target.parent.mkdir(parents=True)
        marker = "# SYNTHETIC-SALES-ASSIST-AUTHORED-M5\n"
        target.write_text(marker + "Write-Output SYN", encoding="utf-8")
        self.assertEqual(scan_prohibited_repository_content(self.root), ())
        canary = "g" + "hp_" + "A" * 36
        target.write_text(marker + canary, encoding="utf-8")
        self.assertIn("source_access_token", {f.category for f in scan_secret_material(self.root)})
        target.write_text(marker + "canary@" + "private.invalid", encoding="utf-8")
        self.assertIn(
            "non_synthetic_email",
            {f.category for f in scan_prohibited_repository_content(self.root)},
        )
        target.write_text(marker + "Write-Output SYN", encoding="utf-8")
        target.rename(target.with_name("unreviewed-drafts.ps1"))
        self.assertIn(
            "unapproved_lifecycle_script",
            {f.category for f in scan_prohibited_repository_content(self.root)},
        )
