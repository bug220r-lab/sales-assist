from __future__ import annotations

import dataclasses
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor

from synthetic_sales_assist.domain.canonical import canonical_json_bytes
from synthetic_sales_assist.domain.idempotency import (
    CanonicalToken,
    DigestCollisionError,
    IdempotencyConflictError,
    IdempotencyDefinitionError,
    InMemoryIdempotencyStore,
    NaturalKey,
    ReceiptAllocation,
)
from synthetic_sales_assist.domain.identities import InteractionId
from synthetic_sales_assist.domain.records import StructuredErrorCode
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp


def _command(sequence: int) -> bytes:
    return canonical_json_bytes(
        {"operation": "SHARED_NO_OP", "sequence": sequence},
        expected_members={"operation", "sequence"},
    )


def _allocation(sequence: int = 1) -> ReceiptAllocation:
    return ReceiptAllocation(
        InteractionId(f"SYN-INTERACTION-RECEIPT-{sequence:04d}"),
        CanonicalTimestamp("2026-08-10T12:34:56.12Z"),
        "shared-idempotency-result/v1",
        canonical_json_bytes({"accepted": True}, expected_members={"accepted"}),
    )


class IdempotencyTests(unittest.TestCase):
    def test_token_internal_factory_cannot_be_used_to_forge_a_binding(self) -> None:
        command = _command(1)
        with self.assertRaises(IdempotencyDefinitionError):
            CanonicalToken._from_validated(
                InMemoryIdempotencyStore.TOKEN_DOMAIN,
                command,
                "0" * 64,
            )

    def setUp(self) -> None:
        self.key = NaturalKey("shared-operation", ("SYN-RUN-IDEMPOTENCY-0001", "0001"))

    def test_token_preimage_is_exact_domain_lf_and_canonical_bytes(self) -> None:
        command = _command(1)
        command_binding = CanonicalToken.from_command(
            "shared-idempotency-command/v1", command
        )
        self.assertEqual(
            command_binding.preimage,
            b"shared-idempotency-command/v1\n" + command,
        )
        self.assertEqual(len(command_binding.sha256), 64)
        self.assertNotIn(command.decode(), repr(command_binding))

    def test_exact_replay_returns_original_without_allocating_again(self) -> None:
        store = InMemoryIdempotencyStore()
        calls = 0

        def allocate() -> ReceiptAllocation:
            nonlocal calls
            calls += 1
            return _allocation(calls)

        original = store.resolve_or_record(self.key, _command(1), allocate)
        replay = store.resolve_or_record(self.key, _command(1), allocate)
        self.assertFalse(original.replayed)
        self.assertTrue(replay.replayed)
        self.assertIs(replay.receipt, original.receipt)
        self.assertEqual(calls, 1)
        self.assertEqual(len(store), 1)

    def test_same_key_different_material_conflicts_before_allocation(self) -> None:
        store = InMemoryIdempotencyStore()
        store.resolve_or_record(self.key, _command(1), _allocation)
        called = False

        def forbidden_allocator() -> ReceiptAllocation:
            nonlocal called
            called = True
            return _allocation(2)

        with self.assertRaises(IdempotencyConflictError):
            store.resolve_or_record(self.key, _command(2), forbidden_allocator)
        self.assertFalse(called)
        self.assertEqual(len(store), 1)

    def test_equal_digest_different_bytes_is_a_collision_not_a_replay(self) -> None:
        fixed_digest = "0" * 64
        store = InMemoryIdempotencyStore(_digest_function=lambda _: fixed_digest)
        store.resolve_or_record(self.key, _command(1), _allocation)
        with self.assertRaises(DigestCollisionError) as caught:
            store.resolve_or_record(self.key, _command(2), lambda: _allocation(2))
        self.assertEqual(caught.exception.code, "IDEMPOTENCY_DIGEST_COLLISION")
        self.assertEqual(len(store), 1)

    def test_lookup_precedes_allocation_under_concurrency(self) -> None:
        store = InMemoryIdempotencyStore()
        allocation_count = 0
        allocation_lock = threading.Lock()

        def allocate() -> ReceiptAllocation:
            nonlocal allocation_count
            with allocation_lock:
                allocation_count += 1
            return _allocation()

        with ThreadPoolExecutor(max_workers=8) as executor:
            outcomes = list(
                executor.map(
                    lambda _: store.resolve_or_record(self.key, _command(1), allocate),
                    range(24),
                )
            )
        self.assertEqual(allocation_count, 1)
        self.assertEqual(sum(outcome.replayed for outcome in outcomes), 23)
        self.assertEqual(len({id(outcome.receipt) for outcome in outcomes}), 1)

    def test_allocator_failure_rolls_back_and_allows_retry(self) -> None:
        store = InMemoryIdempotencyStore()
        marker = "fictional" + "-allocator-private-marker"

        def fail() -> ReceiptAllocation:
            raise RuntimeError(marker)

        with self.assertRaises(IdempotencyDefinitionError) as caught:
            store.resolve_or_record(self.key, _command(1), fail)
        self.assertEqual(caught.exception.code, "RECEIPT_ALLOCATION_FAILED")
        self.assertIsNone(caught.exception.__cause__)
        self.assertIsNone(caught.exception.__context__)
        self.assertNotIn(marker, repr(caught.exception.args))
        self.assertEqual(len(store), 0)
        accepted = store.resolve_or_record(self.key, _command(1), _allocation)
        self.assertFalse(accepted.replayed)

    def test_same_key_allocator_reentry_is_rejected_without_overwrite(self) -> None:
        store = InMemoryIdempotencyStore()
        nested_error: IdempotencyConflictError | None = None

        def allocate() -> ReceiptAllocation:
            nonlocal nested_error
            try:
                store.resolve_or_record(self.key, _command(1), lambda: _allocation(2))
            except IdempotencyConflictError as error:
                nested_error = error
            return _allocation(1)

        accepted = store.resolve_or_record(self.key, _command(1), allocate)
        self.assertFalse(accepted.replayed)
        self.assertIsNotNone(nested_error)
        assert nested_error is not None
        self.assertEqual(nested_error.code, "IDEMPOTENCY_REENTRANT_REQUEST")
        self.assertEqual(accepted.receipt.receipt_id, _allocation(1).receipt_id)
        self.assertEqual(len(store), 1)

    def test_store_and_standalone_token_share_one_domain_grammar(self) -> None:
        invalid_domain = "shared" + "..command/v1"
        with self.assertRaises(IdempotencyDefinitionError):
            InMemoryIdempotencyStore(token_domain=invalid_domain)
        with self.assertRaises(IdempotencyDefinitionError):
            CanonicalToken.from_command(invalid_domain, _command(1))

    def test_digest_callback_failure_is_sanitized(self) -> None:
        marker = "fictional" + "-digest-private-marker"

        def fail(_: bytes) -> str:
            raise RuntimeError(marker)

        store = InMemoryIdempotencyStore(_digest_function=fail)
        with self.assertRaises(IdempotencyDefinitionError) as caught:
            store.resolve_or_record(self.key, _command(1), _allocation)
        self.assertEqual(caught.exception.code, "DIGEST_FUNCTION_FAILED")
        self.assertIsNone(caught.exception.__cause__)
        self.assertIsNone(caught.exception.__context__)
        self.assertNotIn(marker, repr(caught.exception.args))

    def test_shapes_are_strict_immutable_and_non_leaking(self) -> None:
        store = InMemoryIdempotencyStore()
        outcome = store.resolve_or_record(self.key, _command(1), _allocation)
        result_text = outcome.receipt.result.canonical_bytes.decode()
        self.assertNotIn(result_text, repr(outcome.receipt))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            outcome.receipt.recorded_at = CanonicalTimestamp(  # type: ignore[misc]
                "2026-08-10T12:34:57Z"
            )
        with self.assertRaises(IdempotencyDefinitionError):
            NaturalKey("shared-operation", ["0001"])  # type: ignore[arg-type]
        with self.assertRaises(IdempotencyDefinitionError):
            mutable_command = bytearray(_command(1))
            store.resolve_or_record(  # type: ignore[arg-type]
                self.key, mutable_command, _allocation
            )
        with self.assertRaises(IdempotencyDefinitionError):
            store.resolve_or_record(self.key, b'{"z":0,"a":0}', _allocation)

    def test_invalid_receipt_result_has_its_exact_closed_structured_code(self) -> None:
        with self.assertRaises(IdempotencyDefinitionError) as caught:
            ReceiptAllocation(
                InteractionId("SYN-INTERACTION-RECEIPT-0001"),
                CanonicalTimestamp("2026-08-10T12:34:56.12Z"),
                "shared-idempotency-result/v1",
                b'{"z":0,"a":0}',
            )
        self.assertEqual(caught.exception.code, "RECEIPT_RESULT_INVALID")
        self.assertEqual(
            caught.exception.structured.code,
            StructuredErrorCode.RECEIPT_RESULT_INVALID,
        )

        marker = "synthetic" + "privateerrorcode"
        sanitized = IdempotencyDefinitionError(marker)
        self.assertEqual(sanitized.code, "IDEMPOTENCY_ERROR_CODE_INVALID")
        self.assertNotIn(marker, repr(sanitized.args))
        self.assertNotIn(marker, repr(sanitized.structured))


if __name__ == "__main__":
    unittest.main()
