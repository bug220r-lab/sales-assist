"""Executable contract tests for canonical JSON and domain-separated hashes."""

from __future__ import annotations

import hashlib
import math
import unittest
from dataclasses import FrozenInstanceError

from synthetic_sales_assist.domain.canonical import (
    CanonicalHashCollision,
    CanonicalJsonViolation,
    HashBinding,
    HashDomainViolation,
    canonical_json_bytes,
    compare_retained_canonical_bytes,
    domain_hash,
    parse_canonical_json_bytes,
)


class CanonicalJsonTests(unittest.TestCase):
    def test_member_order_utf8_and_compact_encoding_are_deterministic(self) -> None:
        first = {
            "z": [3, {"β": "café"}],
            "a": {"present": True, "value": None},
        }
        second = {
            "a": {"value": None, "present": True},
            "z": [3, {"β": "café"}],
        }
        expected = '{"a":{"present":true,"value":null},"z":[3,{"β":"café"}]}'.encode()

        self.assertEqual(canonical_json_bytes(first), expected)
        self.assertEqual(canonical_json_bytes(second), expected)
        self.assertNotIn(b"\n", expected)

    def test_exact_closed_members_accept_roundtrip_and_reject_missing_or_unknown(self) -> None:
        expected_members = {"kind", "value"}
        canonical = canonical_json_bytes(
            {"value": 7, "kind": "SYN-EVALUATION-000001"},
            expected_members=expected_members,
        )
        parsed = parse_canonical_json_bytes(
            canonical,
            expected_members=expected_members,
        )
        self.assertEqual(parsed, {"kind": "SYN-EVALUATION-000001", "value": 7})

        private_member = "sensitive" + "_member"
        for value in (
            {"kind": "SYN-EVALUATION-000001"},
            {
                "kind": "SYN-EVALUATION-000001",
                "value": 7,
                private_member: "not-retained",
            },
        ):
            with self.subTest(value=value):
                with self.assertRaises(CanonicalJsonViolation) as caught:
                    canonical_json_bytes(value, expected_members=expected_members)
                self.assertNotIn(private_member, str(caught.exception))
                self.assertNotIn("not-retained", str(caught.exception))

    def test_duplicate_nonfinite_invalid_utf8_and_invalid_unicode_fail_closed(self) -> None:
        duplicate = b'{"a":1,"a":2}'
        invalid_utf8 = b'{"a":"' + bytes((0xFF,)) + b'"}'
        invalid_scalar = b'{"a":"\\ud800"}'
        for raw in (duplicate, invalid_utf8, invalid_scalar):
            with self.subTest(raw=raw):
                with self.assertRaises(CanonicalJsonViolation) as caught:
                    parse_canonical_json_bytes(raw)
                self.assertNotIn(repr(raw), str(caught.exception))

        for value in (math.nan, math.inf, -math.inf, -0.0, 0.0, 1.0, 1e-7):
            with self.subTest(value=value):
                with self.assertRaises(CanonicalJsonViolation):
                    canonical_json_bytes({"value": value})
        for raw in (b'{"value":NaN}', b'{"value":Infinity}', b'{"value":-Infinity}'):
            with self.subTest(raw=raw):
                with self.assertRaises(CanonicalJsonViolation):
                    parse_canonical_json_bytes(raw)

    def test_noncanonical_aliases_are_rejected_before_hashing(self) -> None:
        aliases = (
            b'{ "a":1}',
            b'{"b":2,"a":1}',
            b'{"a":1.0}',
            b'{"a":1.0e+0}',
            b'{"a":-0.0}',
            b'{"a":1e-07}',
            b'{"a":"\\u0062"}',
            b'{"a":1}\n',
        )
        for raw in aliases:
            with self.subTest(raw=raw):
                with self.assertRaises(CanonicalJsonViolation):
                    parse_canonical_json_bytes(raw)
                with self.assertRaises(HashDomainViolation):
                    domain_hash("synthetic-envelope/v1", raw)

    def test_non_json_types_and_malformed_member_schemas_are_rejected(self) -> None:
        for value in (
            (1, 2),
            {1: "numeric key"},
            bytearray(b"value"),
            object(),
        ):
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaises(CanonicalJsonViolation):
                    canonical_json_bytes(value)

        for members in ("member", ["a", "a"], ["a", ""]):
            with self.subTest(members=members):
                with self.assertRaises(CanonicalJsonViolation):
                    canonical_json_bytes({"a": 1}, expected_members=members)

        cyclic: list[object] = []
        cyclic.append(cyclic)
        with self.assertRaises(CanonicalJsonViolation):
            canonical_json_bytes(cyclic)

    def test_integer_boundary_is_exact_and_cross_producer_safe(self) -> None:
        maximum = (1 << 53) - 1
        self.assertEqual(canonical_json_bytes({"value": maximum}), b'{"value":9007199254740991}')
        self.assertEqual(
            canonical_json_bytes({"value": -maximum}),
            b'{"value":-9007199254740991}',
        )
        for value in (maximum + 1, -maximum - 1):
            with self.subTest(sign=value < 0):
                with self.assertRaises(CanonicalJsonViolation):
                    canonical_json_bytes({"value": value})

    def test_rejections_do_not_retain_codec_or_parser_exceptions(self) -> None:
        marker = "fictional" + "-private-marker"
        malformed = ('{"value":"' + marker).encode()
        invalid_scalar = marker + "\ud800"
        operations = (
            lambda: parse_canonical_json_bytes(malformed),
            lambda: canonical_json_bytes({"value": invalid_scalar}),
        )
        for operation in operations:
            with self.subTest(operation=operation):
                with self.assertRaises(CanonicalJsonViolation) as caught:
                    operation()
                error = caught.exception
                self.assertIsNone(error.__cause__)
                self.assertIsNone(error.__context__)
                self.assertNotIn(marker, repr(error.args))
                self.assertNotIn(marker, repr(error.__dict__))


class DomainHashTests(unittest.TestCase):
    def test_preimage_is_exact_domain_lf_json_and_sha_is_lowercase(self) -> None:
        canonical = canonical_json_bytes(
            {"run_id": "SYN-RUN-000001"},
            expected_members={"run_id"},
        )
        domain = "synthetic-run-envelope/v1"
        binding = domain_hash(domain, canonical)
        expected_preimage = domain.encode("ascii") + b"\n" + canonical

        self.assertEqual(binding.preimage, expected_preimage)
        self.assertEqual(binding.preimage.count(b"\n"), 1)
        self.assertEqual(binding.sha256, hashlib.sha256(expected_preimage).hexdigest())
        self.assertRegex(binding.sha256, r"^[0-9a-f]{64}$")
        self.assertNotIn("SYN-RUN-000001", repr(binding))
        self.assertNotIn(repr(canonical), repr(binding))

    def test_domain_separation_changes_the_digest_for_identical_bytes(self) -> None:
        canonical = canonical_json_bytes({"value": 1}, expected_members={"value"})
        first = domain_hash("synthetic-first/v1", canonical)
        second = domain_hash("synthetic-second/v1", canonical)
        self.assertNotEqual(first.sha256, second.sha256)
        self.assertEqual(first.canonical_bytes, second.canonical_bytes)

    def test_hash_binding_is_immutable_and_rejects_forgery(self) -> None:
        class DigestSubclass(str):
            pass

        canonical = canonical_json_bytes({"value": 1})
        binding = domain_hash("synthetic-value/v1", canonical)
        with self.assertRaises(FrozenInstanceError):
            binding.sha256 = "0" * 64  # type: ignore[misc]
        with self.assertRaises(HashDomainViolation):
            HashBinding(
                domain="synthetic-value/v1",
                sha256="0" * 64,
                canonical_bytes=canonical,
            )
        with self.assertRaises(HashDomainViolation):
            HashBinding(
                domain=binding.domain,
                sha256=DigestSubclass(binding.sha256),
                canonical_bytes=canonical,
            )

    def test_invalid_domains_fail_without_echoing_input(self) -> None:
        canonical = canonical_json_bytes({"value": 1})
        private_fragment = "private" + "-domain"
        invalid_domains: tuple[object, ...] = (
            "",
            "UPPER/v1",
            "missing-version",
            "synthetic/v0",
            private_fragment + "\n/v1",
            b"synthetic/v1",
        )
        for domain in invalid_domains:
            with self.subTest(domain_type=type(domain).__name__):
                with self.assertRaises(HashDomainViolation) as caught:
                    domain_hash(domain, canonical)  # type: ignore[arg-type]
                self.assertNotIn(private_fragment, str(caught.exception))

    def test_retained_byte_comparison_detects_a_forced_digest_collision(self) -> None:
        first = canonical_json_bytes({"value": 1})
        second = canonical_json_bytes({"value": 2})
        forced_digest = "0" * 64

        self.assertTrue(
            compare_retained_canonical_bytes(
                forced_digest,
                first,
                forced_digest,
                first,
            )
        )
        self.assertFalse(
            compare_retained_canonical_bytes(
                forced_digest,
                first,
                "1" * 64,
                second,
            )
        )
        with self.assertRaises(CanonicalHashCollision) as caught:
            compare_retained_canonical_bytes(
                forced_digest,
                first,
                forced_digest,
                second,
            )
        self.assertNotIn(first.decode(), str(caught.exception))
        self.assertNotIn(second.decode(), str(caught.exception))

    def test_retained_comparison_rejects_noncanonical_hash_or_bytes(self) -> None:
        canonical = canonical_json_bytes({"value": 1})
        with self.assertRaises(HashDomainViolation):
            compare_retained_canonical_bytes(
                "A" * 64,
                canonical,
                "0" * 64,
                canonical,
            )
        with self.assertRaises(HashDomainViolation):
            compare_retained_canonical_bytes(
                "0" * 64,
                b'{ "value":1}',
                "0" * 64,
                canonical,
            )


if __name__ == "__main__":
    unittest.main()
