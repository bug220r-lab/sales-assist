from __future__ import annotations

import hashlib
import sqlite3
import unittest
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

from synthetic_sales_assist.domain.timestamps import (
    TIMESTAMP_HASH_DOMAIN,
    TIMESTAMP_KNOWN_ANSWER_CANONICAL,
    TIMESTAMP_KNOWN_ANSWER_SHA256,
    TIMESTAMP_SQLITE_DECLARATION,
    CanonicalTimestamp,
    TimestampValidationError,
    assert_same_canonical_instant,
    canonicalize_timestamp,
    parse_timestamp,
    timestamp_hash_preimage,
    timestamp_sha256,
    timestamps_same_instant,
    verify_timestamp_known_answer,
)


class TimestampCanonicalizationTests(unittest.TestCase):
    def test_offsets_normalize_to_utc_z(self) -> None:
        equivalent = (
            "2026-08-10T12:34:56.12Z",
            "2026-08-10T08:34:56.120000000-04:00",
            "2026-08-10T18:04:56.120+05:30",
            "2026-08-11T00:34:56.12+12:00",
        )
        canonical = {canonicalize_timestamp(value) for value in equivalent}
        self.assertEqual(canonical, {TIMESTAMP_KNOWN_ANSWER_CANONICAL})

    def test_fractional_boundaries_are_nanosecond_exact(self) -> None:
        vectors = {
            "2026-01-01T00:00:00Z": "2026-01-01T00:00:00Z",
            "2026-01-01T00:00:00.0Z": "2026-01-01T00:00:00Z",
            "2026-01-01T00:00:00.100000000Z": "2026-01-01T00:00:00.1Z",
            "2026-01-01T00:00:00.000000001Z": "2026-01-01T00:00:00.000000001Z",
            "2026-01-01T00:00:00.123456789Z": "2026-01-01T00:00:00.123456789Z",
        }
        for source, expected in vectors.items():
            with self.subTest(fraction_length=source.partition(".")[2].partition("Z")[0]):
                parsed = parse_timestamp(source)
                self.assertEqual(parsed.value, expected)
                self.assertEqual(parsed.canonical_bytes(), expected.encode("ascii"))

    def test_invalid_dates_naive_values_and_noncanonical_grammar_reject(self) -> None:
        invalid: tuple[object, ...] = (
            "2026-02-29T00:00:00Z",
            "0000-01-01T00:00:00Z",
            "2026-01-01T24:00:00Z",
            "2026-01-01T00:00:60Z",
            "2026-01-01T00:00:00",
            "2026-01-01 00:00:00Z",
            "2026-01-01t00:00:00z",
            "2026-01-01T00:00:00.1234567890Z",
            "2026-01-01T00:00:00+24:00",
            "2026-01-01T00:00:00+00:60",
            "2026-01-01T00:00:00-00:00",
            " 2026-01-01T00:00:00Z",
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            None,
        )
        for value in invalid:
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaises(TimestampValidationError):
                    parse_timestamp(value)

    def test_value_is_immutable_and_repr_is_redacted(self) -> None:
        source = "2026-01-01T00:00:00Z"
        timestamp = CanonicalTimestamp(source)
        with self.assertRaises(FrozenInstanceError):
            setattr(timestamp, "value", "2026-01-02T00:00:00Z")
        self.assertNotIn(source, repr(timestamp))

    def test_source_time_coherence_uses_canonical_instant(self) -> None:
        first = "2026-01-15T15:30:00Z"
        equivalent = "2026-01-15T10:30:00-05:00"
        mismatch = "2026-01-15T15:30:00.000000001Z"
        self.assertTrue(timestamps_same_instant(first, equivalent))
        self.assertEqual(assert_same_canonical_instant(first, equivalent).value, first)
        self.assertFalse(timestamps_same_instant(first, mismatch))
        with self.assertRaisesRegex(TimestampValidationError, "timestamp_instant_mismatch"):
            assert_same_canonical_instant(first, mismatch)


class TimestampHashAndStorageTests(unittest.TestCase):
    def test_fixed_known_answer_oracle_reproduces_published_digest(self) -> None:
        expected_preimage = (
            TIMESTAMP_HASH_DOMAIN.encode("ascii")
            + b"\n"
            + TIMESTAMP_KNOWN_ANSWER_CANONICAL.encode("ascii")
        )
        self.assertEqual(
            timestamp_hash_preimage(TIMESTAMP_KNOWN_ANSWER_CANONICAL), expected_preimage
        )
        self.assertEqual(
            hashlib.sha256(expected_preimage).hexdigest(), TIMESTAMP_KNOWN_ANSWER_SHA256
        )
        self.assertEqual(
            timestamp_sha256("2026-08-10T08:34:56.120000000-04:00"),
            TIMESTAMP_KNOWN_ANSWER_SHA256,
        )
        self.assertTrue(verify_timestamp_known_answer())

    def test_equivalent_instants_have_equal_hashes(self) -> None:
        left = "2026-04-15T14:30:00.100Z"
        right = "2026-04-15T10:30:00.1-04:00"
        self.assertEqual(timestamp_sha256(left), timestamp_sha256(right))

    def test_sqlite_text_binary_round_trip_requires_canonical_text(self) -> None:
        timestamp = CanonicalTimestamp("2026-01-15T10:30:00.1200-05:00")
        connection = sqlite3.connect(":memory:")
        self.addCleanup(connection.close)
        connection.execute(
            f"CREATE TABLE timestamp_round_trip (value {TIMESTAMP_SQLITE_DECLARATION} NOT NULL)"
        )
        connection.execute(
            "INSERT INTO timestamp_round_trip(value) VALUES (?)",
            (timestamp.to_sqlite_value(),),
        )
        stored = connection.execute("SELECT value FROM timestamp_round_trip").fetchone()[0]
        restored = CanonicalTimestamp.from_sqlite_text(stored)
        self.assertEqual(restored, timestamp)
        self.assertEqual(restored.to_json_value(), "2026-01-15T15:30:00.12Z")

        with self.assertRaisesRegex(TimestampValidationError, "sqlite_timestamp_not_canonical"):
            CanonicalTimestamp.from_sqlite_text("2026-01-15T10:30:00.1200-05:00")


if __name__ == "__main__":
    unittest.main()
