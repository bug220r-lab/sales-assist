from __future__ import annotations

import unittest

from synthetic_sales_assist.safety.content import (
    VALIDATION_PRECEDENCE,
    ProhibitedCategory,
    ProhibitedInputError,
    assert_payload_safe,
    scan_payload,
    scan_text,
)


def _joined(*parts: str) -> str:
    """Construct unsafe canaries at runtime so they never exist in repository text."""

    return "".join(parts)


class ProhibitedInputCategoryTests(unittest.TestCase):
    def test_recursive_scanner_covers_every_policy_category(self) -> None:
        cases: tuple[tuple[str, object], ...] = (
            (
                ProhibitedCategory.NON_SYNTHETIC_IDENTITY,
                {"customer_id": _joined("CUSTOMER", "-94821")},
            ),
            (
                ProhibitedCategory.REAL_LOOKING_CUSTOMER_NAME,
                {"customer_name": _joined("Avery", " ", "Carter")},
            ),
            (
                ProhibitedCategory.NON_SYNTHETIC_EMAIL,
                {"customer_email": _joined("person", "@", "enterprise", ".", "example")},
            ),
            (
                ProhibitedCategory.NON_FICTIONAL_PHONE,
                {"phone": _joined("212", "-", "555", "-", "0200")},
            ),
            (
                ProhibitedCategory.REAL_LOOKING_ADDRESS,
                {"shipping_address": _joined("742", " ", "Evergreen", " ", "Road")},
            ),
            (
                ProhibitedCategory.VIN,
                {"vehicle_reference": _joined("1HG", "CM8263", "3A004352")},
            ),
            (
                ProhibitedCategory.UNWRAPPED_NUMERIC_ORDER_ID,
                {"order_id": int(_joined("123", "45678"))},
            ),
            (
                ProhibitedCategory.REAL_PRODUCT_OR_MANUFACTURER_ID,
                {"manufacturer_id": _joined("MFG", "-", "48291")},
            ),
            (
                ProhibitedCategory.COPIED_NOTES,
                {"notes": _joined("Customer", " supplied", " copied", " material")},
            ),
            (
                ProhibitedCategory.SCREENSHOT,
                {"screenshot": bytes((137, 80, 78, 71))},
            ),
            (
                ProhibitedCategory.HTML_DUMP,
                {"raw_html": _joined("<", "html>", "<body>", "copied", "</body></html>")},
            ),
            (
                ProhibitedCategory.BROWSER_STORAGE,
                {"local_storage": {"entry": _joined("opaque", "-", "value")}},
            ),
            (
                ProhibitedCategory.CREDENTIAL,
                {"password": _joined("sensitive", "-", "fixture", "-", "material")},
            ),
            (
                ProhibitedCategory.COOKIE,
                {"cookie": _joined("browser", "_state=", "opaque", "-", "fixture")},
            ),
            (
                ProhibitedCategory.TOKEN,
                {"access_token": _joined("opaque", "-", "access", "-", "material")},
            ),
            (
                ProhibitedCategory.SESSION,
                {"session_id": _joined("opaque", "-", "session", "-", "material")},
            ),
            (
                ProhibitedCategory.PRODUCTION_LOG,
                {"production_log": _joined("2026-01-01", " INFO ", "production event")},
            ),
            (
                ProhibitedCategory.COMPANY_DOMAIN,
                {"company_domain": _joined("enterprise-unit-9", ".", "com")},
            ),
            (
                ProhibitedCategory.INTERNAL_HOSTNAME,
                {"hostname": _joined("prod", "-", "db", "-", "01")},
            ),
            (
                ProhibitedCategory.CLOUD_DOCUMENT_ID,
                {"cloud_document_id": _joined("doc", "ument", "Identifier", "9482105736")},
            ),
            (
                ProhibitedCategory.PRODUCTION_SELECTOR,
                {"portal_selector": _joined("#", "customer", "-", "order", "-", "grid")},
            ),
        )

        for expected_category, payload in cases:
            with self.subTest(category=expected_category):
                findings = scan_payload({"wrapper": [payload]})
                self.assertEqual(len(findings), 1)
                self.assertEqual(findings[0].category, expected_category)
                self.assertTrue(findings[0].path.startswith("$"))

    def test_safe_synthetic_payload_passes(self) -> None:
        payload = {
            "customer_id": "SYN-CUSTOMER-000001",
            "order_id": "SYN-ORDER-000001",
            "sku": "SYN-SKU-000001",
            "rep_id": "SYN-REP-000001",
            "customer_name": "Synthetic Customer 000001",
            "customer_email": "customer.000001@example.test",
            "phone": "+1 212 555 0100",
            "shipping_address": "Synthetic Address 000001",
            "manufacturer": "Synthetic Manufacturer 000001",
            "notes": "SYNTHETIC: generated from a rule requirement",
            "hostname": "localhost",
            "url": "http://localhost/orders/SYN-ORDER-000001",
            "portal_selector": '[data-syn-field="order-number"]',
        }
        self.assertEqual(scan_payload(payload), ())
        self.assertIsNone(assert_payload_safe(payload))

    def test_opaque_and_cyclic_values_fail_closed(self) -> None:
        cycle: list[object] = []
        cycle.append(cycle)
        self.assertEqual(scan_payload(cycle)[0].category, ProhibitedCategory.CYCLIC_INPUT)
        self.assertEqual(
            scan_payload({"payload": {"unordered"}})[0].category,
            ProhibitedCategory.UNSUPPORTED_INPUT,
        )
        self.assertEqual(
            scan_payload({"payload": bytes((1, 2, 3))})[0].category,
            ProhibitedCategory.OPAQUE_BINARY,
        )


class ProhibitedInputSafetyTests(unittest.TestCase):
    def test_findings_and_exception_do_not_leak_values_or_mapping_keys(self) -> None:
        canary = _joined("opaque", "-", "material", "-", "94821057")
        field_name = _joined("access", "_", "token")
        payload = {"outer": [{field_name: canary}]}

        findings = scan_payload(payload)
        self.assertEqual(
            findings[0].path,
            "$[entry:0].value[item:0][entry:0].value",
        )
        serialized = repr(findings[0].to_dict())
        self.assertNotIn(canary, serialized)
        self.assertNotIn(field_name, serialized)

        with self.assertRaises(ProhibitedInputError) as raised:
            assert_payload_safe(payload)
        self.assertNotIn(canary, str(raised.exception))
        self.assertNotIn(field_name, str(raised.exception))

    def test_explicit_precedence_selects_one_deterministic_category(self) -> None:
        jwt_shape = _joined(
            "eyJ", "abcdefghij", ".", "abcdefghij", ".", "abcdefghij"
        )
        findings = scan_payload({"password": jwt_shape})
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].category, ProhibitedCategory.CREDENTIAL)
        self.assertLess(
            VALIDATION_PRECEDENCE.index(ProhibitedCategory.CREDENTIAL),
            VALIDATION_PRECEDENCE.index(ProhibitedCategory.TOKEN),
        )

        external_email = _joined("person", "@", "enterprise", ".", "example")
        findings = scan_text(external_email, field_name="access_token")
        self.assertEqual(findings[0].category, ProhibitedCategory.TOKEN)

    def test_caller_supplied_path_cannot_become_a_leak(self) -> None:
        external_email = _joined("person", "@", "enterprise", ".", "example")
        unsafe_path = _joined("$.", "secret", "-", "value")
        findings = scan_text(external_email, path=unsafe_path)
        self.assertEqual(findings[0].path, "$")
        self.assertNotIn(unsafe_path, repr(findings))


if __name__ == "__main__":
    unittest.main()
