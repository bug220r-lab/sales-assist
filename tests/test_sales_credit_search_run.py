from __future__ import annotations

import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, fields, replace
from datetime import date
from threading import Barrier

from synthetic_sales_assist.domain.identities import (
    EvidenceId,
    InteractionId,
    OrderId,
    RunId,
)
from synthetic_sales_assist.domain.records import VersionBinding
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp
from synthetic_sales_assist.sales_credit.discovery import (
    DiscoveryOutcome,
    DiscoveryResult,
    DiscoveryValidationError,
    IdentifierSearchResult,
    InMemoryNoOrderStateLedger,
    InMemorySearchRunAuthority,
    NoOrderLedgerError,
    NoOrderTransitionResult,
    OrderSearchRun,
    SearchCompleteness,
    SearchIdentifier,
    SearchRunAuthorityError,
    plan_discovery,
)
from synthetic_sales_assist.sales_credit.models import (
    InteractionRecord,
    SalesCreditReason,
    SearchTriggerType,
    TimestampPrecision,
    WorkflowState,
)
from synthetic_sales_assist.sales_credit.windows import RecheckDecision


def _timestamp(value: str) -> CanonicalTimestamp:
    return CanonicalTimestamp(value)


def _no_order_ledger() -> InMemoryNoOrderStateLedger:
    return InMemoryNoOrderStateLedger(
        search_run_authority=InMemorySearchRunAuthority()
    )


class OrderSearchRunTests(unittest.TestCase):
    def setUp(self) -> None:
        self.interactions = (
            self.interaction(1, email="search.run@example.test"),
            self.interaction(2, phone="212-555-0100"),
        )
        self.plan = plan_discovery(
            email_values=("search.run@example.test",),
            phone_values=("212-555-0100",),
        )
        self.email = self.plan.identifiers[0]
        self.phone = self.plan.identifiers[1]

    def interaction(
        self,
        index: int,
        *,
        email: str | None = None,
        phone: str | None = None,
        recorded_at: str = "2026-08-01T14:00:00Z",
        review_window_start: date = date(2026, 8, 1),
        last_check_at: str | None = None,
        precision: TimestampPrecision = TimestampPrecision.EXACT,
    ) -> InteractionRecord:
        return InteractionRecord(
            interaction_id=InteractionId(f"SYN-INTERACTION-{index:06d}"),
            source_ref=EvidenceId(f"SYN-EVIDENCE-INTERACTION-{index:06d}"),
            recorded_at=_timestamp(recorded_at),
            timestamp_precision=precision,
            review_window_start=review_window_start,
            review_window_end=date.fromordinal(review_window_start.toordinal() + 14),
            workflow_state=WorkflowState.AWAITING_SOURCE_REVIEW,
            provenance=VersionBinding(
                component="sales_credit_interaction_source",
                version="sales-credit-interaction-source/v1",
            ),
            email=email,
            phone=phone,
            last_check_at=(
                _timestamp(last_check_at) if last_check_at is not None else None
            ),
        )

    def native_result(
        self,
        identifier: SearchIdentifier,
        *order_values: str,
        completeness: SearchCompleteness = SearchCompleteness.COMPLETE,
    ) -> IdentifierSearchResult:
        return IdentifierSearchResult(
            identifier=identifier,
            completeness=completeness,
            order_ids=tuple(OrderId(value) for value in order_values),
        )

    def make_run(
        self,
        *,
        trigger: SearchTriggerType = SearchTriggerType.NORMAL,
        interactions: tuple[InteractionRecord, ...] | None = None,
        native_results: tuple[IdentifierSearchResult, ...] | None = None,
        started_at: str = "2026-08-10T14:00:00.123456789Z",
        completed_at: str = "2026-08-10T14:00:01.000000001Z",
        force_explanation: str | None = None,
        warnings: tuple[str, ...] = (),
        run_id: str = "SYN-RUN-000001",
    ) -> OrderSearchRun:
        selected_interactions = self.interactions if interactions is None else interactions
        if trigger in {
            SearchTriggerType.AUTOMATIC_RECHECK,
            SearchTriggerType.FORCE_RECHECK,
        }:
            selected_interactions = tuple(
                replace(
                    item,
                    workflow_state=WorkflowState.CHECKED_NO_ORDER_WINDOW_ACTIVE,
                    last_check_at=(
                        item.last_check_at
                        or _timestamp("2026-08-09T14:00:00Z")
                    ),
                    next_eligible_check_at=(
                        item.next_eligible_check_at
                        or _timestamp("2026-08-10T04:00:00Z")
                    ),
                )
                for item in selected_interactions
            )
        expected_plan = plan_discovery(
            email_values=tuple(
                item.email for item in selected_interactions if item.email is not None
            ),
            phone_values=tuple(
                item.phone for item in selected_interactions if item.phone is not None
            ),
        )
        selected_results = (
            tuple(self.native_result(identifier) for identifier in expected_plan.identifiers)
            if native_results is None
            else native_results
        )
        return OrderSearchRun(
            run_id=RunId(run_id),
            trigger=trigger,
            interactions=selected_interactions,
            native_result_sets=selected_results,
            adapter=VersionBinding(
                component="sales_credit_search_adapter",
                version=OrderSearchRun.ADAPTER_VERSION,
            ),
            started_at=_timestamp(started_at),
            completed_at=_timestamp(completed_at),
            warnings=warnings,
            force_explanation=force_explanation,
        )

    def assert_rejected_without_leak(
        self,
        callback: object,
        *canaries: str,
    ) -> DiscoveryValidationError:
        with self.assertRaises(DiscoveryValidationError) as raised:
            callback()  # type: ignore[operator]
        rendered = f"{raised.exception!s} {raised.exception!r}"
        for canary in canaries:
            self.assertNotIn(canary, rendered)
        return raised.exception

    def test_all_four_closed_triggers_are_recorded_exactly(self) -> None:
        for trigger in SearchTriggerType:
            with self.subTest(trigger=trigger.value):
                explanation = (
                    "SYNTHETIC_FORCE_REVIEW"
                    if trigger is SearchTriggerType.FORCE_RECHECK
                    else None
                )
                run = self.make_run(
                    trigger=trigger,
                    force_explanation=explanation,
                )
                self.assertIs(run.trigger, trigger)
                self.assertEqual(run.force_explanation, explanation)
                if trigger in {
                    SearchTriggerType.AUTOMATIC_RECHECK,
                    SearchTriggerType.FORCE_RECHECK,
                }:
                    self.assertEqual(len(run.recheck_results), len(run.interactions))
                else:
                    self.assertEqual(run.recheck_results, ())
        self.assertEqual(
            tuple(item.value for item in SearchTriggerType),
            (
                "NORMAL",
                "AUTOMATIC_RECHECK",
                "FORCE_RECHECK",
                "REPLACEMENT_CHECK",
            ),
        )

    def test_interaction_scope_is_nonempty_sorted_unique_and_preserved(self) -> None:
        run = self.make_run()
        self.assertEqual(run.interactions, self.interactions)
        self.assertEqual(
            run.interaction_ids,
            tuple(item.interaction_id for item in self.interactions),
        )

        invalid_scopes: tuple[object, ...] = (
            (),
            tuple(reversed(self.interactions)),
            (self.interactions[0], self.interactions[0]),
            [self.interactions[0]],
            (InteractionId("SYN-INTERACTION-000003"),),
        )
        for scope in invalid_scopes:
            with self.subTest(shape=type(scope).__name__):
                with self.assertRaisesRegex(
                    DiscoveryValidationError,
                    "search_run_interactions",
                ):
                    replace(run, interactions=scope)  # type: ignore[arg-type]

    def test_attempted_identifier_scope_is_sorted_unique_and_exact(self) -> None:
        run = self.make_run()
        self.assertEqual(run.attempted_identifiers, self.plan.identifiers)
        self.assertEqual(
            tuple(result.identifier for result in run.native_result_sets),
            self.plan.identifiers,
        )

        field_by_name = {item.name: item for item in fields(OrderSearchRun)}
        for name in (
            "interaction_ids",
            "attempted_identifiers",
            "recheck_results",
            "result",
        ):
            with self.subTest(field=name):
                self.assertFalse(field_by_name[name].init)
                with self.assertRaisesRegex(ValueError, "init=False"):
                    replace(run, **{name: getattr(run, name)})

    def test_contact_set_rejects_omitted_and_extra_identifier_results(self) -> None:
        run = self.make_run()
        with self.assertRaisesRegex(
            DiscoveryValidationError,
            "search_run_attempt_parity",
        ):
            replace(run, interactions=(self.interactions[0],))

        extra_contact = self.interaction(
            3,
            email="extra.search@example.test",
        )
        with self.assertRaisesRegex(
            DiscoveryValidationError,
            "search_run_attempt_parity",
        ):
            replace(run, interactions=(*self.interactions, extra_contact))

    def test_native_results_must_have_one_to_one_attempt_parity(self) -> None:
        run = self.make_run()
        cases = (
            (self.native_result(self.email),),
            (
                self.native_result(self.email),
                self.native_result(self.email),
            ),
        )
        for native_results in cases:
            with self.subTest(result_count=len(native_results)):
                with self.assertRaisesRegex(
                    DiscoveryValidationError,
                    "search_run_attempt_parity",
                ):
                    replace(run, native_result_sets=native_results)

        with self.assertRaisesRegex(
            DiscoveryValidationError,
            "search_run_results",
        ):
            replace(run, native_result_sets=list(run.native_result_sets))  # type: ignore[arg-type]

    def test_native_result_arrival_order_does_not_change_attempt_parity(self) -> None:
        native_results = (
            self.native_result(self.phone, "SYN-ORDER-000002"),
            self.native_result(self.email, "SYN-ORDER-000001"),
        )
        run = self.make_run(native_results=native_results)
        self.assertEqual(run.native_result_sets, native_results)
        self.assertEqual(
            tuple(order.value for order in run.result.order_ids),
            ("SYN-ORDER-000001", "SYN-ORDER-000002"),
        )

    def test_complete_candidate_outcome_is_bound_to_native_union(self) -> None:
        run = self.make_run(
            native_results=(
                self.native_result(
                    self.email,
                    "SYN-ORDER-000003",
                    "SYN-ORDER-000001",
                ),
                self.native_result(
                    self.phone,
                    "SYN-ORDER-000002",
                    "SYN-ORDER-000001",
                ),
            ),
        )
        self.assertIs(run.result.outcome, DiscoveryOutcome.CANDIDATES_FOUND)
        self.assertTrue(run.result.enumeration_complete)
        self.assertEqual(
            tuple(order.value for order in run.result.order_ids),
            (
                "SYN-ORDER-000001",
                "SYN-ORDER-000002",
                "SYN-ORDER-000003",
            ),
        )
        self.assertEqual(run.result.identifiers_required, 2)
        self.assertEqual(run.result.identifiers_attempted, 2)
        self.assertEqual(run.result.identifiers_completed, 2)

    def test_incomplete_search_retains_candidates_without_no_order_conclusion(self) -> None:
        after_window = "2026-08-16T04:00:00Z"
        run = self.make_run(
            native_results=(
                self.native_result(
                    self.email,
                    "SYN-ORDER-000004",
                    completeness=SearchCompleteness.INCOMPLETE,
                ),
                self.native_result(self.phone),
            ),
            completed_at=after_window,
        )
        self.assertIs(run.result.outcome, DiscoveryOutcome.CANDIDATES_FOUND)
        self.assertFalse(run.result.enumeration_complete)
        self.assertEqual(
            tuple(order.value for order in run.result.order_ids),
            ("SYN-ORDER-000004",),
        )
        self.assertEqual(run.result.identifiers_completed, 1)

        no_candidates = self.make_run(
            native_results=(
                self.native_result(
                    self.email,
                    completeness=SearchCompleteness.INCOMPLETE,
                ),
                self.native_result(self.phone),
            ),
            completed_at=after_window,
        )
        self.assertIs(
            no_candidates.result.outcome,
            DiscoveryOutcome.SEARCH_INCOMPLETE,
        )
        self.assertFalse(no_candidates.result.enumeration_complete)
        self.assertEqual(no_candidates.result.order_ids, ())
        self.assertEqual(
            no_candidates.result.reasons,
            (SalesCreditReason.IDENTIFIER_SEARCH_INCOMPLETE,),
        )

    def test_complete_no_order_records_exact_active_and_closed_outcomes(self) -> None:
        active = self.make_run(
            completed_at="2026-08-16T03:59:59.999999999Z",
        )
        closed = self.make_run(
            completed_at="2026-08-16T04:00:00Z",
        )
        self.assertIs(
            active.result.outcome,
            DiscoveryOutcome.CHECKED_NO_ORDER_WINDOW_ACTIVE,
        )
        self.assertEqual(
            active.result.reasons,
            (SalesCreditReason.NO_ORDER_WINDOW_ACTIVE,),
        )
        self.assertIs(
            closed.result.outcome,
            DiscoveryOutcome.REVIEW_WINDOW_CLOSED_NO_ORDER,
        )
        self.assertEqual(
            closed.result.reasons,
            (SalesCreditReason.NO_ORDER_WINDOW_CLOSED,),
        )
        for run in (active, closed):
            self.assertTrue(run.result.enumeration_complete)
            self.assertEqual(run.result.order_ids, ())

        later_window = self.interaction(
            3,
            email="later.window@example.test",
            recorded_at="2026-08-02T14:00:00Z",
            review_window_start=date(2026, 8, 2),
        )
        mixed_interactions = (*self.interactions, later_window)
        mixed_active = self.make_run(
            interactions=mixed_interactions,
            completed_at="2026-08-17T03:59:59.999999999Z",
        )
        mixed_closed = self.make_run(
            interactions=mixed_interactions,
            completed_at="2026-08-17T04:00:00Z",
        )
        self.assertIs(
            mixed_active.result.outcome,
            DiscoveryOutcome.CHECKED_NO_ORDER_WINDOW_ACTIVE,
        )
        self.assertIs(
            mixed_closed.result.outcome,
            DiscoveryOutcome.REVIEW_WINDOW_CLOSED_NO_ORDER,
        )

    def test_every_scoped_interaction_requires_its_own_usable_identifier(self) -> None:
        unusable = self.interaction(3)
        scopes = (
            (unusable,),
            (*self.interactions, unusable),
        )
        for interactions in scopes:
            with self.subTest(scope_size=len(interactions)):
                with self.assertRaisesRegex(
                    DiscoveryValidationError,
                    "search_run_unusable_interaction",
                ):
                    self.make_run(interactions=interactions)

    def test_every_candidate_from_every_identifier_is_captured_without_early_exit(self) -> None:
        broad_interactions = (
            self.interaction(
                3,
                email="a.search@example.test",
                phone="212-555-0101",
            ),
            self.interaction(
                4,
                email="z.search@example.test",
                phone="212-555-0102",
            ),
        )
        broad_plan = plan_discovery(
            email_values=("a.search@example.test", "z.search@example.test"),
            phone_values=("212-555-0101", "212-555-0102"),
        )
        native_results = tuple(
            self.native_result(
                identifier,
                f"SYN-ORDER-{index:06d}",
                "SYN-ORDER-000099",
                completeness=(
                    SearchCompleteness.INCOMPLETE
                    if index == 3
                    else SearchCompleteness.COMPLETE
                ),
            )
            for index, identifier in enumerate(broad_plan.identifiers, start=1)
        )
        run = self.make_run(
            interactions=broad_interactions,
            native_results=native_results,
        )
        self.assertEqual(len(run.native_result_sets), 4)
        self.assertEqual(run.attempted_identifiers, broad_plan.identifiers)
        self.assertEqual(run.result.identifiers_attempted, 4)
        self.assertEqual(run.result.identifiers_completed, 3)
        self.assertFalse(run.result.enumeration_complete)
        self.assertEqual(
            tuple(order.value for order in run.result.order_ids),
            (
                "SYN-ORDER-000001",
                "SYN-ORDER-000002",
                "SYN-ORDER-000003",
                "SYN-ORDER-000004",
                "SYN-ORDER-000099",
            ),
        )

    def test_forged_terminal_result_or_early_exit_union_is_rejected(self) -> None:
        native_results = (
            self.native_result(self.email, "SYN-ORDER-000001"),
            self.native_result(self.phone, "SYN-ORDER-000002"),
        )
        run = self.make_run(native_results=native_results)
        forged = DiscoveryResult(
            outcome=DiscoveryOutcome.CANDIDATES_FOUND,
            order_ids=(OrderId("SYN-ORDER-000001"),),
            enumeration_complete=True,
            identifiers_required=2,
            identifiers_attempted=2,
            identifiers_completed=2,
        )
        with self.assertRaisesRegex(ValueError, "init=False"):
            replace(run, result=forged)

        with self.assertRaisesRegex(ValueError, "init=False"):
            replace(run, result="CANDIDATES_FOUND")  # type: ignore[arg-type]

    def test_adapter_and_schema_versions_are_exact(self) -> None:
        run = self.make_run()
        self.assertEqual(
            run.adapter,
            VersionBinding(
                component="sales_credit_search_adapter",
                version="sales-credit-search-adapter/v1",
            ),
        )
        self.assertEqual(
            OrderSearchRun.ADAPTER_VERSION,
            "sales-credit-search-adapter/v1",
        )
        self.assertEqual(run.schema_version, "sales-credit-order-search-run/v1")

        invalid_adapters: tuple[object, ...] = (
            VersionBinding(
                component="other_search_adapter",
                version=OrderSearchRun.ADAPTER_VERSION,
            ),
            VersionBinding(
                component="sales_credit_search_adapter",
                version="sales-credit-search-adapter/v2",
            ),
            "sales-credit-search-adapter/v1",
        )
        for adapter in invalid_adapters:
            with self.subTest(adapter_type=type(adapter).__name__):
                with self.assertRaisesRegex(
                    DiscoveryValidationError,
                    "search_run_adapter",
                ):
                    replace(run, adapter=adapter)  # type: ignore[arg-type]

        for schema in ("sales-credit-order-search-run/v2", None):
            with self.subTest(schema=schema):
                with self.assertRaisesRegex(
                    DiscoveryValidationError,
                    "search_run_schema",
                ):
                    replace(run, schema_version=schema)  # type: ignore[arg-type]

    def test_timestamps_are_exact_typed_and_monotonic(self) -> None:
        run = self.make_run()
        self.assertEqual(run.started_at.value, "2026-08-10T14:00:00.123456789Z")
        self.assertEqual(run.completed_at.value, "2026-08-10T14:00:01.000000001Z")

        equal = replace(run, completed_at=run.started_at)
        self.assertEqual(equal.started_at, equal.completed_at)

        with self.assertRaisesRegex(
            DiscoveryValidationError,
            "search_run_time_order",
        ):
            replace(
                run,
                completed_at=_timestamp("2026-08-10T14:00:00.123456788Z"),
            )
        for field_name in ("started_at", "completed_at"):
            with self.subTest(field=field_name):
                with self.assertRaisesRegex(
                    DiscoveryValidationError,
                    f"search_run_{field_name.removesuffix('_at')}",
                ):
                    replace(run, **{field_name: run.started_at.value})

    def test_warning_codes_are_bounded_sorted_unique_and_strict(self) -> None:
        warnings = ("ADAPTER_NOTICE", "RETRYABLE_ENUMERATION_WARNING")
        run = self.make_run(warnings=warnings)
        self.assertEqual(run.warnings, warnings)

        invalid_warnings: tuple[object, ...] = (
            tuple(reversed(warnings)),
            (warnings[0], warnings[0]),
            ("lowercase_warning",),
            ("A" * 65,),
            (1,),
            list(warnings),
        )
        for value in invalid_warnings:
            with self.subTest(shape=type(value).__name__):
                with self.assertRaisesRegex(
                    DiscoveryValidationError,
                    "search_run_warnings",
                ):
                    replace(run, warnings=value)  # type: ignore[arg-type]

    def test_force_recheck_requires_controlled_explanation_only(self) -> None:
        force = self.make_run(
            trigger=SearchTriggerType.FORCE_RECHECK,
            force_explanation="SYNTHETIC_FORCE_REVIEW",
        )
        self.assertEqual(force.force_explanation, "SYNTHETIC_FORCE_REVIEW")

        for explanation in (None, "OK", "lowercase", "A" * 65, 1):
            with self.subTest(explanation_type=type(explanation).__name__):
                with self.assertRaisesRegex(
                    DiscoveryValidationError,
                    "search_run_force_explanation",
                ):
                    replace(force, force_explanation=explanation)  # type: ignore[arg-type]

        for trigger in (
            SearchTriggerType.NORMAL,
            SearchTriggerType.AUTOMATIC_RECHECK,
            SearchTriggerType.REPLACEMENT_CHECK,
        ):
            with self.subTest(trigger=trigger.value):
                with self.assertRaisesRegex(
                    DiscoveryValidationError,
                    "search_run_force_explanation",
                ):
                    replace(force, trigger=trigger)

    def test_automatic_recheck_derives_auditable_per_interaction_witnesses(self) -> None:
        interactions = (
            self.interaction(
                1,
                email="search.run@example.test",
                last_check_at="2026-08-09T23:59:59.999999999Z",
            ),
            self.interaction(2, phone="212-555-0100"),
        )
        run = self.make_run(
            trigger=SearchTriggerType.AUTOMATIC_RECHECK,
            interactions=interactions,
        )

        self.assertEqual(len(run.recheck_results), len(run.interactions))
        for result in run.recheck_results:
            self.assertTrue(result.allowed)
            self.assertIs(result.decision, RecheckDecision.ELIGIBLE)
            self.assertEqual(result.business_date, date(2026, 8, 10))
            self.assertFalse(result.audit_required)
            self.assertFalse(result.bypassed_daily_throttle)
            self.assertIsNone(result.reason)
            self.assertIsNone(result.explanation_code)

    def test_automatic_recheck_rejects_same_local_day_and_future_history(self) -> None:
        invalid_last_checks = (
            "2026-08-10T04:00:00Z",
            "2026-08-10T15:00:00Z",
            "2026-08-11T04:00:00Z",
        )
        for last_check_at in invalid_last_checks:
            with self.subTest(last_check_at=last_check_at):
                interaction = self.interaction(
                    1,
                    email="search.run@example.test",
                    last_check_at=last_check_at,
                )
                with self.assertRaisesRegex(
                    DiscoveryValidationError,
                    "search_run_recheck_ineligible",
                ):
                    self.make_run(
                        trigger=SearchTriggerType.AUTOMATIC_RECHECK,
                        interactions=(interaction,),
                    )

        prior_local_date = self.interaction(
            1,
            email="search.run@example.test",
            last_check_at="2026-08-10T03:59:59.999999999Z",
        )
        eligible = self.make_run(
            trigger=SearchTriggerType.AUTOMATIC_RECHECK,
            interactions=(prior_local_date,),
        )
        self.assertTrue(eligible.recheck_results[0].allowed)

    def test_automatic_and_force_rechecks_reject_outside_every_selected_window(self) -> None:
        cases = (
            (
                SearchTriggerType.AUTOMATIC_RECHECK,
                "2026-07-31T14:00:00Z",
                "2026-07-31T14:00:01Z",
                None,
                "search_run_not_after_interaction",
            ),
            (
                SearchTriggerType.AUTOMATIC_RECHECK,
                "2026-08-16T04:00:00Z",
                "2026-08-16T04:00:01Z",
                None,
                None,
            ),
            (
                SearchTriggerType.FORCE_RECHECK,
                "2026-07-31T14:00:00Z",
                "2026-07-31T14:00:01Z",
                "SYNTHETIC_FORCE_REVIEW",
                "search_run_not_after_interaction",
            ),
            (
                SearchTriggerType.FORCE_RECHECK,
                "2026-08-16T04:00:00Z",
                "2026-08-16T04:00:01Z",
                "SYNTHETIC_FORCE_REVIEW",
                None,
            ),
        )
        for trigger, started_at, completed_at, explanation, error_code in cases:
            with self.subTest(trigger=trigger.value, started_at=started_at):
                if error_code is None:
                    terminal = self.make_run(
                        trigger=trigger,
                        started_at=started_at,
                        completed_at=completed_at,
                        force_explanation=explanation,
                    )
                    self.assertIs(
                        terminal.result.outcome,
                        DiscoveryOutcome.REVIEW_WINDOW_CLOSED_NO_ORDER,
                    )
                    self.assertTrue(
                        all(not result.allowed for result in terminal.recheck_results)
                    )
                    continue
                with self.assertRaisesRegex(
                    DiscoveryValidationError,
                    error_code,
                ):
                    self.make_run(
                        trigger=trigger,
                        started_at=started_at,
                        completed_at=completed_at,
                        force_explanation=explanation,
                    )

    def test_selected_force_recheck_is_audited_and_bypasses_only_daily_throttle(self) -> None:
        interactions = (
            self.interaction(
                1,
                email="search.run@example.test",
                last_check_at="2026-08-10T13:59:59Z",
            ),
        )
        force = self.make_run(
            trigger=SearchTriggerType.FORCE_RECHECK,
            interactions=interactions,
            force_explanation="SYNTHETIC_FORCE_REVIEW",
        )

        self.assertEqual(len(force.recheck_results), 1)
        witness = force.recheck_results[0]
        self.assertTrue(witness.allowed)
        self.assertIs(witness.decision, RecheckDecision.FORCE_RECHECK_SELECTED)
        self.assertTrue(witness.audit_required)
        self.assertTrue(witness.bypassed_daily_throttle)
        self.assertIs(witness.reason, SalesCreditReason.FORCE_RECHECK_ACCEPTED)
        self.assertEqual(witness.explanation_code, "SYNTHETIC_FORCE_REVIEW")

        with self.assertRaisesRegex(
            DiscoveryValidationError,
            "search_run_force_explanation",
        ):
            self.make_run(trigger=SearchTriggerType.FORCE_RECHECK)
        with self.assertRaisesRegex(
            DiscoveryValidationError,
            "search_run_interactions",
        ):
            self.make_run(
                trigger=SearchTriggerType.FORCE_RECHECK,
                interactions=(),
                native_results=(),
                force_explanation="SYNTHETIC_FORCE_REVIEW",
            )

    def test_force_explanation_scans_prohibited_material_without_leaking(self) -> None:
        # Runtime composition keeps the deliberate VIN-shaped canary out of repository text.
        canary = "".join(("ABCDEFGH", "JKLMNPRST"))
        self.assertEqual(len(canary), 17)
        normal = self.make_run()
        error = self.assert_rejected_without_leak(
            lambda: replace(
                normal,
                trigger=SearchTriggerType.FORCE_RECHECK,
                force_explanation=canary,
            ),
            canary,
        )
        self.assertEqual(error.code, "search_run_force_explanation")

    def test_ledger_commits_active_state_exact_replay_and_conflict_atomically(self) -> None:
        ledger = _no_order_ledger()
        initial = self.make_run(run_id="SYN-RUN-LEDGER-INITIAL-0001")
        accepted = ledger.apply_run(initial)
        self.assertIs(type(accepted), NoOrderTransitionResult)
        self.assertFalse(accepted.replayed)  # type: ignore[union-attr]
        self.assertIs(
            accepted.workflow_state,  # type: ignore[union-attr]
            WorkflowState.CHECKED_NO_ORDER_WINDOW_ACTIVE,
        )
        self.assertEqual(
            accepted.reasons,  # type: ignore[union-attr]
            (SalesCreditReason.NO_ORDER_WINDOW_ACTIVE,),
        )
        self.assertEqual(accepted.interaction_count, 2)  # type: ignore[union-attr]
        self.assertEqual(accepted.identifiers_required, 2)  # type: ignore[union-attr]
        self.assertFalse(hasattr(accepted, "run"))
        self.assertFalse(hasattr(accepted, "interactions"))
        for retained in ledger.retained_interactions:
            self.assertIs(
                retained.workflow_state,
                WorkflowState.CHECKED_NO_ORDER_WINDOW_ACTIVE,
            )
            self.assertEqual(retained.last_check_at, initial.started_at)
            self.assertEqual(
                retained.next_eligible_check_at,
                _timestamp("2026-08-11T04:00:00Z"),
            )

        replay = ledger.apply_run(initial)
        self.assertIs(type(replay), NoOrderTransitionResult)
        self.assertTrue(replay.replayed)  # type: ignore[union-attr]
        self.assertEqual(ledger.receipt_count, 1)
        self.assertEqual(repr(replay), "NoOrderTransitionResult(<minimized>)")

        conflicting = replace(initial, warnings=("CHANGED_MATERIAL",))
        before = ledger.retained_interactions
        with self.assertRaisesRegex(
            NoOrderLedgerError,
            "no_order_run_replay_conflict",
        ):
            ledger.apply_run(conflicting)
        self.assertEqual(ledger.retained_interactions, before)
        self.assertEqual(ledger.receipt_count, 1)

        repeated_normal = self.make_run(
            run_id="SYN-RUN-LEDGER-REPEATED-NORMAL",
            interactions=ledger.retained_interactions,
        )
        with self.assertRaisesRegex(
            NoOrderLedgerError,
            "no_order_transition_not_allowed",
        ):
            ledger.apply_run(repeated_normal)

    def test_shared_run_authority_claims_exact_bytes_and_rolls_back_by_owner(
        self,
    ) -> None:
        authority = InMemorySearchRunAuthority()
        first_owner = authority.new_owner()
        second_owner = authority.new_owner()
        run = self.make_run(run_id="SYN-RUN-SHARED-AUTHORITY-0001")

        first = authority.claim(run, owner=first_owner)
        same_owner = authority.claim(run, owner=first_owner)
        second = authority.claim(run, owner=second_owner)
        self.assertTrue(first.newly_acquired)
        self.assertFalse(same_owner.newly_acquired)
        self.assertTrue(second.newly_acquired)
        self.assertEqual(repr(first), "SearchRunAuthorityClaim(<redacted>)")
        self.assertEqual(len(authority.retained_canonical_material), 1)
        self.assertIn(
            b"search.run@example.test",
            authority.retained_canonical_material[0],
        )

        with self.assertRaisesRegex(
            SearchRunAuthorityError,
            "search_run_material_conflict",
        ):
            authority.claim(
                replace(run, warnings=("CHANGED_MATERIAL",)),
                owner=second_owner,
            )
        authority.rollback(second)
        self.assertEqual(len(authority.retained_canonical_material), 1)
        authority.rollback(same_owner)
        self.assertEqual(len(authority.retained_canonical_material), 1)
        authority.release_run(run.run_id, owner=first_owner)
        self.assertEqual(authority.retained_canonical_material, ())
        authority.rollback(first)
        self.assertEqual(authority.retained_canonical_material, ())

        with self.assertRaisesRegex(
            SearchRunAuthorityError,
            "search_run_owner",
        ):
            authority.claim(run, owner=object())

    def test_no_order_ledger_requires_an_explicit_shared_run_authority(self) -> None:
        with self.assertRaises(TypeError):
            InMemoryNoOrderStateLedger()  # type: ignore[call-arg]
        with self.assertRaisesRegex(
            NoOrderLedgerError,
            "no_order_search_run_authority",
        ):
            InMemoryNoOrderStateLedger(  # type: ignore[arg-type]
                search_run_authority=None
            )

    def test_two_ledgers_inject_one_authority_for_cross_ledger_runid_conflict(
        self,
    ) -> None:
        authority = InMemorySearchRunAuthority()
        first = InMemoryNoOrderStateLedger(search_run_authority=authority)
        second = InMemoryNoOrderStateLedger(search_run_authority=authority)
        run = self.make_run(run_id="SYN-RUN-CROSS-LEDGER-0001")
        first.apply_run(run)
        with self.assertRaisesRegex(
            NoOrderLedgerError,
            "no_order_run_replay_conflict",
        ):
            second.apply_run(replace(run, warnings=("CHANGED_MATERIAL",)))
        self.assertEqual(second.retained_interactions, ())
        self.assertEqual(second.receipt_count, 0)
        self.assertEqual(len(authority.retained_canonical_material), 1)

    def test_ledger_enforces_next_day_auto_against_stale_sequential_and_racing_runs(
        self,
    ) -> None:
        ledger = _no_order_ledger()
        initial = ledger.apply_run(
            self.make_run(run_id="SYN-RUN-LEDGER-DAY-ZERO")
        )
        self.assertIs(type(initial), NoOrderTransitionResult)
        current = ledger.retained_interactions
        first_auto = self.make_run(
            trigger=SearchTriggerType.AUTOMATIC_RECHECK,
            interactions=current,
            started_at="2026-08-11T14:00:00Z",
            completed_at="2026-08-11T14:00:01Z",
            run_id="SYN-RUN-LEDGER-AUTO-0001",
        )
        stale_auto = self.make_run(
            trigger=SearchTriggerType.AUTOMATIC_RECHECK,
            interactions=current,
            started_at="2026-08-11T15:00:00Z",
            completed_at="2026-08-11T15:00:01Z",
            run_id="SYN-RUN-LEDGER-AUTO-0002",
        )
        accepted = ledger.apply_run(first_auto)
        self.assertIs(type(accepted), NoOrderTransitionResult)
        with self.assertRaisesRegex(
            NoOrderLedgerError,
            "no_order_stale_interaction",
        ):
            ledger.apply_run(stale_auto)
        for retained in ledger.retained_interactions:
            self.assertEqual(retained.last_check_at, first_auto.started_at)
            self.assertEqual(
                retained.next_eligible_check_at,
                _timestamp("2026-08-12T04:00:00Z"),
            )

        racing_ledger = _no_order_ledger()
        racing_initial = racing_ledger.apply_run(
            self.make_run(run_id="SYN-RUN-LEDGER-RACE-INITIAL")
        )
        self.assertIs(type(racing_initial), NoOrderTransitionResult)
        racing_current = racing_ledger.retained_interactions
        racing_runs = tuple(
            self.make_run(
                trigger=SearchTriggerType.AUTOMATIC_RECHECK,
                interactions=racing_current,
                started_at="2026-08-11T16:00:00Z",
                completed_at="2026-08-11T16:00:01Z",
                run_id=f"SYN-RUN-LEDGER-RACE-AUTO-{index:04d}",
            )
            for index in (1, 2)
        )
        barrier = Barrier(3)

        def race(run: OrderSearchRun) -> tuple[str, object]:
            barrier.wait()
            try:
                return "accepted", racing_ledger.apply_run(run)
            except NoOrderLedgerError as error:
                return "rejected", error.code

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(race, run) for run in racing_runs]
            barrier.wait()
            outcomes = [future.result(timeout=5) for future in futures]
        self.assertEqual(
            sorted(label for label, _ in outcomes),
            ["accepted", "rejected"],
        )
        self.assertEqual(
            [value for label, value in outcomes if label == "rejected"],
            ["no_order_stale_interaction"],
        )
        self.assertEqual(racing_ledger.active_receipt_count, 2)

    def test_ledger_rejects_non_no_order_results_and_replacement_roots(self) -> None:
        candidate = self.make_run(
            native_results=(
                self.native_result(self.email, "SYN-ORDER-000901"),
                self.native_result(self.phone),
            ),
            run_id="SYN-RUN-LEDGER-CANDIDATE",
        )
        incomplete = self.make_run(
            native_results=(
                self.native_result(
                    self.email,
                    completeness=SearchCompleteness.INCOMPLETE,
                ),
                self.native_result(self.phone),
            ),
            run_id="SYN-RUN-LEDGER-INCOMPLETE",
        )
        replacement = self.make_run(
            trigger=SearchTriggerType.REPLACEMENT_CHECK,
            run_id="SYN-RUN-LEDGER-REPLACEMENT",
        )
        self.assertEqual(replacement.recheck_results, ())

        ledger = _no_order_ledger()
        for run, code in (
            (candidate, "no_order_result_not_complete_empty"),
            (incomplete, "no_order_result_not_complete_empty"),
            (replacement, "replacement_check_not_no_order_root"),
        ):
            with self.subTest(code=code):
                with self.assertRaisesRegex(NoOrderLedgerError, code):
                    ledger.apply_run(run)
                self.assertEqual(ledger.retained_interactions, ())
                self.assertEqual(ledger.receipt_count, 0)

        terminal_replacement = self.make_run(
            trigger=SearchTriggerType.REPLACEMENT_CHECK,
            completed_at="2026-08-16T04:00:00Z",
            started_at="2026-08-16T03:59:59Z",
            run_id="SYN-RUN-LEDGER-REPLACEMENT-CLOSED",
        )
        self.assertIs(
            terminal_replacement.result.outcome,
            DiscoveryOutcome.REVIEW_WINDOW_CLOSED_NO_ORDER,
        )
        with self.assertRaisesRegex(
            NoOrderLedgerError,
            "replacement_check_not_no_order_root",
        ):
            ledger.apply_run(terminal_replacement)

    def test_search_run_requires_proved_post_interaction_start_for_every_outcome(
        self,
    ) -> None:
        exact = self.interaction(
            41,
            email="exact.start@example.test",
            recorded_at="2026-08-01T14:00:00Z",
        )
        uncertain = self.interaction(
            42,
            email="uncertain.start@example.test",
            recorded_at="2026-08-01T14:00:00Z",
            precision=TimestampPrecision.HISTORICAL_APPROXIMATION,
        )
        exact_plan = plan_discovery(email_values=(exact.email,))
        candidate_results = (
            self.native_result(
                exact_plan.identifiers[0],
                "SYN-ORDER-PRE-INTERACTION-0001",
            ),
        )
        for index, trigger in enumerate(SearchTriggerType, start=1):
            with self.subTest(trigger=trigger.value):
                with self.assertRaisesRegex(
                    DiscoveryValidationError,
                    "search_run_not_after_interaction",
                ):
                    self.make_run(
                        trigger=trigger,
                        interactions=(exact,),
                        native_results=candidate_results,
                        started_at="2026-08-01T13:59:59.999999999Z",
                        completed_at="2026-08-01T14:00:01Z",
                        force_explanation=(
                            "SYNTHETIC_FORCE_REVIEW"
                            if trigger is SearchTriggerType.FORCE_RECHECK
                            else None
                        ),
                        run_id=f"SYN-RUN-BEFORE-TRIGGER-{index:04d}",
                    )
        for interactions, started_at, run_id in (
            (
                (exact,),
                "2026-08-01T14:00:00Z",
                "SYN-RUN-EQUAL-INTERACTION",
            ),
            (
                (uncertain,),
                "2026-08-01T15:00:00Z",
                "SYN-RUN-UNCERTAIN-SAME-DAY",
            ),
        ):
            with self.subTest(run_id=run_id):
                with self.assertRaisesRegex(
                    DiscoveryValidationError,
                    "search_run_not_after_interaction",
                ):
                    self.make_run(
                        interactions=interactions,
                        started_at=started_at,
                        completed_at="2026-08-01T15:00:01Z",
                        run_id=run_id,
                    )

        proved_after = self.make_run(
            interactions=(exact,),
            started_at="2026-08-01T14:00:00.000000001Z",
            completed_at="2026-08-01T14:00:01Z",
            run_id="SYN-RUN-LEDGER-PROVED-AFTER",
        )
        self.assertIs(
            type(_no_order_ledger().apply_run(proved_after)),
            NoOrderTransitionResult,
        )

        later_date_uncertain = self.make_run(
            interactions=(uncertain,),
            started_at="2026-08-02T04:00:00Z",
            completed_at="2026-08-02T04:00:01Z",
            run_id="SYN-RUN-UNCERTAIN-LATER-DATE",
        )
        self.assertIs(type(later_date_uncertain), OrderSearchRun)

    def test_terminal_no_order_run_must_start_after_the_inclusive_window(
        self,
    ) -> None:
        exact = self.interaction(
            43,
            email="terminal.start@example.test",
            recorded_at="2026-08-01T14:00:00Z",
        )

        crosses_terminal_boundary = self.make_run(
            interactions=(exact,),
            started_at="2026-08-16T03:59:59.999999999Z",
            completed_at="2026-08-16T04:00:00Z",
            run_id="SYN-RUN-LEDGER-CROSSES-CLOSE",
        )
        self.assertIs(
            crosses_terminal_boundary.result.outcome,
            DiscoveryOutcome.REVIEW_WINDOW_CLOSED_NO_ORDER,
        )
        with self.assertRaisesRegex(
            NoOrderLedgerError,
            "no_order_terminal_started_before_close",
        ):
            _no_order_ledger().apply_run(crosses_terminal_boundary)

    def test_closed_field_types_reject_string_and_boolean_aliases(self) -> None:
        run = self.make_run()
        replacements: tuple[tuple[str, object, str], ...] = (
            ("run_id", "SYN-RUN-000001", "search_run_id"),
            ("trigger", "NORMAL", "search_run_trigger"),
            ("trigger", True, "search_run_trigger"),
        )
        for field_name, value, code in replacements:
            with self.subTest(field=field_name, value_type=type(value).__name__):
                with self.assertRaisesRegex(DiscoveryValidationError, code):
                    replace(run, **{field_name: value})

    def test_run_is_frozen_slotted_and_repr_redacts_all_material(self) -> None:
        run = self.make_run(
            trigger=SearchTriggerType.FORCE_RECHECK,
            native_results=(
                self.native_result(self.email, "SYN-ORDER-000777"),
                self.native_result(self.phone),
            ),
            warnings=("SYNTHETIC_WARNING",),
            force_explanation="SYNTHETIC_FORCE_REVIEW",
        )
        rendered = repr(run)
        self.assertEqual(rendered, "OrderSearchRun(<redacted>)")
        for private_value in (
            run.run_id.value,
            *(item.value for item in run.interaction_ids),
            *(item.value for item in run.attempted_identifiers),
            *(item.value for item in run.result.order_ids),
            *(item.email for item in run.interactions if item.email is not None),
            *(item.phone for item in run.interactions if item.phone is not None),
            *run.warnings,
            run.force_explanation,
            run.started_at.value,
        ):
            self.assertNotIn(private_value, rendered)
        self.assertEqual(
            tuple(item.name for item in fields(OrderSearchRun)),
            (
                "run_id",
                "trigger",
                "interactions",
                "native_result_sets",
                "adapter",
                "started_at",
                "completed_at",
                "warnings",
                "force_explanation",
                "schema_version",
                "interaction_ids",
                "attempted_identifiers",
                "recheck_results",
                "result",
            ),
        )
        self.assertFalse(hasattr(run, "__dict__"))
        with self.assertRaises(FrozenInstanceError):
            run.warnings = ()  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
