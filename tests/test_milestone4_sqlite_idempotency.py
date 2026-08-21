from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from synthetic_sales_assist.domain.canonical import canonical_json_bytes, domain_hash
from synthetic_sales_assist.domain.idempotency import (
    DigestCollisionError,
    IdempotencyConflictError,
    NaturalKey,
)
from synthetic_sales_assist.persistence.database import SQLiteDatabase
from synthetic_sales_assist.persistence.faults import (
    FaultInjector,
    FaultPoint,
    InjectedPersistenceFault,
)
from synthetic_sales_assist.persistence.idempotency import SQLiteIdempotencyRepository


FIXED_TIME = datetime(2026, 8, 21, 17, 30, tzinfo=timezone.utc)


def _material(value: str) -> bytes:
    return canonical_json_bytes({"value": value}, expected_members={"value"})


class Milestone4SQLiteIdempotencyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="ssa-m4-idempotency-")
        self.addCleanup(self.temporary.cleanup)
        self.database = SQLiteDatabase(
            Path(self.temporary.name) / "state.sqlite3",
            clock=lambda: FIXED_TIME,
        )
        self.database.initialize()

    def repository(
        self,
        connection: sqlite3.Connection,
        *,
        fault_injector: FaultInjector | None = None,
    ) -> SQLiteIdempotencyRepository:
        return SQLiteIdempotencyRepository(
            connection,
            command_id_factory=lambda: "SYN-EVIDENCE-M4-IDEMPOTENCY-0001",
            clock=lambda: FIXED_TIME,
            fault_injector=fault_injector,
        )

    def test_exact_replay_returns_retained_result_without_new_allocation(self) -> None:
        calls: list[str] = []
        natural_key = NaturalKey("test.command", ("one",))
        with self.database.write() as connection:
            first = self.repository(connection).resolve_or_record(
                natural_key=natural_key,
                command_domain="test-command/v1",
                command_bytes=_material("command"),
                owner_domain="SYSTEM",
                owner_id="SYN-RUN-M4-IDEMPOTENCY-0001",
                result_allocator=lambda command_id, _recorded_at: (
                    calls.append(command_id) or "test-result/v1",
                    _material("result"),
                ),
            )
        with self.database.write() as connection:
            replay = self.repository(connection).resolve_or_record(
                natural_key=natural_key,
                command_domain="test-command/v1",
                command_bytes=_material("command"),
                owner_domain="SYSTEM",
                owner_id="SYN-RUN-M4-IDEMPOTENCY-0001",
                result_allocator=lambda _command_id, _recorded_at: self.fail(
                    "allocator was called during lookup-first replay"
                ),
            )

        self.assertFalse(first.replayed)
        self.assertTrue(replay.replayed)
        self.assertEqual(first.command_id, replay.command_id)
        self.assertEqual(first.result, replay.result)
        self.assertEqual(calls, ["SYN-EVIDENCE-M4-IDEMPOTENCY-0001"])

    def test_same_key_changed_material_conflicts_before_allocation(self) -> None:
        natural_key = NaturalKey("test.command", ("conflict",))
        with self.database.write() as connection:
            self.repository(connection).resolve_or_record(
                natural_key=natural_key,
                command_domain="test-command/v1",
                command_bytes=_material("first"),
                owner_domain="SYSTEM",
                owner_id="SYN-RUN-M4-IDEMPOTENCY-0002",
                result_allocator=lambda _command_id, _recorded_at: (
                    "test-result/v1",
                    _material("result"),
                ),
            )
        with self.assertRaises(IdempotencyConflictError):
            with self.database.write() as connection:
                self.repository(connection).resolve_or_record(
                    natural_key=natural_key,
                    command_domain="test-command/v1",
                    command_bytes=_material("changed"),
                    owner_domain="SYSTEM",
                    owner_id="SYN-RUN-M4-IDEMPOTENCY-0002",
                    result_allocator=lambda _command_id, _recorded_at: self.fail(
                        "allocator was called during conflict detection"
                    ),
                )

    def test_same_digest_different_canonical_bytes_fails_closed(self) -> None:
        candidate = _material("candidate")
        retained = _material("retained")
        token = domain_hash("test-command/v1", candidate)
        key_text = canonical_json_bytes(
            {"components": ["collision"]},
            expected_members={"components"},
        ).decode("utf-8")
        result = domain_hash("test-result/v1", _material("result"))
        with self.database.write() as connection:
            connection.execute(
                """
                INSERT INTO durable_commands (
                    command_id, natural_namespace, natural_key, command_domain,
                    command_sha256, command_bytes, accepted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "SYN-EVIDENCE-M4-COLLISION-0001",
                    "test.command",
                    key_text,
                    "test-command/v1",
                    token.sha256,
                    retained,
                    "2026-08-21T17:30:00Z",
                ),
            )
            connection.execute(
                """
                INSERT INTO durable_command_receipts (
                    command_id, result_domain, result_sha256, result_bytes, recorded_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    "SYN-EVIDENCE-M4-COLLISION-0001",
                    "test-result/v1",
                    result.sha256,
                    _material("result"),
                    "2026-08-21T17:30:00Z",
                ),
            )
        with self.assertRaises(DigestCollisionError):
            with self.database.write() as connection:
                self.repository(connection).resolve_or_record(
                    natural_key=NaturalKey("test.command", ("collision",)),
                    command_domain="test-command/v1",
                    command_bytes=candidate,
                    owner_domain="SYSTEM",
                    owner_id="SYN-RUN-M4-COLLISION-0001",
                    result_allocator=lambda _command_id, _recorded_at: self.fail(
                        "allocator was called during collision detection"
                    ),
                )

    def test_fault_after_first_insert_rolls_back_command_and_receipt(self) -> None:
        with self.assertRaises(InjectedPersistenceFault):
            with self.database.write(
                fault_injector=FaultInjector(
                    frozenset({FaultPoint.AFTER_FIRST_INSERT})
                )
            ) as connection:
                self.repository(
                    connection,
                    fault_injector=FaultInjector(
                        frozenset({FaultPoint.AFTER_FIRST_INSERT})
                    ),
                ).resolve_or_record(
                    natural_key=NaturalKey("test.command", ("fault",)),
                    command_domain="test-command/v1",
                    command_bytes=_material("fault"),
                    owner_domain="SYSTEM",
                    owner_id="SYN-RUN-M4-FAULT-0001",
                    result_allocator=lambda _command_id, _recorded_at: (
                        "test-result/v1",
                        _material("result"),
                    ),
                )
        with self.database.read() as connection:
            counts = (
                connection.execute("SELECT COUNT(*) FROM durable_commands").fetchone()[0],
                connection.execute(
                    "SELECT COUNT(*) FROM durable_command_receipts"
                ).fetchone()[0],
            )
        self.assertEqual(counts, (0, 0))


if __name__ == "__main__":
    unittest.main()
