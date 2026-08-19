from __future__ import annotations

import unittest

from synthetic_sales_assist.safety.identity import (
    IdentityFirewallError,
    RESERVED_IDENTITY_NAMESPACES,
    assert_fictional_555_phone,
    assert_reserved_identity,
    assert_synthetic_email,
    is_fictional_555_phone,
    is_reserved_identity,
    is_synthetic_email,
    parse_reserved_identity,
)


class ReservedIdentityTests(unittest.TestCase):
    def test_every_closed_namespace_accepts_a_canonical_identity(self) -> None:
        for namespace in RESERVED_IDENTITY_NAMESPACES:
            with self.subTest(namespace=namespace):
                value = f"SYN-{namespace}-000001"
                parsed = parse_reserved_identity(value, expected_namespace=namespace)
                self.assertEqual(parsed.value, value)
                self.assertEqual(parsed.namespace, namespace)
                self.assertTrue(is_reserved_identity(value, expected_namespace=f"SYN-{namespace}"))

    def test_identity_validation_is_strict_and_does_not_normalize(self) -> None:
        invalid = (
            "syn-order-000001",
            "SYN-ORDER-",
            "SYN-ORDER-000001 ",
            " SYN-ORDER-000001",
            "SYN-ORDER-000001_2",
            "SYN-ORDER-000001--2",
            "SYN-OTHER-000001",
            100001,
            None,
        )
        for value in invalid:
            with self.subTest(value_type=type(value).__name__):
                self.assertFalse(is_reserved_identity(value))
                with self.assertRaises(IdentityFirewallError):
                    assert_reserved_identity(value)

    def test_expected_namespace_cannot_be_substituted(self) -> None:
        value = "SYN-REP-000001"
        with self.assertRaisesRegex(IdentityFirewallError, "identity_namespace_mismatch"):
            assert_reserved_identity(value, expected_namespace="ORDER")

    def test_identity_error_never_echoes_rejected_material(self) -> None:
        rejected = "OUTSIDE" + "-IDENTITY-94821"
        with self.assertRaises(IdentityFirewallError) as raised:
            assert_reserved_identity(rejected)
        self.assertNotIn(rejected, str(raised.exception))
        self.assertFalse(hasattr(raised.exception, "value"))


class SyntheticContactTests(unittest.TestCase):
    def test_email_domain_is_exactly_example_test(self) -> None:
        accepted = "synthetic.user@example.test"
        self.assertEqual(assert_synthetic_email(accepted), accepted)
        self.assertTrue(is_synthetic_email(accepted))

        rejected = (
            "synthetic.user@" + "sub." + "example.test",
            "synthetic.user@EXAMPLE.TEST",
            "Synthetic User <synthetic.user@example.test>",
            "synthetic..user@example.test",
            " synthetic.user@example.test",
        )
        for value in rejected:
            with self.subTest(shape=value.count("@")):
                self.assertFalse(is_synthetic_email(value))
                with self.assertRaises(IdentityFirewallError):
                    assert_synthetic_email(value)

        external_canary = "fixture-user" + "@" + "enterprise" + "." + "example"
        self.assertFalse(is_synthetic_email(external_canary))

    def test_only_conservative_fictional_555_numbers_are_accepted(self) -> None:
        accepted = (
            "555-0100",
            "555-0199",
            "212-555-0100",
            "(212) 555-0199",
            "+1 212 555 0150",
        )
        for value in accepted:
            with self.subTest(length=len(value)):
                self.assertTrue(is_fictional_555_phone(value))
                self.assertEqual(assert_fictional_555_phone(value), value)

        rejected = (
            "555-0099",
            "555-0200",
            "112-555-0100",
            "212-555-0100 ext 1",
            "2(1)2--555..0100",
            " 212-555-0100",
            5550100,
        )
        for value in rejected:
            with self.subTest(value_type=type(value).__name__):
                self.assertFalse(is_fictional_555_phone(value))
                with self.assertRaises(IdentityFirewallError):
                    assert_fictional_555_phone(value)


if __name__ == "__main__":
    unittest.main()
