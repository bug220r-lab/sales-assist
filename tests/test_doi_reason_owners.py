from __future__ import annotations

import unittest

from synthetic_sales_assist.doi.evaluator import evaluate_doi
from synthetic_sales_assist.doi.models import (
    DOIEvaluationInput,
    DropShipState,
    GeographyClass,
    HumanFactResultCode,
    HumanFactUsageKind,
    LineAvailability,
    OrderState,
    QuantityAvailability,
    RepRelation,
)
from synthetic_sales_assist.domain.identities import OrderId
from tests.test_doi_evaluator import (
    evaluation_input,
    human_fact,
    make_line,
    order_source,
    split_lines,
)


class DOIActualRuleReasonOwnershipTests(unittest.TestCase):
    """Independent actual-rule oracles for reasons shared by compact branch tests."""

    def test_core_rule_outputs_emit_exact_registered_reasons(self) -> None:
        source = order_source(OrderId("SYN-ORDER-DOI-0001"))
        full_ds = (
            make_line(
                1,
                source,
                drop_ship=DropShipState.DS,
                availability=LineAvailability.IN_STOCK,
                quantity_availability=QuantityAvailability.FULL,
                explicitly_available=2,
            ),
        )
        mixed_ds = (
            make_line(1, source, drop_ship=DropShipState.DS),
            make_line(2, source),
        )
        partial = (
            make_line(
                1,
                source,
                availability=LineAvailability.IN_STOCK,
                quantity_availability=QuantityAvailability.PARTIAL,
                active_quantity=3,
                explicitly_available=1,
            ),
        )
        all_in_stock = (
            make_line(
                1,
                source,
                availability=LineAvailability.IN_STOCK,
                quantity_availability=QuantityAvailability.FULL,
                explicitly_available=2,
            ),
        )
        cases = (
            ("full_ds", evaluation_input(full_ds), {"RC-019"}),
            ("mixed_ds", evaluation_input(mixed_ds), {"RC-020", "RC-030"}),
            ("split", evaluation_input(split_lines()), {"RC-031", "RC-052"}),
            ("partial", evaluation_input(partial), {"RC-032", "RC-052"}),
            (
                "shipped",
                evaluation_input(split_lines(), order_state=OrderState.SHIPPED),
                {"RC-021"},
            ),
            (
                "canceled",
                evaluation_input(split_lines(), order_state=OrderState.CANCELED),
                {"RC-022"},
            ),
            (
                "transferred",
                evaluation_input(split_lines(), rep_relation=RepRelation.OTHER_REP),
                {"RC-023"},
            ),
            (
                "all_in_stock",
                evaluation_input(
                    all_in_stock,
                    geography=GeographyClass.DOMESTIC_STANDARD,
                ),
                {"RC-028"},
            ),
        )
        for name, request, expected in cases:
            with self.subTest(case=name):
                result = evaluate_doi(request)
                self.assertEqual(
                    {reason.code for reason in result.reasons.reasons},
                    expected,
                )

        monitor_base = evaluation_input(
            (make_line(1, source),),
            evaluation_suffix="REASON-OWNER-MONITOR",
            order_state=OrderState.ACTIVE,
        )
        monitor_fact = human_fact(
            monitor_base,
            usage=HumanFactUsageKind.NO_ACTION_DECISION,
            result=HumanFactResultCode.APPROVED,
            suffix="REASON-OWNER-MONITOR",
        )
        monitor = evaluate_doi(
            DOIEvaluationInput(
                evaluation_id=monitor_base.evaluation_id,
                snapshot=monitor_base.snapshot,
                evaluated_at=monitor_base.evaluated_at,
                human_facts=(monitor_fact,),
            )
        )
        self.assertEqual(
            {reason.code for reason in monitor.reasons.reasons},
            {"RC-029"},
        )


if __name__ == "__main__":
    unittest.main()
