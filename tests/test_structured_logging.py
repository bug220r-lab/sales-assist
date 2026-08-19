from __future__ import annotations

import json
import logging
import unittest
from datetime import datetime, timezone
from io import StringIO

from synthetic_sales_assist.structured_logging import (
    LOG_SCHEMA_VERSION,
    SAFETY_COUNTER_NAMES,
    SafetyCounterInvariantError,
    StructuredLogger,
    UnsafeLogDataError,
    assert_safety_counters_zero,
    build_log_record,
    zero_safety_counters,
)


FIXED_TIME = datetime(2026, 8, 19, 12, 34, 56, 789123, tzinfo=timezone.utc)


class StructuredLoggingTests(unittest.TestCase):
    def test_emits_one_closed_deterministic_json_record(self) -> None:
        stream = StringIO()
        logger = StructuredLogger(
            "m0.foundation",
            stream=stream,
            clock=lambda: FIXED_TIME,
        )
        self.addCleanup(logger.close)

        logger.emit(
            "FOUNDATION_CHECK",
            component="safety",
            operation="candidate_gate",
            status="SUCCEEDED",
            code="M0_OK",
            count=0,
            duration_ms=1.25,
            migration_version=1,
            artifact_schema_version="foundation/v1",
            safety_counters=zero_safety_counters(),
        )

        lines = stream.getvalue().splitlines()
        self.assertEqual(len(lines), 1)
        payload = json.loads(lines[0])
        self.assertEqual(payload["log_schema_version"], LOG_SCHEMA_VERSION)
        self.assertEqual(payload["timestamp"], "2026-08-19T12:34:56.789Z")
        self.assertEqual(payload["event"], "FOUNDATION_CHECK")
        self.assertEqual(payload["level"], "INFO")
        self.assertEqual(payload["safety_counters"], zero_safety_counters())
        self.assertNotIn("message", payload)
        self.assertNotIn("exception", payload)

    def test_logger_has_one_local_stream_handler_and_no_propagation(self) -> None:
        logger = StructuredLogger("m0.handler", stream=StringIO())
        self.addCleanup(logger.close)

        self.assertEqual(len(logger.handlers), 1)
        self.assertIs(type(logger.handlers[0]), logging.StreamHandler)
        self.assertFalse(logger.propagates)

    def test_rejects_contact_note_session_and_raw_exception_fields_without_leak(self) -> None:
        canaries: dict[str, object] = {
            "email": "synthetic.person@example.test",
            "phone": "+1-202-555-0107",
            "note": "fictional copied note body",
            "session": "fictional-session-material",
            "exception": RuntimeError("fictional raw exception body"),
        }

        for field, canary in canaries.items():
            with self.subTest(field=field):
                stream = StringIO()
                logger = StructuredLogger("m0.rejection", stream=stream)
                self.addCleanup(logger.close)
                with self.assertRaises(UnsafeLogDataError) as caught:
                    logger.emit("REJECTED_INPUT", **{field: canary})
                self.assertEqual(stream.getvalue(), "")
                self.assertNotIn(str(canary), str(caught.exception))
                self.assertNotIn(field, str(caught.exception))

    def test_rejects_sensitive_material_even_in_an_allowlisted_token_field(self) -> None:
        secret_canary = "".join(("g", "hp", "_", "A" * 36))
        values = (
            "synthetic.person@example.test",
            "+1-202-555-0107",
            "202-555-0107",
            "fictional note with spaces",
            "http://localhost/internal",
            "SYN-ORDER-000001",
            secret_canary,
        )
        for value in values:
            with self.subTest(value_kind=len(value)):
                with self.assertRaises(UnsafeLogDataError) as caught:
                    build_log_record(
                        "VALID_EVENT",
                        fields={"operation": value},
                        timestamp=FIXED_TIME,
                    )
                self.assertNotIn(value, str(caught.exception))
                self.assertNotIn("operation", str(caught.exception))

    def test_all_token_fields_reject_phone_and_executable_identity_shapes(self) -> None:
        fields = (
            "artifact_schema_version",
            "code",
            "component",
            "operation",
            "rule_pack_version",
        )
        canaries = ("202-555-0107", "SYN-ORDER-000001")
        for field in fields:
            for canary in canaries:
                with self.subTest(field=field, canary_kind=canary.startswith("SYN-")):
                    with self.assertRaises(UnsafeLogDataError) as caught:
                        build_log_record(
                            "VALID_EVENT",
                            fields={field: canary},
                            timestamp=FIXED_TIME,
                        )
                    self.assertNotIn(field, str(caught.exception))
                    self.assertNotIn(canary, str(caught.exception))

    def test_rejects_nonfinite_or_negative_durations(self) -> None:
        for value in (-1, float("nan"), float("inf"), True):
            with self.subTest(value=value):
                with self.assertRaises(UnsafeLogDataError):
                    build_log_record(
                        "TIMING",
                        fields={"duration_ms": value},
                        timestamp=FIXED_TIME,
                    )

    def test_union_of_binding_safety_counters_is_exact_and_zero(self) -> None:
        counters = zero_safety_counters()
        self.assertEqual(len(SAFETY_COUNTER_NAMES), 9)
        self.assertEqual(tuple(counters), SAFETY_COUNTER_NAMES)
        self.assertTrue(all(value == 0 for value in counters.values()))
        assert_safety_counters_zero(counters)

    def test_counter_shape_and_nonzero_values_fail_closed(self) -> None:
        invalid_snapshots: list[dict[str, object]] = []

        missing = zero_safety_counters()
        missing.pop(SAFETY_COUNTER_NAMES[0])
        invalid_snapshots.append(missing)

        extra: dict[str, object] = zero_safety_counters()
        extra["UNLISTED_COUNTER"] = 0
        invalid_snapshots.append(extra)

        nonzero: dict[str, object] = zero_safety_counters()
        nonzero[SAFETY_COUNTER_NAMES[0]] = 1
        invalid_snapshots.append(nonzero)

        noninteger: dict[str, object] = zero_safety_counters()
        noninteger[SAFETY_COUNTER_NAMES[0]] = True
        invalid_snapshots.append(noninteger)

        for counters in invalid_snapshots:
            with self.subTest(keys=len(counters)):
                with self.assertRaises(SafetyCounterInvariantError) as caught:
                    assert_safety_counters_zero(counters)
                self.assertEqual(
                    str(caught.exception),
                    "safety counter invariant violated",
                )

    def test_naive_timestamp_and_unknown_level_fail_closed(self) -> None:
        with self.assertRaises(UnsafeLogDataError):
            build_log_record(
                "FOUNDATION",
                timestamp=datetime(2026, 8, 19, 12, 0, 0),
            )
        with self.assertRaises(UnsafeLogDataError):
            build_log_record(
                "FOUNDATION",
                level="NOTICE",
                timestamp=FIXED_TIME,
            )


if __name__ == "__main__":
    unittest.main()
