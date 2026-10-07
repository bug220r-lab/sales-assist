"""Regressions for missing or changed required resources in review bundles."""

import unittest
from pathlib import Path

from tools.review_package_payload import REQUIRED_MIGRATIONS, validate_migration_payload


class ReviewPackagePayloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.payloads = {name: (root / name).read_bytes() for name in REQUIRED_MIGRATIONS}

    def test_complete_authoritative_payload_is_accepted(self):
        validate_migration_payload(self.payloads)

    def test_bundle_without_migrations_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "REVIEW_MIGRATION_INVENTORY_INVALID"):
            validate_migration_payload({"src/fictional.py": b""})

    def test_each_missing_migration_is_rejected(self):
        for name in REQUIRED_MIGRATIONS:
            with self.subTest(name=name):
                incomplete = dict(self.payloads)
                del incomplete[name]
                with self.assertRaisesRegex(ValueError, "REVIEW_MIGRATION_INVENTORY_INVALID"):
                    validate_migration_payload(incomplete)

    def test_each_changed_migration_is_rejected(self):
        for name in REQUIRED_MIGRATIONS:
            with self.subTest(name=name):
                changed = dict(self.payloads)
                changed[name] += b"\n-- fictional alteration\n"
                with self.assertRaisesRegex(ValueError, "REVIEW_MIGRATION_PAYLOAD_INVALID"):
                    validate_migration_payload(changed)

    def test_unexpected_migration_is_rejected(self):
        unexpected = dict(self.payloads)
        unexpected["migrations/0005_fictional.sql"] = b"SELECT 1;"
        with self.assertRaisesRegex(ValueError, "REVIEW_MIGRATION_INVENTORY_INVALID"):
            validate_migration_payload(unexpected)

    def test_text_in_place_of_original_bytes_is_rejected(self):
        changed = dict(self.payloads)
        name = next(iter(REQUIRED_MIGRATIONS))
        changed[name] = changed[name].decode("utf-8")
        with self.assertRaisesRegex(ValueError, "REVIEW_MIGRATION_PAYLOAD_INVALID"):
            validate_migration_payload(changed)
