"""Typed read-only health checks needed by the local application boundary."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from synthetic_sales_assist.persistence.telemetry import SAFETY_COUNTER_NAMES


@dataclass(frozen=True, slots=True)
class SafetyCounterVerification:
    counters: tuple[tuple[str, int], ...]
    system_valid: bool
    telemetry_valid: bool

    @property
    def valid(self) -> bool:
        return self.system_valid and self.telemetry_valid


def verify_application_safety_counters(
    connection: sqlite3.Connection,
) -> SafetyCounterVerification:
    """Verify the exact persisted nine-counter baseline and every telemetry snapshot."""

    if type(connection) is not sqlite3.Connection:
        raise TypeError("SAFETY_COUNTER_CONNECTION_INVALID")
    expected = tuple((name, 0) for name in SAFETY_COUNTER_NAMES)
    rows = tuple(
        (str(row[0]), int(row[1]))
        for row in connection.execute(
            "SELECT counter_name, counter_value FROM system_safety_counters "
            "ORDER BY counter_name"
        ).fetchall()
    )
    operation_count = int(
        connection.execute("SELECT COUNT(*) FROM processing_telemetry").fetchone()[0]
    )
    snapshot_count = int(
        connection.execute(
            "SELECT COUNT(DISTINCT operation_id) FROM telemetry_safety_counters"
        ).fetchone()[0]
    )
    invalid_snapshot = connection.execute(
        """
        SELECT operation_id
        FROM telemetry_safety_counters
        GROUP BY operation_id
        HAVING COUNT(*) != 9
            OR MIN(counter_value) != 0
            OR MAX(counter_value) != 0
            OR COUNT(DISTINCT counter_name) != 9
        LIMIT 1
        """
    ).fetchone()
    telemetry_names = tuple(
        str(row[0])
        for row in connection.execute(
            "SELECT DISTINCT counter_name FROM telemetry_safety_counters "
            "ORDER BY counter_name"
        ).fetchall()
    )
    names_valid = not telemetry_names or telemetry_names == SAFETY_COUNTER_NAMES
    return SafetyCounterVerification(
        counters=rows,
        system_valid=rows == expected,
        telemetry_valid=(
            operation_count == snapshot_count
            and invalid_snapshot is None
            and names_valid
        ),
    )


__all__ = ["SafetyCounterVerification", "verify_application_safety_counters"]
