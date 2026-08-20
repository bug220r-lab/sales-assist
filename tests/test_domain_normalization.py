from __future__ import annotations

import unittest
from datetime import date

from synthetic_sales_assist.domain.normalization import (
    MAX_ES_INPUT_UTF8_BYTES,
    MAX_EXACT_PROVIDER_INTEGER,
    MAX_MFG_OE_CANONICAL_BYTES,
    NormalizationError,
    ascii_four_trim,
    normalize_es_number,
    normalize_mfg_number,
    normalize_mfg_oe_number,
    normalize_order_number,
)


class AsciiFourTests(unittest.TestCase):
    def test_only_the_four_ascii_edge_characters_are_removed(self) -> None:
        self.assertEqual(ascii_four_trim(" \t\r\nVALUE\n\r\t "), "VALUE")
        self.assertEqual(ascii_four_trim("A B\tC"), "A B\tC")

        no_break_space = chr(0xA0)
        untouched = no_break_space + " VALUE " + no_break_space
        self.assertEqual(ascii_four_trim(untouched), untouched)

    def test_trim_is_strict_text_only(self) -> None:
        for value in (None, b"VALUE", 1, True):
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaises(NormalizationError):
                    ascii_four_trim(value)


class OrderNumberNormalizationTests(unittest.TestCase):
    def test_text_and_exact_provider_integer_normalize(self) -> None:
        self.assertEqual(normalize_order_number(" \t000123\r\n"), "123")
        self.assertEqual(normalize_order_number(123), "123")
        self.assertEqual(
            normalize_order_number(MAX_EXACT_PROVIDER_INTEGER),
            str(MAX_EXACT_PROVIDER_INTEGER),
        )

        exact_large_text = str(MAX_EXACT_PROVIDER_INTEGER + 2)
        self.assertEqual(normalize_order_number(exact_large_text), exact_large_text)

    def test_illegal_order_shapes_and_ambiguous_numeric_types_reject(self) -> None:
        unicode_digits = chr(0x661) + chr(0x662) + chr(0x663)
        invalid: tuple[object, ...] = (
            "",
            "000",
            "0",
            "+1",
            "-1",
            "1.0",
            "1e3",
            "1 2",
            "2026-01-01",
            unicode_digits,
            0,
            -1,
            MAX_EXACT_PROVIDER_INTEGER + 1,
            1.0,
            True,
            date(2026, 1, 1),
            None,
        )
        for value in invalid:
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaises(NormalizationError):
                    normalize_order_number(value)


class EsNumberNormalizationTests(unittest.TestCase):
    def test_numeric_core_policy_and_ascii_case_prefixes(self) -> None:
        vectors = {
            "000123": "123",
            "ES000123": "123",
            "es000123": "123",
            "Es#000123": "123",
            " eS#42\r\n": "42",
        }
        for source, expected in vectors.items():
            with self.subTest(source_length=len(source)):
                self.assertEqual(normalize_es_number(source), expected)

    def test_input_utf8_byte_boundary_is_enforced_before_canonicalization(self) -> None:
        boundary = "ES#" + "1" * (MAX_ES_INPUT_UTF8_BYTES - 3)
        self.assertEqual(normalize_es_number(boundary), boundary[3:])
        with self.assertRaisesRegex(NormalizationError, "es_input_length"):
            normalize_es_number(boundary + "1")

    def test_invalid_es_values_reject(self) -> None:
        unicode_digit = chr(0x661)
        invalid: tuple[object, ...] = (
            "",
            "ES",
            "ES#",
            "ES000",
            "ES#0",
            "ES#1 2",
            "ES-12",
            "+12",
            "1e2",
            unicode_digit,
            "ES#1\x00",
            123,
            True,
            None,
        )
        for value in invalid:
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaises(NormalizationError):
                    normalize_es_number(value)

    def test_encoding_rejection_does_not_retain_source_material(self) -> None:
        marker = "fictional" + "-private-marker"
        source = marker + "\ud800"
        with self.assertRaises(NormalizationError) as caught:
            normalize_es_number(source)
        error = caught.exception
        self.assertIsNone(error.__cause__)
        self.assertIsNone(error.__context__)
        self.assertNotIn(marker, repr(error.__dict__))


class MfgOeNormalizationTests(unittest.TestCase):
    def test_ascii_case_changes_while_separators_and_zeroes_are_preserved(self) -> None:
        source = " \tab-001 / cd__2..  ef\r\n"
        expected = "AB-001 / CD__2..  EF"
        self.assertEqual(normalize_mfg_oe_number(source), expected)
        self.assertEqual(normalize_mfg_number(source), expected)

    def test_post_trim_printable_ascii_boundary_is_exact(self) -> None:
        boundary = "a" * MAX_MFG_OE_CANONICAL_BYTES
        self.assertEqual(normalize_mfg_oe_number(" \t" + boundary + "\r"), boundary.upper())
        with self.assertRaisesRegex(NormalizationError, "mfg_oe_length"):
            normalize_mfg_oe_number(boundary + "a")

    def test_invalid_mfg_oe_values_reject_without_echo(self) -> None:
        rejected = "part" + chr(0x2603) + "number"
        invalid: tuple[object, ...] = (
            "",
            " \t\r\n",
            "ABC\x00DEF",
            "ABC\nDEF",
            rejected,
            123,
            True,
            None,
        )
        for value in invalid:
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaises(NormalizationError) as raised:
                    normalize_mfg_oe_number(value)
                if str(value):
                    self.assertNotIn(str(value), str(raised.exception))


if __name__ == "__main__":
    unittest.main()
