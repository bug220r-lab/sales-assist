from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError

from synthetic_sales_assist.domain.identities import (
    ID_CLASS_BY_NAMESPACE,
    MAX_TYPED_ID_LENGTH,
    TYPED_ID_CLASSES,
    ConversationId,
    CustomerId,
    DomainIdentityError,
    EvaluationId,
    EvidenceId,
    InteractionId,
    OrderId,
    RepId,
    RunId,
    SkuId,
    SnapshotId,
)


class TypedIdentityTests(unittest.TestCase):
    def test_closed_ten_type_inventory_and_namespaces(self) -> None:
        expected = {
            "CUSTOMER": CustomerId,
            "ORDER": OrderId,
            "SKU": SkuId,
            "INTERACTION": InteractionId,
            "CONVERSATION": ConversationId,
            "SNAPSHOT": SnapshotId,
            "EVALUATION": EvaluationId,
            "RUN": RunId,
            "REP": RepId,
            "EVIDENCE": EvidenceId,
        }
        self.assertEqual(len(TYPED_ID_CLASSES), 10)
        self.assertEqual(ID_CLASS_BY_NAMESPACE, expected)
        with self.assertRaises(TypeError):
            ID_CLASS_BY_NAMESPACE["ORDER"] = CustomerId  # type: ignore[index]

        for namespace, identity_type in expected.items():
            with self.subTest(namespace=namespace):
                raw = f"SYN-{namespace}-000001"
                identity = identity_type(raw)
                self.assertEqual(identity.value, raw)
                self.assertEqual(identity.to_json_value(), raw)
                self.assertEqual(identity.to_sqlite_value(), raw)
                self.assertEqual(str(identity), raw)

    def test_types_are_immutable_hashable_and_not_strings(self) -> None:
        customer = CustomerId("SYN-CUSTOMER-000001")
        order = OrderId("SYN-ORDER-000001")
        self.assertNotEqual(customer, customer.value)
        self.assertNotEqual(customer, order)
        self.assertEqual({customer, CustomerId(customer.value)}, {customer})
        with self.assertRaises(FrozenInstanceError):
            setattr(customer, "value", "SYN-CUSTOMER-000002")

    def test_constructor_is_strict_and_never_coerces(self) -> None:
        class StringSubclass(str):
            pass

        invalid: tuple[object, ...] = (
            1,
            True,
            b"SYN-ORDER-000001",
            StringSubclass("SYN-ORDER-000001"),
            CustomerId("SYN-CUSTOMER-000001"),
        )
        for value in invalid:
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaises(DomainIdentityError):
                    OrderId(value)  # type: ignore[arg-type]

    def test_namespace_and_closed_grammar_are_enforced(self) -> None:
        invalid = (
            "SYN-CUSTOMER-000001",
            "syn-order-000001",
            "SYN-ORDER-",
            "SYN-ORDER-000001_2",
            " SYN-ORDER-000001",
            "SYN-ORDER-000001 ",
            "SYN-ORDER-000001--2",
        )
        for value in invalid:
            with self.subTest(length=len(value)):
                with self.assertRaises(DomainIdentityError):
                    OrderId(value)

    def test_length_boundary_is_exact(self) -> None:
        prefix = "SYN-CUSTOMER-"
        boundary = prefix + "A" * (MAX_TYPED_ID_LENGTH - len(prefix))
        self.assertEqual(len(CustomerId(boundary).value), MAX_TYPED_ID_LENGTH)
        with self.assertRaises(DomainIdentityError):
            CustomerId(boundary + "A")

    def test_exception_and_repr_do_not_echo_material(self) -> None:
        rejected = "SYN-ORDER-" + "fixture" + "@" + "enterprise" + "." + "example"
        with self.assertRaises(DomainIdentityError) as raised:
            OrderId(rejected)
        self.assertNotIn(rejected, str(raised.exception))

        accepted = "SYN-ORDER-000001"
        self.assertNotIn(accepted, repr(OrderId(accepted)))


if __name__ == "__main__":
    unittest.main()
