"""Prepare the deterministic local-only Milestone 7 manager demonstration."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

from synthetic_sales_assist.application import ScenarioApplication
from synthetic_sales_assist.domain.canonical import canonical_json_bytes
from synthetic_sales_assist.persistence.telemetry import SAFETY_COUNTER_NAMES
from synthetic_sales_assist.safety.content import assert_payload_safe


DEMO_PREPARATION_SCHEMA_VERSION: Final = (
    "synthetic-sales-assist-m7-demo-preparation/v1"
)
EXPECTED_DATABASE_SCHEMA_VERSION: Final = 4
_ERROR_CODE = re.compile(r"\A[A-Z][A-Z0-9_]{0,95}\Z", re.ASCII)


class DemoPreparationError(RuntimeError):
    """Fail closed without copying a path or application payload into output."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class _ScenarioPlan:
    alias: str
    rule_pack: str
    expected_result: str
    expected_workflow: str
    human_review_required: bool

    @property
    def instance_key(self) -> str:
        return f"m7-demo-{self.alias}"

    @property
    def evaluation_key(self) -> str:
        return f"m7-demo-evaluate-{self.alias}"


_PLANS: Final = (
    _ScenarioPlan(
        "sales-credit-target-rep",
        "SALES_CREDIT",
        "CREDIT_CONFIRMED_TARGET_REP",
        "CREDIT_CONFIRMED_TARGET_REP",
        False,
    ),
    _ScenarioPlan(
        "sales-credit-human-review",
        "SALES_CREDIT",
        "MANUAL_REVIEW_REQUIRED",
        "MANUAL_REVIEW_REQUIRED",
        True,
    ),
    _ScenarioPlan(
        "doi-fulfillment-split",
        "DOI",
        "DOI_OPPORTUNITY",
        "ACTIVE",
        True,
    ),
    _ScenarioPlan(
        "doi-overlap",
        "DOI",
        "DOI_OPPORTUNITY",
        "ACTIVE",
        True,
    ),
)
_MALFORMED_ALIAS: Final = "malformed-input"
_MALFORMED_INSTANCE_KEY: Final = "m7-demo-malformed-incomplete"


def _evaluated_scenario(
    application: ScenarioApplication,
    plan: _ScenarioPlan,
    *,
    preexisting_orders: frozenset[str],
) -> dict[str, object]:
    detail = application.instantiate(
        plan.alias,
        request_key=plan.instance_key,
        mode="complete",
    )
    evaluation = application.evaluate(
        detail.order_id,
        request_key=plan.evaluation_key,
    )
    if (
        detail.rule_pack != plan.rule_pack
        or evaluation.rule_pack != plan.rule_pack
        or evaluation.top_level_result != plan.expected_result
        or evaluation.workflow_state != plan.expected_workflow
        or evaluation.human_review_required is not plan.human_review_required
        or evaluation.case_id is None
        or evaluation.evaluation_id is None
        or evaluation.run_id is None
    ):
        raise DemoPreparationError("M7_DEMO_SCENARIO_RESULT_INVALID")
    case_route = (
        f"/sales-credit/{evaluation.case_id}"
        if plan.rule_pack == "SALES_CREDIT"
        else f"/doi/{evaluation.case_id}"
    )
    return {
        "alias": plan.alias,
        "case_id": evaluation.case_id,
        "evaluation_id": evaluation.evaluation_id,
        "evaluation_replayed": evaluation.replayed,
        "human_review_required": evaluation.human_review_required,
        "instance_preexisting": detail.order_id in preexisting_orders,
        "mode": "complete",
        "order_id": detail.order_id,
        "routes": {
            "case_detail": case_route,
            "evaluation_audit": f"/audit/evaluation/{evaluation.evaluation_id}",
            "order_detail": f"/orders/{detail.order_id}",
            "run_detail": f"/runs/{evaluation.run_id}",
        },
        "rule_pack": plan.rule_pack,
        "run_id": evaluation.run_id,
        "top_level_result": evaluation.top_level_result,
        "workflow_state": evaluation.workflow_state,
    }


def _malformed_scenario(
    application: ScenarioApplication,
    *,
    preexisting_orders: frozenset[str],
) -> dict[str, object]:
    detail = application.instantiate(
        _MALFORMED_ALIAS,
        request_key=_MALFORMED_INSTANCE_KEY,
        mode="incomplete",
    )
    if (
        detail.rule_pack != "DOI"
        or detail.source_status != "INCOMPLETE"
        or detail.latest_evaluation is not None
    ):
        raise DemoPreparationError("M7_DEMO_MALFORMED_STATE_INVALID")
    return {
        "alias": _MALFORMED_ALIAS,
        "evaluated": False,
        "instance_preexisting": detail.order_id in preexisting_orders,
        "mode": "incomplete",
        "order_id": detail.order_id,
        "routes": {"order_detail": f"/orders/{detail.order_id}"},
        "rule_pack": "DOI",
        "source_status": detail.source_status,
    }


def _route_sequence(
    by_alias: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    target = by_alias["sales-credit-target-rep"]
    review = by_alias["sales-credit-human-review"]
    split = by_alias["doi-fulfillment-split"]
    overlap = by_alias["doi-overlap"]
    malformed = by_alias[_MALFORMED_ALIAS]
    return [
        {"route": "/system", "step": 1},
        {"route": "/overview", "step": 2},
        {"route": cast(dict[str, str], target["routes"])["case_detail"], "step": 3},
        {"route": cast(dict[str, str], review["routes"])["case_detail"], "step": 4},
        {"route": cast(dict[str, str], split["routes"])["case_detail"], "step": 5},
        {"route": cast(dict[str, str], overlap["routes"])["case_detail"], "step": 6},
        {"route": "/review", "step": 7},
        {
            "route": cast(dict[str, str], overlap["routes"])["evaluation_audit"],
            "step": 8,
        },
        {"route": cast(dict[str, str], target["routes"])["order_detail"], "step": 9},
        {
            "route": cast(dict[str, str], malformed["routes"])["order_detail"],
            "step": 10,
        },
        {"route": "/system/telemetry", "step": 11},
        {"route": "/system/backups", "step": 12},
    ]


def prepare_demo(data_dir: Path | None = None) -> dict[str, object]:
    """Create or replay the bounded synthetic dataset used by the M7 walkthrough."""

    application = ScenarioApplication.open(data_dir)
    preexisting_orders = frozenset(
        item.order_id for item in application.list_orders()
    )
    scenarios = [
        _evaluated_scenario(
            application,
            plan,
            preexisting_orders=preexisting_orders,
        )
        for plan in _PLANS
    ]
    scenarios.append(
        _malformed_scenario(
            application,
            preexisting_orders=preexisting_orders,
        )
    )
    by_alias = {
        cast(str, scenario["alias"]): scenario for scenario in scenarios
    }
    status = application.system_status(deep=True).to_dict()
    counters = cast(dict[str, int], status["safety_counters"])
    if (
        status["database_status"] != "PASS"
        or status["database_schema_version"] != EXPECTED_DATABASE_SCHEMA_VERSION
        or tuple(counters) != SAFETY_COUNTER_NAMES
        or any(counters.values())
    ):
        raise DemoPreparationError("M7_DEMO_POSTCONDITION_FAILED")
    replay_count = sum(
        scenario.get("evaluation_replayed") is True for scenario in scenarios
    )
    result: dict[str, object] = {
        "all_evaluations_replayed": replay_count == len(_PLANS),
        "database_schema_version": EXPECTED_DATABASE_SCHEMA_VERSION,
        "evaluation_replay_count": replay_count,
        "human_actions": {
            "doi_overlap_selection": "PENDING_MANUAL_CONFIRMATION",
            "sales_credit_manager_outcome": "PENDING_MANUAL_CONFIRMATION",
        },
        "route_sequence": _route_sequence(by_alias),
        "safety_counters": counters,
        "scenarios": scenarios,
        "schema_version": DEMO_PREPARATION_SCHEMA_VERSION,
    }
    assert_payload_safe(result)
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        help="Absolute local runtime root; defaults to LocalAppData SyntheticSalesAssist.",
    )
    return parser


def _write_json(value: object) -> None:
    sys.stdout.buffer.write(canonical_json_bytes(value) + b"\n")


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        _write_json(prepare_demo(arguments.data_dir))
    except Exception as exc:
        code = getattr(exc, "code", None)
        if type(code) is not str or _ERROR_CODE.fullmatch(code) is None:
            code = "M7_DEMO_PREPARATION_FAILED"
        _write_json(
            {
                "error": {"code": code},
                "schema_version": DEMO_PREPARATION_SCHEMA_VERSION,
            }
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
