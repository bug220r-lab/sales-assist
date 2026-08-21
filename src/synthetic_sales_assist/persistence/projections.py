"""Read-only verification of durable rebuildable projections."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from synthetic_sales_assist.persistence.database import SQLiteDatabase


@dataclass(frozen=True, slots=True)
class ProjectionVerification:
    projection_name: str
    checked_count: int
    mismatches: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.mismatches


def verify_sales_credit_projections(
    connection: sqlite3.Connection,
) -> ProjectionVerification:
    """Replay event ordering and compare each latest event with its case row."""

    mismatches: list[str] = []
    cases = connection.execute(
        """
        SELECT order_id, workflow_state, attribution, order_value_status,
               current_evaluation_id, last_event_sequence, last_event_id,
               replacement_parent_order_id
        FROM sc_cases ORDER BY order_id
        """
    ).fetchall()
    for case in cases:
        order_id = str(case[0])
        events = connection.execute(
            """
            SELECT event_id, sequence, predecessor_event_id, workflow_state,
                   attribution, order_value_status, current_evaluation_id,
                   replacement_parent_present
            FROM sc_case_events WHERE order_id = ? ORDER BY sequence
            """,
            (order_id,),
        ).fetchall()
        if not events:
            mismatches.append(f"{order_id}:EVENT_STREAM_EMPTY")
            continue
        previous: str | None = None
        for expected_sequence, event in enumerate(events, start=1):
            if int(event[1]) != expected_sequence:
                mismatches.append(f"{order_id}:EVENT_SEQUENCE")
            if event[2] != previous:
                mismatches.append(f"{order_id}:EVENT_PREDECESSOR")
            previous = str(event[0])
        latest = events[-1]
        expected = (
            str(latest[3]),
            str(latest[4]),
            str(latest[5]),
            latest[6],
            bool(int(latest[7])),
            int(latest[1]),
            str(latest[0]),
        )
        actual = (
            str(case[1]),
            str(case[2]),
            str(case[3]),
            case[4],
            case[7] is not None,
            int(case[5]),
            str(case[6]),
        )
        if actual != expected:
            mismatches.append(f"{order_id}:PROJECTION_DRIFT")
        active_link = connection.execute(
            """
            SELECT parent_order_id FROM sc_active_replacement_links
            WHERE candidate_order_id = ?
            """,
            (order_id,),
        ).fetchone()
        linked_parent = None if active_link is None else str(active_link[0])
        persisted_parent = None if case[7] is None else str(case[7])
        if linked_parent != persisted_parent:
            mismatches.append(f"{order_id}:REPLACEMENT_LINK_DRIFT")
        closed = connection.execute(
            "SELECT 1 FROM sc_closed_audits WHERE order_id = ?",
            (order_id,),
        ).fetchone()
        if closed is not None:
            active_counts = tuple(
                int(
                    connection.execute(
                        f"SELECT COUNT(*) FROM {table} WHERE order_id = ?",
                        (order_id,),
                    ).fetchone()[0]
                )
                for table in (
                    "sc_case_interactions",
                    "sc_case_search_runs",
                    "sc_case_snapshots",
                    "sc_case_evidence",
                    "sc_case_evaluations",
                    "sc_manager_outcomes",
                )
            )
            if any(active_counts):
                mismatches.append(f"{order_id}:CLOSED_ACTIVE_DETAIL")
    return ProjectionVerification(
        projection_name="SALES_CREDIT_CASE",
        checked_count=len(cases),
        mismatches=tuple(mismatches),
    )


class ProjectionVerifier:
    """Database-bound facade for all currently implemented projection checks."""

    def __init__(self, database: SQLiteDatabase) -> None:
        if type(database) is not SQLiteDatabase:
            raise TypeError("DATABASE_INVALID")
        self.database = database

    def verify_sales_credit(self) -> ProjectionVerification:
        with self.database.read() as connection:
            return verify_sales_credit_projections(connection)


__all__ = [
    "ProjectionVerification",
    "ProjectionVerifier",
    "verify_sales_credit_projections",
]
