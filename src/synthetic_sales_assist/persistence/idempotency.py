"""Durable canonical-byte idempotency resolved inside an existing SQLite UoW."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime, timezone

from synthetic_sales_assist.domain.canonical import (
    canonical_json_bytes,
    domain_hash,
    parse_canonical_json_bytes,
)
from synthetic_sales_assist.domain.idempotency import (
    DigestCollisionError,
    IdempotencyConflictError,
    IdempotencyDefinitionError,
    NaturalKey,
)
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp
from synthetic_sales_assist.persistence.faults import FaultInjector, FaultPoint
from synthetic_sales_assist.persistence.records import DurableCommandResult


CommandIdFactory = Callable[[], str]
TrustedClock = Callable[[], datetime]
ResultAllocator = Callable[[str, CanonicalTimestamp], tuple[str, bytes]]


def _timestamp(clock: TrustedClock) -> CanonicalTimestamp:
    value = clock()
    if type(value) is not datetime or value.tzinfo is None:
        raise IdempotencyDefinitionError("RECEIPT_TIMESTAMP_INVALID")
    text = value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )
    return CanonicalTimestamp(text)


def _natural_key_text(value: NaturalKey) -> str:
    encoded = canonical_json_bytes(
        {"components": list(value.components)},
        expected_members={"components"},
    )
    return encoded.decode("utf-8")


class SQLiteIdempotencyRepository:
    """Compare retained material before calling any supplied allocator."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        command_id_factory: CommandIdFactory,
        clock: TrustedClock,
        fault_injector: FaultInjector | None = None,
    ) -> None:
        if not isinstance(connection, sqlite3.Connection):
            raise IdempotencyDefinitionError("IDEMPOTENCY_REQUEST_INVALID")
        if not callable(command_id_factory) or not callable(clock):
            raise IdempotencyDefinitionError("IDEMPOTENCY_REQUEST_INVALID")
        self._connection = connection
        self._command_id_factory = command_id_factory
        self._clock = clock
        self._faults = FaultInjector() if fault_injector is None else fault_injector

    def resolve_or_record(
        self,
        *,
        natural_key: NaturalKey,
        command_domain: str,
        command_bytes: bytes,
        owner_domain: str,
        owner_id: str,
        result_allocator: ResultAllocator,
    ) -> DurableCommandResult:
        if type(natural_key) is not NaturalKey or not callable(result_allocator):
            raise IdempotencyDefinitionError("IDEMPOTENCY_REQUEST_INVALID")
        if owner_domain not in {"SALES_CREDIT", "DOI", "SYSTEM"}:
            raise IdempotencyDefinitionError("IDEMPOTENCY_REQUEST_INVALID")
        if type(owner_id) is not str or not 1 <= len(owner_id) <= 128:
            raise IdempotencyDefinitionError("IDEMPOTENCY_REQUEST_INVALID")
        try:
            parse_canonical_json_bytes(command_bytes)
            token = domain_hash(command_domain, command_bytes)
        except (TypeError, ValueError) as exc:
            raise IdempotencyDefinitionError("COMMAND_BYTES_INVALID") from exc
        key_text = _natural_key_text(natural_key)
        retained = self._connection.execute(
            """
            SELECT
                command.command_id,
                command.command_sha256,
                command.command_bytes,
                receipt.result_domain,
                receipt.result_sha256,
                receipt.result_bytes,
                receipt.recorded_at
            FROM durable_commands AS command
            LEFT JOIN durable_command_receipts AS receipt
                ON receipt.command_id = command.command_id
            WHERE command.natural_namespace = ? AND command.natural_key = ?
            """,
            (natural_key.namespace, key_text),
        ).fetchone()
        if retained is not None:
            if str(retained[1]) != token.sha256:
                raise IdempotencyConflictError("IDEMPOTENCY_KEY_MATERIAL_CONFLICT")
            if bytes(retained[2]) != command_bytes:
                raise DigestCollisionError("IDEMPOTENCY_DIGEST_COLLISION")
            if retained[3] is None or retained[4] is None or retained[5] is None:
                raise IdempotencyDefinitionError("RECEIPT_ALLOCATION_INVALID")
            result_bytes = bytes(retained[5])
            try:
                result = domain_hash(str(retained[3]), result_bytes)
            except ValueError as exc:
                raise IdempotencyDefinitionError("RECEIPT_RESULT_INVALID") from exc
            if result.sha256 != str(retained[4]):
                raise DigestCollisionError("IDEMPOTENCY_DIGEST_COLLISION")
            return DurableCommandResult(
                command_id=str(retained[0]),
                result=result,
                recorded_at=CanonicalTimestamp(str(retained[6])),
                replayed=True,
            )

        command_id = self._command_id_factory()
        recorded_at = _timestamp(self._clock)
        if type(command_id) is not str or not 1 <= len(command_id) <= 128:
            raise IdempotencyDefinitionError("RECEIPT_ID_INVALID")
        self._connection.execute(
            """
            INSERT INTO durable_commands (
                command_id,
                natural_namespace,
                natural_key,
                command_domain,
                command_sha256,
                command_bytes,
                accepted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                command_id,
                natural_key.namespace,
                key_text,
                command_domain,
                token.sha256,
                command_bytes,
                recorded_at.value,
            ),
        )
        self._faults.hit(FaultPoint.AFTER_FIRST_INSERT)
        allocated = result_allocator(command_id, recorded_at)
        if (
            type(allocated) is not tuple
            or len(allocated) != 2
            or type(allocated[0]) is not str
            or type(allocated[1]) is not bytes
        ):
            raise IdempotencyDefinitionError("RECEIPT_ALLOCATION_INVALID")
        result_domain, result_bytes = allocated
        try:
            parse_canonical_json_bytes(result_bytes)
            result = domain_hash(result_domain, result_bytes)
        except (TypeError, ValueError) as exc:
            raise IdempotencyDefinitionError("RECEIPT_RESULT_INVALID") from exc
        self._connection.execute(
            """
            INSERT INTO durable_command_receipts (
                command_id,
                result_domain,
                result_sha256,
                result_bytes,
                recorded_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (command_id, result_domain, result.sha256, result_bytes, recorded_at.value),
        )
        self._connection.execute(
            """
            INSERT INTO durable_receipt_owners (command_id, owner_domain, owner_id)
            VALUES (?, ?, ?)
            """,
            (command_id, owner_domain, owner_id),
        )
        return DurableCommandResult(
            command_id=command_id,
            result=result,
            recorded_at=recorded_at,
            replayed=False,
        )


__all__ = [
    "CommandIdFactory",
    "ResultAllocator",
    "SQLiteIdempotencyRepository",
    "TrustedClock",
]
