"""Regression for valid retained history exceeding the closed CLI response bound."""

from dataclasses import replace
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from synthetic_sales_assist.application.scenarios import ScenarioApplication
from synthetic_sales_assist.cli.commands import main
from synthetic_sales_assist.domain.identities import EvidenceId
from synthetic_sales_assist.demos import DemoError
from synthetic_sales_assist.durable_demo_backend import DurableDemoAuditBackend
from synthetic_sales_assist.domain.idempotency import IdempotencyConflictError
from synthetic_sales_assist.persistence.sales_credit_repository import SalesCreditRepositoryError
from synthetic_sales_assist.sales_credit.fixtures import milestone2_case_mutation
from tests.test_milestone4_sales_credit_retention import _closure_projection, _plus_days, CLOSED_AT


class HistoryPagingTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="synthetic-sales-assist-history-page-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.application = ScenarioApplication.open(self.root)
        self.backend = DurableDemoAuditBackend(self.application.database)
        self.service = self.backend.sales_credit

    def test_real_1001_event_history_pages_without_loss_and_keeps_replay_and_conflict(self):
        base = milestone2_case_mutation()

        def append(number):
            mutation = replace(base, command_id=EvidenceId(f"SYN-EVIDENCE-M8-PAGE-{number:04d}"))
            result = self.service.persist_case_mutation(mutation, request_key=f"page-{number}")
            return mutation, result

        for number in range(1, 1_001):
            append(number)
        at_limit = self.backend.case_history(base.order_id.value)
        self.assertEqual(len(at_limit.events), 1_000)
        self.assertFalse(dict(at_limit.summary)["has_more"])
        final_mutation, original = append(1_001)
        first = self.backend.case_history(base.order_id.value)
        summary = dict(first.summary)
        self.assertEqual(summary["event_count"], 1_001)
        self.assertEqual(summary["returned_event_count"], 1_000)
        self.assertTrue(summary["has_more"])
        self.assertEqual(summary["next_after_sequence"], 1_000)
        self.assertEqual(summary["through_sequence"], 1_001)
        with self.application.database.read() as connection:
            before = connection.execute("SELECT COUNT(*) FROM durable_commands").fetchone()[0]
        replay = self.service.persist_case_mutation(final_mutation, request_key="page-1001")
        self.assertTrue(replay.replayed)
        self.assertEqual(original.command_id, replay.command_id)
        with self.assertRaises(IdempotencyConflictError):
            self.service.persist_case_mutation(base, request_key="page-1001")
        # Append between pages: the captured prefix must remain unchanged.
        append(1_002)
        second = self.backend.case_history(
            base.order_id.value, after_sequence=summary["next_after_sequence"],
            through_sequence=summary["through_sequence"], limit=100,
            through_event_id=summary["through_event_id"],
        )
        self.assertEqual(dict(second.summary)["event_count"], 1_001)
        self.assertFalse(dict(second.summary)["has_more"])
        rows = [dict(item) for item in (*first.events, *second.events)]
        self.assertEqual([item["sequence"] for item in rows], list(range(1, 1_002)))
        self.assertEqual(len({item["event_id"] for item in rows}), 1_001)
        latest = self.backend.case_history(base.order_id.value, after_sequence=1_001)
        self.assertEqual(dict(latest.events[0])["sequence"], 1_002)
        self.assertEqual(dict(latest.summary)["event_count"], 1_002)
        output = StringIO()
        code = main([
            "--json", "--data-dir", str(self.root), "case", "history", base.order_id.value,
            "--after-sequence", "1000", "--through-sequence", "1001", "--limit", "1",
            "--through-event-id", summary["through_event_id"],
        ], stdout=output, stderr=output)
        self.assertEqual(code, 0, output.getvalue())
        rendered = json.loads(output.getvalue())["result"]
        self.assertEqual(len(rendered["events"]), 1)
        self.assertEqual(rendered["events"][0]["sequence"], 1_001)
        self.assertIsNone(rendered["summary"]["next_after_sequence"])
        retained = self.service.case_history(base.order_id)
        self.assertEqual(len(retained), 1_002)
        self.assertTrue(all(b.predecessor_event_id == a.event_id
                            for a, b in zip(retained, retained[1:])))
        self.assertTrue(self.service.verify_projections().valid)
        with self.application.database.read() as connection:
            count = connection.execute("SELECT COUNT(*) FROM durable_commands").fetchone()[0]
            self.assertEqual(count, before + 1)

    def test_invalid_page_values_fail_before_database_read(self):
        order = milestone2_case_mutation().order_id
        invalid = [
            {"after_sequence": True}, {"after_sequence": -1}, {"after_sequence": 2**63},
            {"after_sequence": "1"}, {"through_sequence": True}, {"through_sequence": -1},
            {"through_sequence": 2**63}, {"after_sequence": 2, "through_sequence": 1},
            {"through_sequence": 0}, {"through_sequence": 1},
            {"through_event_id": EvidenceId("SYN-EVIDENCE-M8-ENDPOINT")},
            {"through_sequence": 1, "through_event_id": "SYN-EVIDENCE-M8-ENDPOINT"},
            {"limit": True}, {"limit": 0}, {"limit": 1_001}, {"limit": "1"},
        ]
        with patch.object(self.application.database, "read",
                          side_effect=AssertionError("SQL opened")):
            for parameters in invalid:
                with self.subTest(parameters=parameters):
                    with self.assertRaisesRegex(SalesCreditRepositoryError,
                                                "CASE_HISTORY_PAGE_INVALID"):
                        self.service.case_history_page(order, **parameters)

    def test_cursor_beyond_retained_prefix_is_rejected(self):
        mutation = milestone2_case_mutation()
        self.service.persist_case_mutation(mutation)
        endpoint = self.service.case_history_page(mutation.order_id).through_event_id
        for parameters in ({"through_sequence": 2, "through_event_id": endpoint},
                           {"after_sequence": 2}):
            with self.subTest(parameters=parameters):
                with self.assertRaisesRegex(SalesCreditRepositoryError,
                                            "CASE_HISTORY_CURSOR_INVALID"):
                    self.service.case_history_page(mutation.order_id, **parameters)
        empty = self.service.case_history_page(mutation.order_id, after_sequence=1)
        self.assertEqual(empty.events, ())
        self.assertEqual(empty.event_count, 1)
        self.assertFalse(empty.has_more)

    def test_closure_and_purge_reuse_invalidate_old_endpoint_identity(self):
        mutation, closure = _closure_projection()
        self.service.persist_case_mutation(mutation, request_key="before-close")
        original = dict(self.backend.case_history(mutation.order_id.value).summary)
        self.service.close_and_minimize_case(
            projection=closure, audit_id=EvidenceId("SYN-EVIDENCE-M8-PAGE-CLOSURE"),
            request_key="close-for-page-test",
        )
        closed = dict(self.backend.case_history(mutation.order_id.value).summary)
        self.assertEqual(original["through_sequence"], closed["through_sequence"])
        self.assertNotEqual(original["through_event_id"], closed["through_event_id"])

        def assert_stale(summary):
            with self.assertRaisesRegex(DemoError, "CASE_HISTORY_CURSOR_INVALID"):
                self.backend.case_history(
                    mutation.order_id.value, through_sequence=summary["through_sequence"],
                    through_event_id=summary["through_event_id"],
                )

        assert_stale(original)
        self.service.purge_closed_case(order_id=mutation.order_id, now=_plus_days(CLOSED_AT, 91))
        self.service.persist_case_mutation(
            replace(mutation, command_id=EvidenceId("SYN-EVIDENCE-M8-PAGE-RECREATED")),
            request_key="after-purge",
        )
        assert_stale(original)
        assert_stale(closed)
        self.assertEqual(len(self.service.case_history(mutation.order_id)), 1)
