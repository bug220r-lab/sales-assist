"""Exact, immutable Quantity and Money primitives.

Money construction is Decimal-only and binds every value to the closed currency registry,
its version, and its scale.  Arithmetic uses integer minor units so ambient Decimal context
cannot round a business value.  This module performs no currency conversion.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from types import MappingProxyType
from typing import ClassVar, cast


QUANTITY_MINIMUM = 0
QUANTITY_MAXIMUM = 999_999_999
QUANTITY_GRAMMAR = r"0|[1-9][0-9]{0,8}"
QUANTITY_SQLITE_TYPE = "TEXT"
QUANTITY_SQLITE_COLLATION = "BINARY"
QUANTITY_SQLITE_DECLARATION = "TEXT COLLATE BINARY"
_QUANTITY_PATTERN = re.compile(rf"^(?:{QUANTITY_GRAMMAR})$", re.ASCII)
_EXACT_DECIMAL_QUANTITY_PATTERN = re.compile(
    r"^(0|[1-9][0-9]{0,8})\.([0-9]+)$",
    re.ASCII,
)

CURRENCY_REGISTRY_VERSION = "synthetic-iso-style-currency-registry/v1"
JSON_SAFE_INTEGER_MAXIMUM = 9_007_199_254_740_991


class QuantityViolation(ValueError):
    """Raised when a quantity is outside its exact closed representation."""


class SafeIntegerViolation(ValueError):
    """Raised when a count or ordinal is not an exact JSON-safe integer."""


class MoneyViolation(ValueError):
    """Raised when a monetary value lacks an exact registry binding."""


class CurrencyMismatch(MoneyViolation):
    """Raised when arithmetic would combine distinct currency bindings."""


@dataclass(frozen=True, slots=True)
class CurrencyDefinition:
    """One immutable entry in the versioned minimal currency registry."""

    code: str
    scale: int
    registry_version: str

    def __post_init__(self) -> None:
        if type(self.code) is not str or not re.fullmatch(
            r"[A-Z]{3}", self.code, flags=re.ASCII
        ):
            raise MoneyViolation("currency registry code must use three uppercase letters")
        if type(self.scale) is not int or not 0 <= self.scale <= 9:
            raise MoneyViolation("currency registry scale is invalid")
        if (
            type(self.registry_version) is not str
            or self.registry_version != CURRENCY_REGISTRY_VERSION
        ):
            raise MoneyViolation("currency registry version is invalid")


_CURRENCY_DEFINITIONS = (
    CurrencyDefinition("EUR", 2, CURRENCY_REGISTRY_VERSION),
    CurrencyDefinition("JPY", 0, CURRENCY_REGISTRY_VERSION),
    CurrencyDefinition("KWD", 3, CURRENCY_REGISTRY_VERSION),
    CurrencyDefinition("USD", 2, CURRENCY_REGISTRY_VERSION),
)
CURRENCY_REGISTRY = MappingProxyType(
    {definition.code: definition for definition in _CURRENCY_DEFINITIONS}
)


@dataclass(frozen=True, slots=True)
class Quantity:
    """A governed nonnegative integer quantity serialized to JSON as a string."""

    value: int

    MINIMUM: ClassVar[int] = QUANTITY_MINIMUM
    MAXIMUM: ClassVar[int] = QUANTITY_MAXIMUM

    def __post_init__(self) -> None:
        if type(self.value) is not int:
            raise QuantityViolation("quantity must be an exact integer")
        if not self.MINIMUM <= self.value <= self.MAXIMUM:
            raise QuantityViolation("quantity is outside the governed range")

    @classmethod
    def from_json_value(cls, value: object) -> Quantity:
        """Parse the immutable JSON string representation without coercion."""

        if type(value) is not str:
            raise QuantityViolation("quantity JSON must use the canonical string grammar")
        text = cast(str, value)
        if not _QUANTITY_PATTERN.fullmatch(text):
            raise QuantityViolation("quantity JSON must use the canonical string grammar")
        return cls(int(text))

    @classmethod
    def from_source_text(
        cls, value: object, *, exact_decimal_source: bool = False
    ) -> Quantity:
        """Normalize exact source text under the governed integer-only decision.

        Canonical integer text needs no decimal normalization.  Decimal text is accepted
        only with an explicit exact-source proof and only when every fractional digit is
        zero.  No sign, exponent, comma, whitespace, leading zero, or rounding is accepted.
        """

        if type(value) is not str:
            raise QuantityViolation("quantity source text must be a string")
        source_text = cast(str, value)
        if _QUANTITY_PATTERN.fullmatch(source_text):
            return cls(int(source_text))
        decimal_match = _EXACT_DECIMAL_QUANTITY_PATTERN.fullmatch(source_text)
        if (
            decimal_match is None
            or exact_decimal_source is not True
            or any(digit != "0" for digit in decimal_match.group(2))
        ):
            raise QuantityViolation("quantity source text is not an exact integer")
        return cls(int(decimal_match.group(1)))

    def to_json_value(self) -> str:
        return str(self.value)

    @classmethod
    def from_sqlite_text(cls, value: object) -> Quantity:
        """Load only the canonical text used by SQLite logical storage."""

        return cls.from_json_value(value)

    def to_sqlite_value(self) -> str:
        return self.to_json_value()

    def __str__(self) -> str:
        return self.to_json_value()


@dataclass(frozen=True, slots=True)
class PositiveQuantity(Quantity):
    """A scoped or moved quantity whose governed minimum is one."""

    MINIMUM: ClassVar[int] = 1


@dataclass(frozen=True, slots=True)
class NonNegativeCount:
    """A nonnegative JSON counter, deliberately distinct from business Quantity."""

    value: int

    def __post_init__(self) -> None:
        if (
            type(self.value) is not int
            or self.value < 0
            or self.value > JSON_SAFE_INTEGER_MAXIMUM
        ):
            raise SafeIntegerViolation("count must be an exact nonnegative safe integer")

    def to_json_value(self) -> int:
        return self.value


@dataclass(frozen=True, slots=True)
class PositiveOrdinal:
    """A positive JSON-safe sequence position, distinct from counts and quantities."""

    value: int

    def __post_init__(self) -> None:
        if (
            type(self.value) is not int
            or self.value < 1
            or self.value > JSON_SAFE_INTEGER_MAXIMUM
        ):
            raise SafeIntegerViolation("ordinal must be an exact positive safe integer")

    def to_json_value(self) -> int:
        return self.value


def _currency_definition(
    currency_code: object, registry_version: object, scale: object
) -> CurrencyDefinition:
    if type(currency_code) is not str:
        raise MoneyViolation("currency code must be an explicit string")
    if type(registry_version) is not str:
        raise MoneyViolation("currency registry version must be explicit")
    if type(scale) is not int:
        raise MoneyViolation("currency scale must be an explicit integer")
    code = cast(str, currency_code)
    version = cast(str, registry_version)
    exact_scale = cast(int, scale)
    definition = CURRENCY_REGISTRY.get(code)
    if (
        definition is None
        or version != definition.registry_version
        or exact_scale != definition.scale
    ):
        raise MoneyViolation("currency code, registry version, or scale is invalid")
    return definition


def _minor_units_from_decimal(amount: Decimal, scale: int) -> int:
    if type(amount) is not Decimal:
        raise MoneyViolation("money amount must be an explicit Decimal")
    if not amount.is_finite():
        raise MoneyViolation("money amount must be finite")
    decimal_tuple = amount.as_tuple()
    if decimal_tuple.exponent != -scale:
        raise MoneyViolation("money amount does not use the registry scale")
    if amount.is_zero() and amount.is_signed():
        raise MoneyViolation("negative zero is a noncanonical money amount")
    coefficient = 0
    for digit in decimal_tuple.digits:
        coefficient = coefficient * 10 + digit
    return -coefficient if decimal_tuple.sign else coefficient


def _decimal_from_minor_units(minor_units: int, scale: int) -> Decimal:
    if type(minor_units) is not int:
        raise MoneyViolation("minor units must be an exact integer")
    sign = 1 if minor_units < 0 else 0
    digits_text = str(abs(minor_units))
    digits = tuple(int(character) for character in digits_text)
    return Decimal((sign, digits, -scale))


def _money_amount_pattern(scale: int) -> re.Pattern[str]:
    if scale == 0:
        return re.compile(r"^-?(?:0|[1-9][0-9]*)$", re.ASCII)
    return re.compile(
        rf"^-?(?:0|[1-9][0-9]*)\.[0-9]{{{scale}}}$",
        re.ASCII,
    )


@dataclass(frozen=True, slots=True)
class Money:
    """Exact decimal money with an explicit closed registry/version/scale binding."""

    amount: Decimal
    currency_code: str
    registry_version: str
    scale: int
    _minor_units: int = field(init=False, repr=False, compare=False)

    JSON_MEMBERS: ClassVar[frozenset[str]] = frozenset(
        {
            "amount",
            "currency_code",
            "currency_registry_version",
            "currency_scale",
        }
    )

    def __post_init__(self) -> None:
        definition = _currency_definition(
            self.currency_code,
            self.registry_version,
            self.scale,
        )
        minor_units = _minor_units_from_decimal(self.amount, definition.scale)
        object.__setattr__(self, "_minor_units", minor_units)

    @property
    def minor_units(self) -> int:
        return self._minor_units

    @classmethod
    def from_minor_units(
        cls,
        minor_units: int,
        *,
        currency_code: str,
        registry_version: str,
        scale: int,
    ) -> Money:
        definition = _currency_definition(currency_code, registry_version, scale)
        amount = _decimal_from_minor_units(minor_units, definition.scale)
        return cls(
            amount=amount,
            currency_code=currency_code,
            registry_version=registry_version,
            scale=scale,
        )

    @classmethod
    def from_json_value(cls, value: object) -> Money:
        """Parse the exact closed JSON object without aliases or defaults."""

        if type(value) is not dict:
            raise MoneyViolation("money JSON members do not match the closed schema")
        money_object = cast(dict[object, object], value)
        if frozenset(money_object) != cls.JSON_MEMBERS:
            raise MoneyViolation("money JSON members do not match the closed schema")
        amount_text = money_object["amount"]
        currency_code = money_object["currency_code"]
        registry_version = money_object["currency_registry_version"]
        scale = money_object["currency_scale"]
        definition = _currency_definition(currency_code, registry_version, scale)
        if type(amount_text) is not str:
            raise MoneyViolation("money amount text is noncanonical")
        amount_string = cast(str, amount_text)
        if not _money_amount_pattern(definition.scale).fullmatch(amount_string):
            raise MoneyViolation("money amount text is noncanonical")
        return cls(
            amount=Decimal(amount_string),
            currency_code=definition.code,
            registry_version=definition.registry_version,
            scale=definition.scale,
        )

    def to_json_value(self) -> dict[str, object]:
        return {
            "amount": format(self.amount, "f"),
            "currency_code": self.currency_code,
            "currency_registry_version": self.registry_version,
            "currency_scale": self.scale,
        }

    def _require_same_binding(self, other: object) -> Money:
        if type(other) is not Money:
            raise MoneyViolation("money arithmetic requires another Money value")
        accepted = cast(Money, other)
        if (
            self.currency_code != accepted.currency_code
            or self.registry_version != accepted.registry_version
            or self.scale != accepted.scale
        ):
            raise CurrencyMismatch("mixed-currency arithmetic is prohibited")
        return accepted

    def __add__(self, other: object) -> Money:
        accepted = self._require_same_binding(other)
        return Money.from_minor_units(
            self.minor_units + accepted.minor_units,
            currency_code=self.currency_code,
            registry_version=self.registry_version,
            scale=self.scale,
        )

    def __sub__(self, other: object) -> Money:
        accepted = self._require_same_binding(other)
        return Money.from_minor_units(
            self.minor_units - accepted.minor_units,
            currency_code=self.currency_code,
            registry_version=self.registry_version,
            scale=self.scale,
        )

    def multiply(self, quantity: Quantity) -> Money:
        """Return exact quantity times money without consulting Decimal context."""

        if type(quantity) not in {Quantity, PositiveQuantity}:
            raise MoneyViolation("money multiplication requires Quantity")
        return Money.from_minor_units(
            self.minor_units * quantity.value,
            currency_code=self.currency_code,
            registry_version=self.registry_version,
            scale=self.scale,
        )


__all__ = [
    "CURRENCY_REGISTRY",
    "CURRENCY_REGISTRY_VERSION",
    "CurrencyDefinition",
    "CurrencyMismatch",
    "JSON_SAFE_INTEGER_MAXIMUM",
    "Money",
    "MoneyViolation",
    "NonNegativeCount",
    "PositiveOrdinal",
    "PositiveQuantity",
    "QUANTITY_GRAMMAR",
    "QUANTITY_MAXIMUM",
    "QUANTITY_MINIMUM",
    "QUANTITY_SQLITE_COLLATION",
    "QUANTITY_SQLITE_DECLARATION",
    "QUANTITY_SQLITE_TYPE",
    "Quantity",
    "QuantityViolation",
    "SafeIntegerViolation",
]
