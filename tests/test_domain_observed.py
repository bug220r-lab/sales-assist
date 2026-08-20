from __future__ import annotations

import json
import unittest
from dataclasses import FrozenInstanceError
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import cast

from synthetic_sales_assist.domain.observed import (
    FINDING_PRESENCE_VERSION,
    OBSERVED_TAGGED_VALUE_VERSION,
    RAW_HINT_CODES,
    RAW_HINT_MAX_UTF8_BYTES,
    FindingPresenceV2,
    KnownObservedValue,
    NotApplicableObservedValue,
    ObservedTag,
    ObservedTaggedValue,
    ObservedValueError,
    UnknownObservedValue,
    parse_finding_presence,
    parse_observed_tagged_value,
    parse_observed_tagged_value_json,
)
from synthetic_sales_assist.domain.numeric import Quantity


UNKNOWN_REASONS = frozenset({"RC-016"})
AVAILABILITY_HINTS = frozenset(
    {
        "CONTRADICTORY_AVAILABILITY_TOKENS",
        "UNRECOGNIZED_AVAILABILITY_TOKEN",
    }
)


def parse_known_token(value: object) -> str:
    if not isinstance(value, str) or value not in {"IN_STOCK", "OUT_OF_STOCK"}:
        raise ValueError("closed known token")
    return value


def wrapper(
    tag: str,
    *,
    value: object = None,
    reason_code: object = None,
    raw_hint: object = None,
) -> dict[str, object]:
    return {
        "raw_hint": raw_hint,
        "reason_code": reason_code,
        "tag": tag,
        "value": value,
    }


def parse(
    payload: dict[str, object], *, allow_not_applicable: bool = True
) -> ObservedTaggedValue[str]:
    return parse_observed_tagged_value(
        payload,
        version=OBSERVED_TAGGED_VALUE_VERSION,
        known_value_parser=parse_known_token,
        allowed_unknown_reasons=UNKNOWN_REASONS,
        allowed_raw_hints=AVAILABILITY_HINTS,
        allow_not_applicable=allow_not_applicable,
    )


class ObservedTaggedValueTests(unittest.TestCase):
    def test_closed_observation_enum_members_reject_mutation(self) -> None:
        for member in (ObservedTag.KNOWN, FindingPresenceV2.PRESENT):
            with self.subTest(enum_type=type(member).__name__):
                with self.assertRaises(AttributeError):
                    member._value_ = "MUTATED"  # type: ignore[misc]
                with self.assertRaises(AttributeError):
                    member.extra = []  # type: ignore[attr-defined]
                with self.assertRaises(TypeError):
                    member.__dict__["_value_"] = "MUTATED"
                raw_state = object.__getattribute__(member, "__dict__")
                original_value = raw_state["_value_"]
                try:
                    raw_state["_value_"] = "MUTATED"
                    self.assertEqual(member.value, str.__str__(member))
                finally:
                    raw_state["_value_"] = original_value

    def test_known_branch_round_trips_with_exact_closed_members(self) -> None:
        original = wrapper("KNOWN", value="IN_STOCK")
        observed = parse(original)

        self.assertIsInstance(observed, KnownObservedValue)
        self.assertEqual(observed.tag, ObservedTag.KNOWN)
        self.assertEqual(observed.value, "IN_STOCK")
        self.assertIsNone(observed.reason_code)
        self.assertIsNone(observed.raw_hint)
        self.assertEqual(tuple(observed.to_mapping()), ("raw_hint", "reason_code", "tag", "value"))
        self.assertEqual(observed.to_mapping(), original)

        encoded = json.dumps(original, separators=(",", ":"))
        decoded = parse_observed_tagged_value_json(
            encoded,
            version=OBSERVED_TAGGED_VALUE_VERSION,
            known_value_parser=parse_known_token,
            allowed_unknown_reasons=UNKNOWN_REASONS,
            allowed_raw_hints=AVAILABILITY_HINTS,
        )
        self.assertEqual(decoded, observed)

    def test_unknown_branch_requires_exact_reason_and_optional_allowlisted_hint(self) -> None:
        without_hint = parse(wrapper("UNKNOWN", reason_code="RC-016"))
        with_hint = parse(
            wrapper(
                "UNKNOWN",
                reason_code="RC-016",
                raw_hint="UNRECOGNIZED_AVAILABILITY_TOKEN",
            )
        )

        self.assertIsInstance(without_hint, UnknownObservedValue)
        self.assertEqual(without_hint.to_mapping(), wrapper("UNKNOWN", reason_code="RC-016"))
        self.assertEqual(
            with_hint.to_mapping(),
            wrapper(
                "UNKNOWN",
                reason_code="RC-016",
                raw_hint="UNRECOGNIZED_AVAILABILITY_TOKEN",
            ),
        )

    def test_not_applicable_is_distinct_from_unknown_and_missing(self) -> None:
        observed = parse(wrapper("NOT_APPLICABLE"))
        self.assertIsInstance(observed, NotApplicableObservedValue)
        self.assertEqual(observed.tag, ObservedTag.NOT_APPLICABLE)
        self.assertEqual(observed.to_mapping(), wrapper("NOT_APPLICABLE"))

        with self.assertRaises(ObservedValueError):
            parse(wrapper("NOT_APPLICABLE"), allow_not_applicable=False)

    def test_branch_instances_are_frozen_and_known_rejects_mutable_values(self) -> None:
        known = cast(KnownObservedValue[str], parse(wrapper("KNOWN", value="IN_STOCK")))
        unknown = cast(UnknownObservedValue, parse(wrapper("UNKNOWN", reason_code="RC-016")))

        with self.assertRaises(FrozenInstanceError):
            known.value = "OUT_OF_STOCK"  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            unknown.reason_code = "RC-017"  # type: ignore[misc]
        with self.assertRaises(ObservedValueError):
            KnownObservedValue(["mutable"])
        with self.assertRaises(ObservedValueError):
            KnownObservedValue(("nested", ["mutable"]))
        with self.assertRaises(ObservedValueError):
            KnownObservedValue("UNKNOWN")

        backing = {"state": "before"}
        indirect_mutable = MappingProxyType(backing)
        with self.assertRaises(ObservedValueError):
            parse_observed_tagged_value(
                wrapper("KNOWN", value="IN_STOCK"),
                version=OBSERVED_TAGGED_VALUE_VERSION,
                known_value_parser=lambda _: indirect_mutable,
                allowed_unknown_reasons=UNKNOWN_REASONS,
            )

        class MutableUserObject:
            def __init__(self) -> None:
                self.state = "before"

        with self.assertRaises(ObservedValueError):
            parse_observed_tagged_value(
                wrapper("KNOWN", value="IN_STOCK"),
                version=OBSERVED_TAGGED_VALUE_VERSION,
                known_value_parser=lambda _: MutableUserObject(),
                allowed_unknown_reasons=UNKNOWN_REASONS,
            )

    def test_known_construction_is_parser_gated_and_repr_is_redacted(self) -> None:
        canary = "SYNTHETIC_PRIVATE_CANARY"
        with self.assertRaises(ObservedValueError):
            KnownObservedValue(canary)

        observed = parse_observed_tagged_value(
            wrapper("KNOWN", value=canary),
            version=OBSERVED_TAGGED_VALUE_VERSION,
            known_value_parser=lambda value: value,
            allowed_unknown_reasons=UNKNOWN_REASONS,
        )
        self.assertNotIn(canary, repr(observed))

        closed = Quantity(7)
        parsed = parse_observed_tagged_value(
            wrapper("KNOWN", value="SAFE"),
            version=OBSERVED_TAGGED_VALUE_VERSION,
            known_value_parser=lambda _: closed,
            allowed_unknown_reasons=UNKNOWN_REASONS,
        )
        self.assertIs(cast(KnownObservedValue[Quantity], parsed).value, closed)

    def test_known_parser_rejects_subclass_and_unregistered_object_mutability(self) -> None:
        class DecimalSubclass(Decimal):
            pass

        class MutableEnum(StrEnum):
            VALUE = "VALUE"

        decimal_value = DecimalSubclass("1")
        decimal_value.extra = []
        enum_value = MutableEnum.VALUE
        enum_value.extra = []
        for value in (decimal_value, enum_value):
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaises(ObservedValueError):
                    parse_observed_tagged_value(
                        wrapper("KNOWN", value="SAFE"),
                        version=OBSERVED_TAGGED_VALUE_VERSION,
                        known_value_parser=lambda _, result=value: result,
                        allowed_unknown_reasons=UNKNOWN_REASONS,
                    )

    def test_direct_parser_rejects_mapping_and_string_subclass_aliases(self) -> None:
        class StringSubclass(str):
            pass

        canonical = wrapper("KNOWN", value="IN_STOCK")
        with self.assertRaises(ObservedValueError):
            parse_observed_tagged_value(
                MappingProxyType(canonical),
                version=OBSERVED_TAGGED_VALUE_VERSION,
                known_value_parser=parse_known_token,
                allowed_unknown_reasons=UNKNOWN_REASONS,
            )
        canonical["tag"] = StringSubclass("KNOWN")
        with self.assertRaises(ObservedValueError):
            parse(canonical)

    def test_missing_extra_and_alias_members_are_rejected_without_reflection(self) -> None:
        cases: list[tuple[str, dict[str, object]]] = []
        missing = wrapper("KNOWN", value="IN_STOCK")
        missing.pop("raw_hint")
        cases.append(("missing", missing))

        extra = wrapper("KNOWN", value="IN_STOCK")
        extra["schema_version"] = OBSERVED_TAGGED_VALUE_VERSION
        cases.append(("extra", extra))

        alias = wrapper("known", value="IN_STOCK")
        cases.append(("alias", alias))

        forbidden = wrapper("ABSENT")
        cases.append(("forbidden", forbidden))

        for canary, payload in cases:
            with self.subTest(case=canary):
                with self.assertRaises(ObservedValueError) as caught:
                    parse(payload)
                self.assertEqual(str(caught.exception), "observed tagged value rejected")
                self.assertNotIn(canary, str(caught.exception))

    def test_every_illegal_null_partition_is_rejected(self) -> None:
        invalid = (
            wrapper("KNOWN"),
            wrapper("KNOWN", value="IN_STOCK", reason_code="RC-016"),
            wrapper("KNOWN", value="IN_STOCK", raw_hint="UNRECOGNIZED_AVAILABILITY_TOKEN"),
            wrapper("UNKNOWN", value="IN_STOCK", reason_code="RC-016"),
            wrapper("UNKNOWN"),
            wrapper("UNKNOWN", reason_code="RC-017"),
            wrapper("NOT_APPLICABLE", value="IN_STOCK"),
            wrapper("NOT_APPLICABLE", reason_code="RC-016"),
            wrapper("NOT_APPLICABLE", raw_hint="UNRECOGNIZED_AVAILABILITY_TOKEN"),
        )
        for payload in invalid:
            with self.subTest(tag=payload["tag"]):
                with self.assertRaises(ObservedValueError):
                    parse(payload)

    def test_wrong_version_is_rejected_without_echo(self) -> None:
        wrong_version = "doi-observed-tagged-value/r01-v" + "999"
        with self.assertRaises(ObservedValueError) as caught:
            parse_observed_tagged_value(
                wrapper("KNOWN", value="IN_STOCK"),
                version=wrong_version,
                known_value_parser=parse_known_token,
                allowed_unknown_reasons=UNKNOWN_REASONS,
            )
        self.assertNotIn(wrong_version, str(caught.exception))

    def test_raw_hints_are_closed_bounded_and_never_customer_text(self) -> None:
        self.assertTrue(RAW_HINT_CODES)
        self.assertTrue(
            all(len(value.encode("utf-8")) <= RAW_HINT_MAX_UTF8_BYTES for value in RAW_HINT_CODES)
        )

        privacy_canaries = (
            "fictional" + ".person" + "@" + "example" + ".test",
            "202" + "-555-0107",
            "copied" + " customer note",
            "A" * (RAW_HINT_MAX_UTF8_BYTES + 1),
        )
        for canary in privacy_canaries:
            with self.subTest(canary_size=len(canary)):
                with self.assertRaises(ObservedValueError) as caught:
                    parse_observed_tagged_value(
                        wrapper("UNKNOWN", reason_code="RC-016", raw_hint=canary),
                        version=OBSERVED_TAGGED_VALUE_VERSION,
                        known_value_parser=parse_known_token,
                        allowed_unknown_reasons=UNKNOWN_REASONS,
                        allowed_raw_hints=frozenset({canary}),
                    )
                self.assertNotIn(canary, str(caught.exception))

    def test_reason_code_boundaries_and_wrong_field_reason_fail_closed(self) -> None:
        for reason in ("RC-001", "RC-138"):
            observed = UnknownObservedValue(
                reason,
                allowed_reason_codes=frozenset({reason}),
            )
            self.assertEqual(observed.reason_code, reason)

        for reason in ("RC-000", "RC-139", "RC-999"):
            with self.subTest(reason=reason):
                with self.assertRaises(ObservedValueError):
                    UnknownObservedValue(
                        reason,
                        allowed_reason_codes=frozenset({reason}),
                    )

    def test_json_entry_point_rejects_duplicates_nonfinite_and_invalid_utf8(self) -> None:
        duplicate = (
            '{"raw_hint":null,"reason_code":null,"tag":"KNOWN",'
            '"tag":"KNOWN","value":"IN_STOCK"}'
        )
        nonfinite = '{"raw_hint":null,"reason_code":null,"tag":"KNOWN","value":NaN}'
        invalid_utf8 = b'{"raw_hint":null,"reason_code":null,"tag":"KNOWN","value":"\xff"}'
        for document in (duplicate, nonfinite, invalid_utf8):
            with self.subTest(document_type=type(document).__name__):
                with self.assertRaises(ObservedValueError):
                    parse_observed_tagged_value_json(
                        document,
                        version=OBSERVED_TAGGED_VALUE_VERSION,
                        known_value_parser=parse_known_token,
                        allowed_unknown_reasons=UNKNOWN_REASONS,
                    )

    def test_rejections_do_not_retain_json_or_callback_material(self) -> None:
        marker = "fictional" + "-private-marker"

        def failing_parser(_: object) -> str:
            raise RuntimeError(marker)

        operations = (
            lambda: parse_observed_tagged_value_json(
                ('{"raw_hint":null,"reason_code":null,"tag":"KNOWN","value":"' + marker).encode(),
                version=OBSERVED_TAGGED_VALUE_VERSION,
                known_value_parser=parse_known_token,
                allowed_unknown_reasons=UNKNOWN_REASONS,
            ),
            lambda: parse_observed_tagged_value(
                wrapper("KNOWN", value="SAFE"),
                version=OBSERVED_TAGGED_VALUE_VERSION,
                known_value_parser=failing_parser,
                allowed_unknown_reasons=UNKNOWN_REASONS,
            ),
        )
        for operation in operations:
            with self.subTest(operation=operation):
                with self.assertRaises(ObservedValueError) as caught:
                    operation()
                error = caught.exception
                self.assertIsNone(error.__cause__)
                self.assertIsNone(error.__context__)
                self.assertNotIn(marker, repr(error.__dict__))


class FindingPresenceTests(unittest.TestCase):
    def test_direct_four_member_v2_is_exact(self) -> None:
        expected = ("PRESENT", "NOT_PRESENT", "UNKNOWN", "NOT_APPLICABLE")
        self.assertEqual(tuple(member.value for member in FindingPresenceV2), expected)
        for value in expected:
            self.assertEqual(
                parse_finding_presence(value, version=FINDING_PRESENCE_VERSION).value,
                value,
            )

    def test_absent_wrapper_dual_encoding_alias_and_wrong_version_are_rejected(self) -> None:
        wrong_version = "doi-finding-presence/r01-v" + "1"
        canaries: tuple[tuple[object, str], ...] = (
            ("ABSENT", FINDING_PRESENCE_VERSION),
            ("present", FINDING_PRESENCE_VERSION),
            ({"presence": "PRESENT"}, FINDING_PRESENCE_VERSION),
            ({"tag": "KNOWN", "value": "PRESENT"}, FINDING_PRESENCE_VERSION),
            ("PRESENT", wrong_version),
        )
        for value, version in canaries:
            with self.subTest(value_type=type(value).__name__, version=version):
                with self.assertRaises(ObservedValueError) as caught:
                    parse_finding_presence(value, version=version)
                self.assertEqual(str(caught.exception), "observed tagged value rejected")
                self.assertNotIn(repr(value), str(caught.exception))


if __name__ == "__main__":
    unittest.main()
