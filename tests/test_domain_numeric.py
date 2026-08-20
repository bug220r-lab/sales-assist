"""Executable contract tests for exact Quantity and Money primitives."""

from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError
from decimal import Decimal, localcontext

from synthetic_sales_assist.domain.numeric import (
    CURRENCY_REGISTRY,
    CURRENCY_REGISTRY_VERSION,
    CurrencyDefinition,
    CurrencyMismatch,
    JSON_SAFE_INTEGER_MAXIMUM,
    Money,
    MoneyViolation,
    NonNegativeCount,
    PositiveOrdinal,
    PositiveQuantity,
    QUANTITY_MAXIMUM,
    QUANTITY_SQLITE_DECLARATION,
    Quantity,
    QuantityViolation,
    SafeIntegerViolation,
)


def _money(
    amount: str,
    *,
    currency_code: str = "USD",
    scale: int = 2,
) -> Money:
    return Money(
        amount=Decimal(amount),
        currency_code=currency_code,
        registry_version=CURRENCY_REGISTRY_VERSION,
        scale=scale,
    )


class QuantityTests(unittest.TestCase):
    def test_boundaries_are_exact_and_immutable(self) -> None:
        zero = Quantity(0)
        maximum = Quantity(QUANTITY_MAXIMUM)
        positive = PositiveQuantity(1)

        self.assertEqual(zero.to_json_value(), "0")
        self.assertEqual(maximum.to_json_value(), "999999999")
        self.assertEqual(positive.to_json_value(), "1")
        with self.assertRaises(FrozenInstanceError):
            zero.value = 1  # type: ignore[misc]

    def test_constructor_rejects_wrong_types_and_out_of_range_values(self) -> None:
        invalid: tuple[object, ...] = (
            -1,
            QUANTITY_MAXIMUM + 1,
            True,
            1.0,
            Decimal("1"),
            "1",
            None,
        )
        for value in invalid:
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaises(QuantityViolation):
                    Quantity(value)  # type: ignore[arg-type]

    def test_json_string_roundtrip_and_positive_specialization(self) -> None:
        for text in ("0", "1", "42", "999999999"):
            with self.subTest(text=text):
                quantity = Quantity.from_json_value(text)
                self.assertEqual(quantity.to_json_value(), text)
                self.assertEqual(
                    Quantity.from_sqlite_text(quantity.to_sqlite_value()), quantity
                )
        self.assertEqual(QUANTITY_SQLITE_DECLARATION, "TEXT COLLATE BINARY")

        for text in ("1", "999999999"):
            with self.subTest(text=text):
                self.assertEqual(PositiveQuantity.from_json_value(text).to_json_value(), text)
        with self.assertRaises(QuantityViolation):
            PositiveQuantity.from_json_value("0")

    def test_json_rejects_numeric_aliases_signs_exponents_and_ambiguous_forms(self) -> None:
        rejected: tuple[object, ...] = (
            0,
            1,
            1.0,
            True,
            "",
            "00",
            "01",
            "+1",
            "-0",
            "-1",
            "1.0",
            "1e0",
            "1,000",
            " 1",
            "1 ",
            "1000000000",
        )
        for value in rejected:
            with self.subTest(value=value):
                with self.assertRaises(QuantityViolation):
                    Quantity.from_json_value(value)

    def test_exact_decimal_source_text_normalizes_only_zero_fraction(self) -> None:
        accepted = {
            "0": 0,
            "7": 7,
            "0.0": 0,
            "7.000": 7,
            "999999999.000000": QUANTITY_MAXIMUM,
        }
        for text, expected in accepted.items():
            with self.subTest(text=text):
                self.assertEqual(
                    Quantity.from_source_text(
                        text,
                        exact_decimal_source="." in text,
                    ).value,
                    expected,
                )

        rejected = (
            ("7.0", False),
            ("7.1", True),
            ("7.0001", True),
            ("01.0", True),
            ("+7.0", True),
            ("-7.0", True),
            ("7e0", True),
            ("7,0", True),
            (" 7.0", True),
            ("1000000000.0", True),
        )
        for text, exact in rejected:
            with self.subTest(text=text, exact=exact):
                with self.assertRaises(QuantityViolation):
                    Quantity.from_source_text(text, exact_decimal_source=exact)


class SafeIntegerTests(unittest.TestCase):
    def test_count_and_ordinal_have_distinct_exact_json_integer_boundaries(self) -> None:
        self.assertEqual(NonNegativeCount(0).to_json_value(), 0)
        self.assertEqual(
            NonNegativeCount(JSON_SAFE_INTEGER_MAXIMUM).to_json_value(),
            JSON_SAFE_INTEGER_MAXIMUM,
        )
        self.assertEqual(PositiveOrdinal(1).to_json_value(), 1)
        self.assertEqual(
            PositiveOrdinal(JSON_SAFE_INTEGER_MAXIMUM).to_json_value(),
            JSON_SAFE_INTEGER_MAXIMUM,
        )
        self.assertIs(type(NonNegativeCount(1).to_json_value()), int)
        self.assertNotEqual(NonNegativeCount(1), Quantity(1))

    def test_count_and_ordinal_reject_aliases_and_out_of_range_values(self) -> None:
        count_values: tuple[object, ...] = (
            -1,
            JSON_SAFE_INTEGER_MAXIMUM + 1,
            True,
            1.0,
            "1",
            None,
        )
        ordinal_values: tuple[object, ...] = (
            0,
            -1,
            JSON_SAFE_INTEGER_MAXIMUM + 1,
            True,
            1.0,
            "1",
            None,
        )
        for value in count_values:
            with self.subTest(kind="count", value_type=type(value).__name__):
                with self.assertRaises(SafeIntegerViolation):
                    NonNegativeCount(value)  # type: ignore[arg-type]
        for value in ordinal_values:
            with self.subTest(kind="ordinal", value_type=type(value).__name__):
                with self.assertRaises(SafeIntegerViolation):
                    PositiveOrdinal(value)  # type: ignore[arg-type]

class MoneyRegistryTests(unittest.TestCase):
    def test_currency_definition_rejects_wrong_types_with_domain_error(self) -> None:
        class VersionSubclass(str):
            pass

        class EqualToVersion:
            def __eq__(self, other: object) -> bool:
                return True

        invalid_codes: tuple[object, ...] = (123, b"USD", None, True)
        for value in invalid_codes:
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaises(MoneyViolation):
                    CurrencyDefinition(  # type: ignore[arg-type]
                        value, 2, CURRENCY_REGISTRY_VERSION
                    )
        invalid_versions: tuple[object, ...] = (
            VersionSubclass(CURRENCY_REGISTRY_VERSION),
            EqualToVersion(),
            None,
        )
        for value in invalid_versions:
            with self.subTest(version_type=type(value).__name__):
                with self.assertRaises(MoneyViolation):
                    CurrencyDefinition("USD", 2, value)  # type: ignore[arg-type]

    def test_registry_is_closed_versioned_and_has_explicit_scales(self) -> None:
        self.assertEqual(
            {code: item.scale for code, item in CURRENCY_REGISTRY.items()},
            {"EUR": 2, "JPY": 0, "KWD": 3, "USD": 2},
        )
        self.assertEqual(
            {item.registry_version for item in CURRENCY_REGISTRY.values()},
            {CURRENCY_REGISTRY_VERSION},
        )
        with self.assertRaises(TypeError):
            CURRENCY_REGISTRY["NEW"] = CURRENCY_REGISTRY["USD"]  # type: ignore[index]

    def test_decimal_only_money_roundtrips_through_closed_json(self) -> None:
        value = _money("12.34")
        expected_json = {
            "amount": "12.34",
            "currency_code": "USD",
            "currency_registry_version": CURRENCY_REGISTRY_VERSION,
            "currency_scale": 2,
        }
        self.assertEqual(value.minor_units, 1234)
        self.assertEqual(value.to_json_value(), expected_json)
        self.assertEqual(Money.from_json_value(expected_json), value)
        self.assertNotIn("_minor_units", repr(value))

    def test_each_registered_scale_has_one_exact_roundtrip(self) -> None:
        examples = (
            ("EUR", 2, "12.34", 1234),
            ("JPY", 0, "12", 12),
            ("KWD", 3, "12.345", 12345),
            ("KWD", 3, "-0.125", -125),
            ("USD", 2, "0.10", 10),
        )
        for code, scale, text, minor_units in examples:
            with self.subTest(currency=code):
                value = _money(text, currency_code=code, scale=scale)
                self.assertEqual(value.minor_units, minor_units)
                self.assertEqual(Money.from_json_value(value.to_json_value()), value)

    def test_constructor_rejects_float_coercion_nonfinite_and_wrong_scale(self) -> None:
        rejected_amounts: tuple[object, ...] = (
            1,
            1.0,
            "1.00",
            Decimal("1"),
            Decimal("1.0"),
            Decimal("1.000"),
            Decimal("NaN"),
            Decimal("Infinity"),
            Decimal("-Infinity"),
            Decimal("-0.00"),
        )
        for amount in rejected_amounts:
            with self.subTest(amount_type=type(amount).__name__, amount=repr(amount)):
                with self.assertRaises(MoneyViolation):
                    Money(
                        amount=amount,  # type: ignore[arg-type]
                        currency_code="USD",
                        registry_version=CURRENCY_REGISTRY_VERSION,
                        scale=2,
                    )

    def test_code_version_and_scale_are_explicit_with_no_default_currency(self) -> None:
        invalid_bindings: tuple[tuple[object, object, object], ...] = (
            ("usd", CURRENCY_REGISTRY_VERSION, 2),
            ("CAD", CURRENCY_REGISTRY_VERSION, 2),
            ("USD", "synthetic-iso-style-currency-registry/v2", 2),
            ("USD", CURRENCY_REGISTRY_VERSION, 3),
            ("USD", CURRENCY_REGISTRY_VERSION, True),
            (None, CURRENCY_REGISTRY_VERSION, 2),
        )
        for code, version, scale in invalid_bindings:
            with self.subTest(code_type=type(code).__name__, scale=scale):
                with self.assertRaises(MoneyViolation):
                    Money(
                        amount=Decimal("1.00"),
                        currency_code=code,  # type: ignore[arg-type]
                        registry_version=version,  # type: ignore[arg-type]
                        scale=scale,  # type: ignore[arg-type]
                    )

    def test_json_rejects_unknown_missing_and_noncanonical_amount_members(self) -> None:
        base: dict[str, object] = {
            "amount": "1.00",
            "currency_code": "USD",
            "currency_registry_version": CURRENCY_REGISTRY_VERSION,
            "currency_scale": 2,
        }
        private_member = "sensitive" + "_money_member"
        variants: list[object] = [
            {key: value for key, value in base.items() if key != "amount"},
            {**base, private_member: "not-retained"},
            {**base, "amount": 1.00},
            {**base, "amount": "+1.00"},
            {**base, "amount": "01.00"},
            {**base, "amount": "1.0"},
            {**base, "amount": "1.000"},
            {**base, "amount": "1e0"},
            {**base, "amount": "-0.00"},
        ]
        for value in variants:
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaises(MoneyViolation) as caught:
                    Money.from_json_value(value)
                self.assertNotIn(private_member, str(caught.exception))
                self.assertNotIn("not-retained", str(caught.exception))


class ExactMoneyArithmeticTests(unittest.TestCase):
    def test_quantity_subclass_cannot_bypass_money_invariants(self) -> None:
        class UnvalidatedQuantity(Quantity):
            def __post_init__(self) -> None:
                pass

        invalid = UnvalidatedQuantity(-7)
        with self.assertRaises(MoneyViolation):
            _money("1.00").multiply(invalid)

    def test_add_subtract_and_quantity_product_ignore_decimal_context_rounding(self) -> None:
        with localcontext() as context:
            context.prec = 1
            total = _money("99.99") + _money("0.02")
            difference = _money("0.10") - _money("0.30")
            product = _money("0.10").multiply(Quantity(999_999_999))

        self.assertEqual(total.to_json_value()["amount"], "100.01")
        self.assertEqual(difference.to_json_value()["amount"], "-0.20")
        self.assertEqual(Money.from_json_value(difference.to_json_value()), difference)
        self.assertEqual(product.to_json_value()["amount"], "99999999.90")

    def test_mixed_currency_sum_and_non_money_coercion_are_prohibited(self) -> None:
        usd = _money("1.00", currency_code="USD", scale=2)
        eur = _money("1.00", currency_code="EUR", scale=2)
        with self.assertRaises(CurrencyMismatch):
            _ = usd + eur
        with self.assertRaises(MoneyViolation):
            _ = usd + Decimal("1.00")
        with self.assertRaises(TypeError):
            _ = usd * 2

    def test_from_minor_units_is_exact_and_requires_full_binding(self) -> None:
        value = Money.from_minor_units(
            -12345,
            currency_code="KWD",
            registry_version=CURRENCY_REGISTRY_VERSION,
            scale=3,
        )
        self.assertEqual(value.amount, Decimal("-12.345"))
        self.assertEqual(value.minor_units, -12345)


if __name__ == "__main__":
    unittest.main()
