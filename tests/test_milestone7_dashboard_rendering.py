from __future__ import annotations

import unittest
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser

from synthetic_sales_assist.application.control_center import (
    CONTROL_CENTER_SCHEMA_VERSION,
    DENOMINATOR_REGISTRY_VERSION,
    EXTENSION_STATUS_SCHEMA_VERSION,
    M4_BENCHMARK_REFERENCE,
    denominator_registry,
)
from synthetic_sales_assist.persistence.telemetry import ZERO_SAFETY_COUNTERS
from synthetic_sales_assist.portal.contracts import PortalContractError
from synthetic_sales_assist.portal.dashboard_assets import (
    DASHBOARD_CSS,
    DASHBOARD_JS,
    DASHBOARD_STATIC_ASSETS,
)
from synthetic_sales_assist.portal.dashboard_rendering import (
    DASHBOARD_DOM_VERSION,
    render_dashboard_page,
)


CSRF = "a" * 64
ORDER_ID = "SYN-ORDER-M7-RENDER-0001"
CASE_ID = "SYN-EVIDENCE-M7-DOI-CASE-0001"
EVALUATION_ID = "SYN-EVALUATION-M7-RENDER-0001"
OPPORTUNITY_A = "SYN-EVIDENCE-M7-DOI-OPPORTUNITY-0001"
OPPORTUNITY_B = "SYN-EVIDENCE-M7-DOI-OPPORTUNITY-0002"
EVENT_ID = "SYN-EVIDENCE-M7-EVENT-0001"


def _rate(numerator: int, denominator: int) -> dict[str, object]:
    return {
        "defined": denominator > 0,
        "display": "N/A" if denominator == 0 else f"{numerator / denominator:.1%}",
        "denominator": denominator,
        "numerator": numerator,
    }


def _metrics() -> dict[str, object]:
    return {
        "active_doi_cases": 1,
        "active_doi_opportunities": 2,
        "active_sales_credit_cases": 1,
        "current_human_review_items": 2,
        "database_error_count": 1,
        "doi_evaluation_result_distribution": {"DOI_OPPORTUNITY": 1},
        "doi_state_distribution": {"DOI_OPPORTUNITY": 1},
        "exact_replays": 1,
        "failed_closed_rate": _rate(0, 4),
        "failed_closed_requests": 0,
        "human_review_rate": _rate(2, 2),
        "manager_outcome_rate": _rate(0, 1),
        "material_conflicts": 1,
        "median_latency_ns": 1_500,
        "opportunity_type_counts": {
            "EXACT_SKU_RECHECK": 1,
            "FULFILLMENT_SPLIT": 1,
        },
        "p95_latency_ns": 2_000,
        "potential_by_currency": [
            {
                "amount_minor_units": 1250,
                "currency_code": "USD",
                "currency_registry_version": (
                    "synthetic-iso-style-currency-registry/v1"
                ),
                "currency_scale": 2,
                "item_count": 1,
            }
        ],
        "potential_unavailable_count": 0,
        "realized_by_currency": [],
        "request_result_distribution": {"CONFLICT": 1, "ERROR": 1, "SUCCESS": 2},
        "requests_received": 4,
        "safety_counters": dict(ZERO_SAFETY_COUNTERS),
        "schema_version": DENOMINATOR_REGISTRY_VERSION,
        "sales_credit_result_distribution": {
            "OUTBOUND_EVIDENCE_HUMAN_REVIEW": 1
        },
        "successful_request_rate": _rate(2, 4),
        "successful_requests": 2,
        "throughput_per_second": "1.5",
        "unique_evaluations": 2,
        "unresolved_overlap_count": 0,
        "window": "ALL_DURABLE_HISTORY",
    }


def _timeline() -> list[dict[str, object]]:
    return [
        {
            "event_id": EVENT_ID,
            "event_kind": "CASE_CREATED",
            "occurred_at": "2026-09-01T12:00:00Z",
            "sequence": 1,
            "state": "OUTBOUND_EVIDENCE_HUMAN_REVIEW",
            "transition_id": None,
        }
    ]


def _sales_credit_summary() -> dict[str, object]:
    return {
        "attribution": "TARGET_REP",
        "current_evaluation_id": EVALUATION_ID,
        "human_review_required": True,
        "interaction_count": 2,
        "manager_outcome": None,
        "order_id": ORDER_ID,
        "order_value_status": "AVAILABLE",
        "unresolved_human_review": True,
        "updated_at": "2026-09-01T12:00:00Z",
        "workflow_state": "OUTBOUND_EVIDENCE_HUMAN_REVIEW",
    }


def _doi_summary() -> dict[str, object]:
    return {
        "aggregate_potential_state": "UNAVAILABLE",
        "attention_causes": [],
        "case_id": CASE_ID,
        "current_evaluation_id": EVALUATION_ID,
        "doi_state": "DOI_OPPORTUNITY",
        "human_review_required": True,
        "lifecycle_state": "ACTIVE",
        "opportunity_types": ["EXACT_SKU_RECHECK", "FULFILLMENT_SPLIT"],
        "order_id": ORDER_ID,
        "reason_codes": ["RC-087"],
        "scenario_selection_state": "REQUIRED",
        "updated_at": "2026-09-01T12:00:00Z",
    }


def _opportunities() -> list[dict[str, object]]:
    base: dict[str, object] = {
        "amount_minor_units": None,
        "currency_code": None,
        "currency_registry_version": None,
        "currency_scale": None,
        "mutual_exclusion_group_id": "SYN-EVIDENCE-M7-MUTUAL-EXCLUSION-0001",
        "potential_state": "UNAVAILABLE",
        "scope_components": [],
    }
    return [
        {
            **base,
            "opportunity_id": OPPORTUNITY_A,
            "opportunity_type": "EXACT_SKU_RECHECK",
        },
        {
            **base,
            "opportunity_id": OPPORTUNITY_B,
            "opportunity_type": "FULFILLMENT_SPLIT",
        },
    ]


def _extension() -> dict[str, object]:
    return {
        "expected_package_sha256": (
            "3c0d145c789fb990c9fe849f16a031f397285de020ec14b6bb97551ddf1aca55"
        ),
        "expected_version": "0.1.2",
        "last_seen_at": None,
        "observed_version": None,
        "schema_version": EXTENSION_STATUS_SCHEMA_VERSION,
        "stale_after_seconds": 300,
        "state": "EXPECTED_PACKAGE_ONLY",
    }


def _backup() -> dict[str, object]:
    return {
        "backup_id": "SYN-EVIDENCE-BACKUP-M7-0001",
        "backup_sha256": "c" * 64,
        "completed_at": "2026-09-01T12:00:00Z",
        "foreign_key_check": "ok",
        "quick_check": "ok",
        "schema_version": 4,
        "status": "COMPLETED",
    }


def _restore() -> dict[str, object]:
    return {
        "backup_sha256": "e" * 64,
        "completed_at": "2026-09-01T12:05:00Z",
        "error_code": None,
        "pre_restore_backup_id": "SYN-EVIDENCE-BACKUP-M7-0002",
        "restore_id": "SYN-EVIDENCE-RESTORE-M7-0001",
        "schema_version": 4,
        "status": "COMPLETED",
    }


def _operational_status() -> dict[str, object]:
    return {
        "database_size_bytes": 4096,
        "latest_backup": _backup(),
        "latest_restore": _restore(),
        "safety_observed_at": "2026-09-01T12:06:00Z",
        "verification_observed_at": "2026-09-01T12:06:00Z",
    }


def _database() -> dict[str, object]:
    return {
        "application_schema_version": "synthetic-sales-assist-application/v1",
        "build_version": "synthetic-sales-assist-m8/v1",
        "database_location_class": "LOCAL_FILESYSTEM",
        "database_size_bytes": 4096,
        "database_status": "HEALTHY",
        "foreign_key_status": "OK",
        "integrity_check": "ok",
        "latest_backup": _backup(),
        "latest_restore": _restore(),
        "migrations": [
            {
                "applied_at_utc": f"2026-09-01T12:00:0{version}Z",
                "name": name,
                "sha256": sha256,
                "version": version,
            }
            for version, name, sha256 in (
                (
                    1,
                    "foundation",
                    "5693cfe9868f10868d134bd042ccc26271126be9eae847a214c26f57216d6638",
                ),
                (
                    2,
                    "shared_persistence",
                    "5e6f5ea08a4cfd5ec6241da60c49721d99c246fa1e4251d44293a1487e749e31",
                ),
                (
                    3,
                    "sales_credit_persistence",
                    "fd22b13f73d389422405bf222313e34a4aa5995f6b28610a222108a3da813395",
                ),
                (
                    4,
                    "doi_persistence",
                    "5799e5fe3b0e1c9ffae948f6c6b0a820556a9a0d200b29d7c5751e80c475b09d",
                ),
            )
        ],
        "projection_status": "OK",
        "quick_check": "ok",
        "safety_counters": dict(ZERO_SAFETY_COUNTERS),
        "safety_observed_at": "2026-09-01T12:06:00Z",
        "schema_version": 4,
        "verification_observed_at": "2026-09-01T12:06:00Z",
    }


def _views() -> dict[str, dict[str, object]]:
    sc_summary = _sales_credit_summary()
    doi_summary = _doi_summary()
    return {
        "overview": {
            "metrics": _metrics(),
            "reconciliation": {
                "active_doi_cases": 1,
                "active_sales_credit_cases": 1,
                "current_human_review_items": 2,
                "doi_history_events": 3,
                "exact_replays": 1,
                "material_conflicts": 1,
                "sales_credit_history_events": 2,
                "unique_evaluations": 2,
            },
            "schema_version": CONTROL_CENTER_SCHEMA_VERSION,
            "system": {
                "database_status": "HEALTHY",
                "extension_status": "EXPECTED_PACKAGE_ONLY",
                "latest_backup": _backup(),
                "service_status": "PASS",
            },
        },
        "sales_credit_queue": {
            "items": [sc_summary],
            "limit": 25,
            "offset": 0,
            "query": {
                "descending": True,
                "search": None,
                "sort_by": "updated_at",
                "state": None,
            },
            "schema_version": CONTROL_CENTER_SCHEMA_VERSION,
            "total_count": 1,
        },
        "sales_credit_detail": {
            "current_evaluation": {
                "evaluation_id": EVALUATION_ID,
                "human_review_required": True,
                "material_sha256": "f" * 64,
                "rule_pack_version": "sc-rules/v1",
                "snapshot_id": "SYN-SNAPSHOT-M7-SC-CURRENT-0001",
            },
            "evidence": [
                {
                    "classification": "VERIFIED_PREORDER_EVIDENCE",
                    "evidence_id": "SYN-EVIDENCE-M7-SC-EVIDENCE-0001",
                    "interaction_id": "SYN-INTERACTION-M7-SC-0001",
                    "occurred_at": "2026-09-01T11:45:00Z",
                    "source_type": "SYNTHETIC_EMAIL",
                }
            ],
            "interactions": [
                {
                    "interaction_id": "SYN-INTERACTION-M7-SC-0001",
                    "recorded_at": "2026-09-01T11:45:00Z",
                    "source_ref_id": "SYN-EVIDENCE-M7-SC-SOURCE-0001",
                    "timestamp_precision": "EXACT",
                    "workflow_state": "VERIFIED_PREORDER_EVIDENCE",
                },
                {
                    "interaction_id": "SYN-INTERACTION-M7-SC-0002",
                    "recorded_at": "2026-09-01T11:50:00Z",
                    "source_ref_id": "SYN-EVIDENCE-M7-SC-SOURCE-0002",
                    "timestamp_precision": "EXACT",
                    "workflow_state": "OUTBOUND_EVIDENCE_HUMAN_REVIEW",
                },
            ],
            "manager_outcomes": [],
            "reason_codes": ["SC-RC-REVIEW"],
            "schema_version": CONTROL_CENTER_SCHEMA_VERSION,
            "search_runs": [
                {
                    "adapter_version": "synthetic-search-adapter/v1",
                    "completed_at": "2026-09-01T11:58:00Z",
                    "enumeration_complete": True,
                    "identifier_count": 2,
                    "run_id": "SYN-RUN-M7-SC-0001",
                    "started_at": "2026-09-01T11:57:00Z",
                    "terminal_outcome": "CANDIDATES_FOUND",
                    "trigger_type": "INITIAL",
                }
            ],
            "snapshots": [
                {
                    "captured_at": "2026-09-01T11:59:00Z",
                    "extraction_status": "VALID",
                    "is_current": True,
                    "lifecycle_status": "ACTIVE",
                    "line_count": 2,
                    "parser_version": "sales-credit-parser/v0",
                    "snapshot_id": "SYN-SNAPSHOT-M7-SC-CURRENT-0001",
                }
            ],
            "summary": sc_summary,
            "timeline": _timeline(),
        },
        "doi_queue": {
            "items": [doi_summary],
            "limit": 25,
            "offset": 0,
            "query": {
                "descending": True,
                "search": None,
                "sort_by": "updated_at",
                "state": None,
            },
            "schema_version": CONTROL_CENTER_SCHEMA_VERSION,
            "total_count": 1,
        },
        "doi_detail": {
            "current_attention_causes": [],
            "current_evaluation": {
                "evaluation_id": EVALUATION_ID,
                "input_domain": "doi-evaluation-input/v1",
                "input_sha256": "7" * 64,
                "output_domain": "doi-evaluation-output/v1",
                "output_sha256": "8" * 64,
                "run_id": "SYN-RUN-M7-DOI-0001",
                "snapshot_id": "SYN-SNAPSHOT-M7-DOI-0001",
                "top_level_state": "DOI_OPPORTUNITY",
                "transition_id": "TR-087",
            },
            "handling_flags": [],
            "human_fact_events": [],
            "interventions": [],
            "opportunities": _opportunities(),
            "reason_explanations": [
                {
                    "class": "BLOCK",
                    "code": "RC-087",
                    "description": (
                        "Potential opportunities address overlapping/mutually exclusive "
                        "merchandise scopes and no explicit scenario selection exists. "
                        "Keep opportunity values separate and overall potential UNAVAILABLE."
                    ),
                    "label": "POTENTIAL_OVERLAP_UNRESOLVED",
                    "registry_version": "synthetic-doi-reason-registry/v1.0.1",
                }
            ],
            "resulting_order_links": [],
            "retained_kpi_contributions": [],
            "schema_version": CONTROL_CENTER_SCHEMA_VERSION,
            "scenario_selection": None,
            "source_completeness": [
                {
                    "completeness_proof_present": True,
                    "completeness_sha256": "1" * 64,
                    "is_current": True,
                    "line_count": 2,
                    "order_id": ORDER_ID,
                    "record_domain": "doi-snapshot/v1",
                    "record_sha256": "2" * 64,
                    "relevant_line_count": 2,
                    "run_id": "SYN-RUN-M7-DOI-0001",
                    "snapshot_id": "SYN-SNAPSHOT-M7-DOI-0001",
                    "source_observed_at": "2026-09-01T11:59:00Z",
                }
            ],
            "summary": doi_summary,
            "timeline": [
                {
                    "event_id": EVALUATION_ID,
                    "event_kind": "EVALUATION",
                    "occurred_at": "2026-09-01T12:00:00Z",
                    "sequence": 1,
                    "state": "EVALUATION",
                    "transition_id": None,
                }
            ],
            "value_events": [],
        },
        "review": {
            "items": [
                {
                    "action_available": True,
                    "audit_subject_kind": "SALES_CREDIT_CASE",
                    "domain": "SALES_CREDIT",
                    "order_id": ORDER_ID,
                    "reason_codes": ["OUTBOUND_EVIDENCE_HUMAN_REVIEW"],
                    "required_action": "RECORD_MANAGER_OUTCOME",
                    "source_completeness_state": "COMPLETE_EVALUATION_RECORDED",
                    "subject_id": ORDER_ID,
                    "system_state": "OUTBOUND_EVIDENCE_HUMAN_REVIEW",
                }
            ],
            "schema_version": CONTROL_CENTER_SCHEMA_VERSION,
            "total_count": 1,
        },
        "audit": {
            "events": _timeline(),
            "schema_version": CONTROL_CENTER_SCHEMA_VERSION,
            "subject_id": ORDER_ID,
            "subject_kind": "SALES_CREDIT_CASE",
        },
        "system": {
            "api_request_schema_version": "synthetic-sales-assist-api-request/v1",
            "api_schema_version": "synthetic-sales-assist-api/v1",
            "application_schema_version": "synthetic-sales-assist-application/v1",
            "application_version": "0.1.2",
            "benchmark_reference": M4_BENCHMARK_REFERENCE.to_dict(),
            "build_version": "synthetic-sales-assist-m8/v1",
            "database": _database(),
            "dom_schema_version": "synthetic-sales-assist-dom/v1",
            "extension": _extension(),
            "network_policy": "LOOPBACK_ONLY_EXTERNAL_REQUESTS_ZERO",
            "owned_pid": 4242,
            "recent_safe_errors": [
                {
                    "category": "VALIDATION",
                    "code": "SAFE_VALIDATION_FAILURE",
                    "occurred_at": "2026-09-01T12:04:00Z",
                    "retryable": False,
                }
            ],
            "runtime_directory_class": "OWNED_LOCAL_RUNTIME_DIRECTORY",
            "schema_version": CONTROL_CENTER_SCHEMA_VERSION,
            "service_origin": "http://127.0.0.1:8765/",
            "service_status": "PASS",
        },
        "database": {
            "database": _database(),
            "schema_version": CONTROL_CENTER_SCHEMA_VERSION,
        },
        "backups": {
            "items": [_backup()],
            "schema_version": CONTROL_CENTER_SCHEMA_VERSION,
            "total_count": 1,
        },
        "telemetry": {
            "benchmark_reference": M4_BENCHMARK_REFERENCE.to_dict(),
            "denominator_registry": denominator_registry(),
            "metrics": _metrics(),
            "operational_status": _operational_status(),
            "schema_version": CONTROL_CENTER_SCHEMA_VERSION,
        },
        "extension": {
            "extension": _extension(),
            "schema_version": CONTROL_CENTER_SCHEMA_VERSION,
        },
    }


def _populated_doi_detail() -> dict[str, object]:
    view = _views()["doi_detail"]
    intervention_a = "SYN-EVIDENCE-M7-DOI-INTERVENTION-0001"
    intervention_b = "SYN-EVIDENCE-M7-DOI-INTERVENTION-0002"
    view["source_completeness"] = [
        {
            "completeness_proof_present": True,
            "completeness_sha256": "1" * 64,
            "is_current": True,
            "line_count": 2,
            "order_id": ORDER_ID,
            "record_domain": "doi-snapshot/v1",
            "record_sha256": "2" * 64,
            "relevant_line_count": 1,
            "run_id": "SYN-RUN-M7-DOI-0001",
            "snapshot_id": "SYN-SNAPSHOT-M7-DOI-0001",
            "source_observed_at": "2026-09-01T11:59:00Z",
        }
    ]
    view["handling_flags"] = ["COORDINATION_REQUIRED", "MANUAL_HANDLING"]
    view["summary"]["attention_causes"] = ["RECHECK_REQUIRED"]
    view["current_attention_causes"] = [
        {
            "cause_key": "SYN-EVIDENCE-M7-DOI-ATTENTION-CAUSE-0001",
            "condition": "RECHECK_REQUIRED",
            "current_event_id": "SYN-EVIDENCE-M7-DOI-ATTENTION-EVENT-0001",
            "current_event_occurred_at": "2026-09-01T12:00:01Z",
            "head_sha256": "3" * 64,
            "projection_state": "SET",
            "record_domain": "doi-owner-event-envelope/v1",
            "record_sha256": "4" * 64,
            "sequence": 1,
            "stream_id": "SYN-EVIDENCE-M7-DOI-ATTENTION-STREAM-0001",
        }
    ]
    view["opportunities"][0]["scope_components"] = [
        {
            "line_snapshot_id": "SYN-EVIDENCE-M7-DOI-LINE-0001",
            "ordinal": 1,
            "quantity_text": "2.000",
            "role": "AVAILABLE",
        }
    ]
    view["human_fact_events"] = [
        {
            "event_id": "SYN-EVIDENCE-M7-DOI-HUMAN-FACT-EVENT-0001",
            "occurred_at": "2026-09-01T12:00:02Z",
            "projection_state": "SCENARIO_SELECTED",
            "record_domain": "doi-owner-event-envelope/v1",
            "record_sha256": "5" * 64,
            "sequence": 1,
            "stream_id": "SYN-EVIDENCE-M7-DOI-HUMAN-FACT-STREAM-0001",
            "transition_id": "TR-087",
        }
    ]
    view["interventions"] = [
        {
            "action_occurred_at": "2026-09-01T12:01:00Z",
            "created_at": "2026-09-01T12:01:01Z",
            "head_sha256": "6" * 64,
            "intervention_id": intervention_a,
            "intervention_type": "FULFILLMENT_SPLIT",
            "opportunity_id": OPPORTUNITY_A,
            "projection_version": 1,
            "record_domain": "doi-intervention/v1",
            "record_sha256": "7" * 64,
            "status": "VERIFIED_ACTIVE",
            "verification_events": [
                {
                    "event_id": "SYN-EVIDENCE-M7-DOI-VERIFICATION-0001",
                    "occurrence_id": "SYN-INTERACTION-M7-DOI-VERIFICATION-0001",
                    "record_domain": "doi-action-verification/v1",
                    "record_sha256": "8" * 64,
                }
            ],
        },
        {
            "action_occurred_at": "2026-09-01T12:02:00Z",
            "created_at": "2026-09-01T12:02:01Z",
            "head_sha256": "9" * 64,
            "intervention_id": intervention_b,
            "intervention_type": "FULFILLMENT_SPLIT",
            "opportunity_id": OPPORTUNITY_B,
            "projection_version": 1,
            "record_domain": "doi-intervention/v1",
            "record_sha256": "a" * 64,
            "status": "VERIFIED_ACTIVE",
            "verification_events": [],
        },
    ]
    view["resulting_order_links"] = [
        {
            "child_order_id": "SYN-ORDER-M7-DOI-RESULT-0001",
            "current_revision": 2,
            "head_sha256": "b" * 64,
            "intervention_id": intervention_a,
            "link_id": "SYN-EVIDENCE-M7-DOI-LINK-0001",
            "parent_order_id": ORDER_ID,
            "revisions": [
                {
                    "mapping_components": [],
                    "predecessor_sha256": None,
                    "record_domain": "doi-resulting-order-link/v1",
                    "record_sha256": "c" * 64,
                    "revision": 1,
                    "revision_id": "SYN-EVIDENCE-M7-DOI-LINK-REVISION-0001",
                },
                {
                    "mapping_components": [
                        {
                            "child_line_id": "SYN-EVIDENCE-M7-DOI-CHILD-LINE-0001",
                            "ordinal": 1,
                            "parent_line_id": "SYN-EVIDENCE-M7-DOI-PARENT-LINE-0001",
                            "quantity_text": "2.000",
                        }
                    ],
                    "predecessor_sha256": "c" * 64,
                    "record_domain": "doi-resulting-order-link/v1",
                    "record_sha256": "d" * 64,
                    "revision": 2,
                    "revision_id": "SYN-EVIDENCE-M7-DOI-LINK-REVISION-0002",
                },
            ],
            "state": "AUTO_LINKED",
        }
    ]
    view["value_events"] = [
        {
            "amount_minor_units": 600,
            "currency_code": "USD",
            "currency_registry_version": "synthetic-iso-style-currency-registry/v1",
            "currency_scale": 2,
            "event_id": "SYN-EVIDENCE-M7-DOI-VALUE-0001",
            "event_type": "INITIAL_VERIFIED_VALUE",
            "intervention_id": intervention_a,
            "occurrence_id": "SYN-INTERACTION-M7-DOI-VALUE-0001",
            "predecessor_sha256": None,
            "record_domain": "doi-value-event/v1",
            "record_sha256": "e" * 64,
            "sequence": 1,
        },
        {
            "amount_minor_units": 700,
            "currency_code": "EUR",
            "currency_registry_version": "synthetic-iso-style-currency-registry/v1",
            "currency_scale": 2,
            "event_id": "SYN-EVIDENCE-M7-DOI-VALUE-0002",
            "event_type": "INITIAL_VERIFIED_VALUE",
            "intervention_id": intervention_b,
            "occurrence_id": "SYN-INTERACTION-M7-DOI-VALUE-0002",
            "predecessor_sha256": None,
            "record_domain": "doi-value-event/v1",
            "record_sha256": "f" * 64,
            "sequence": 1,
        },
    ]
    view["retained_kpi_contributions"] = [
        {
            "action_date": "2026-09-01",
            "amount_minor_units": 500,
            "currency_code": "USD",
            "currency_registry_version": "synthetic-iso-style-currency-registry/v1",
            "currency_scale": 2,
            "head_sha256": "1" * 64,
            "intervention_id": intervention_a,
            "intervention_type": "FULFILLMENT_SPLIT",
            "revision": 1,
        },
        {
            "action_date": "2026-09-01",
            "amount_minor_units": 800,
            "currency_code": "EUR",
            "currency_registry_version": "synthetic-iso-style-currency-registry/v1",
            "currency_scale": 2,
            "head_sha256": "2" * 64,
            "intervention_id": intervention_b,
            "intervention_type": "FULFILLMENT_SPLIT",
            "revision": 1,
        },
    ]
    return view


def _replace_path(
    view: dict[str, object],
    path: tuple[str | int, ...],
    value: object,
) -> None:
    current: object = view
    for member in path[:-1]:
        if type(current) is dict and type(member) is str:
            current = current[member]
        elif type(current) is list and type(member) is int:
            current = current[member]
        else:
            raise AssertionError("invalid test mutation path")
    final = path[-1]
    if type(current) is dict and type(final) is str:
        current[final] = value
        return
    if type(current) is list and type(final) is int:
        current[final] = value
        return
    raise AssertionError("invalid test mutation target")


class _AccessibilityParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.h1_count = 0
        self.main_count = 0
        self.primary_navigation = 0
        self.status_landmarks = 0
        self.caption_count = 0
        self.table_count = 0
        self.th_without_scope = 0
        self.inline_violations: list[str] = []
        self.remote_attributes: list[str] = []
        self.script_depth = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        values = dict(attrs)
        if tag == "h1":
            self.h1_count += 1
        if tag == "main":
            self.main_count += 1
        if tag == "nav" and values.get("aria-label") == "Primary":
            self.primary_navigation += 1
        if values.get("role") == "status":
            self.status_landmarks += 1
        if tag == "caption":
            self.caption_count += 1
        if tag == "table":
            self.table_count += 1
        if tag == "th" and values.get("scope") != "col":
            self.th_without_scope += 1
        if tag == "style":
            self.inline_violations.append("style-element")
        if tag == "script":
            self.script_depth += 1
            if not values.get("src"):
                self.inline_violations.append("script-source")
        for name, value in attrs:
            lowered = name.casefold()
            if lowered == "style" or lowered.startswith("on"):
                self.inline_violations.append(lowered)
            if value and lowered in {"href", "src", "action"}:
                if "://" in value or value.startswith(("//", "data:", "javascript:")):
                    self.remote_attributes.append(value)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self.script_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.script_depth and data.strip():
            self.inline_violations.append("inline-script")


class DashboardRenderingTests(unittest.TestCase):
    def _assert_mutations_rejected(
        self,
        route: str,
        mutations: tuple[
            tuple[str, Callable[[dict[str, object]], None]],
            ...,
        ],
    ) -> None:
        for label, mutation in mutations:
            with self.subTest(route=route, mutation=label):
                view = _views()[route]
                mutation(view)
                with self.assertRaises(PortalContractError):
                    render_dashboard_page(route, view, CSRF)

    def test_every_dashboard_page_has_accessible_static_structure(self) -> None:
        for route, view in _views().items():
            with self.subTest(route=route):
                raw = render_dashboard_page(route, view, CSRF)
                self.assertTrue(raw.startswith(b"<!" + b"doctype html>\n<!--"))
                text = raw.decode("utf-8")
                parser = _AccessibilityParser()
                parser.feed(text)
                self.assertEqual(parser.h1_count, 1)
                self.assertEqual(parser.main_count, 1)
                self.assertEqual(parser.primary_navigation, 1)
                self.assertGreaterEqual(parser.status_landmarks, 1)
                self.assertEqual(parser.caption_count, parser.table_count)
                self.assertEqual(parser.th_without_scope, 0)
                self.assertEqual(parser.inline_violations, [])
                self.assertEqual(parser.remote_attributes, [])
                self.assertIn('href="#ssa-dashboard-main"', text)
                self.assertIn(
                    f'data-ssa-dashboard-schema-version="{DASHBOARD_DOM_VERSION}"',
                    text,
                )
                self.assertNotIn("C:\\Users\\", text)
                self.assertNotIn("<style", text)

    def test_human_action_forms_are_explicit_confirmed_and_closed(self) -> None:
        views = _views()
        sales_credit = render_dashboard_page(
            "sales_credit_detail",
            views["sales_credit_detail"],
            CSRF,
        ).decode("utf-8")
        self.assertIn('data-ssa-dashboard-action="manager-outcome"', sales_credit)
        self.assertIn('name="confirmed"', sales_credit)
        self.assertIn('name="request_key"', sales_credit)
        self.assertIn('name="decided_at"', sales_credit)
        for outcome in ("APPROVED", "DENIED", "PARTIAL", "OTHER_REP", "NOT_PURSUED"):
            self.assertIn(f'value="{outcome}"', sales_credit)
        doi = render_dashboard_page(
            "doi_detail",
            views["doi_detail"],
            CSRF,
        ).decode("utf-8")
        self.assertIn('data-ssa-dashboard-action="doi-scenario-selection"', doi)
        self.assertIn('name="evaluation_id"', doi)
        self.assertIn('name="selected_opportunity_id"', doi)
        self.assertEqual(doi.count('name="option_opportunity_ids"'), 2)
        self.assertIn('name="occurred_at"', doi)
        self.assertIn("creates no intervention", doi)

    def test_action_form_transport_preserves_exact_null_and_array_members(self) -> None:
        views = _views()
        sales_credit = render_dashboard_page(
            "sales_credit_detail",
            views["sales_credit_detail"],
            CSRF,
        ).decode("utf-8")
        self.assertEqual(sales_credit.count('data-ssa-optional="true"'), 2)
        self.assertIn(
            'name="amount_minor_units" data-ssa-value-type="integer" '
            'data-ssa-optional="true"',
            sales_credit,
        )
        self.assertIn('name="currency_code" data-ssa-optional="true"', sales_credit)
        empty_branch = 'if (optional && value === "") {'
        self.assertIn(empty_branch, DASHBOARD_JS)
        self.assertIn("payload[control.name] = null;", DASHBOARD_JS)
        self.assertLess(
            DASHBOARD_JS.index(empty_branch),
            DASHBOARD_JS.index('if (valueType === "integer")'),
        )
        self.assertIn("const integerValue = Number(value);", DASHBOARD_JS)
        self.assertIn("const jsonSafeIntegerMaximum = 9007199254740991;", DASHBOARD_JS)
        self.assertIn("Number.isSafeInteger(integerValue)", DASHBOARD_JS)
        self.assertIn("payload[control.name] = integerValue;", DASHBOARD_JS)
        self.assertLess(
            DASHBOARD_JS.index("Number.isSafeInteger(integerValue)"),
            DASHBOARD_JS.index("payload[control.name] = integerValue;"),
        )
        self.assertIn("payload[control.name] = value;", DASHBOARD_JS)

        doi = render_dashboard_page(
            "doi_detail",
            views["doi_detail"],
            CSRF,
        ).decode("utf-8")
        option_a = (
            f'<input type="hidden" name="option_opportunity_ids" value="{OPPORTUNITY_A}" '
            'data-ssa-value-type="array">'
        )
        option_b = (
            f'<input type="hidden" name="option_opportunity_ids" value="{OPPORTUNITY_B}" '
            'data-ssa-value-type="array">'
        )
        self.assertIn(option_a, doi)
        self.assertIn(option_b, doi)
        self.assertLess(doi.index(option_a), doi.index(option_b))
        self.assertEqual(doi.count('data-ssa-value-type="array"'), 2)
        self.assertIn("payload[control.name] = [];", DASHBOARD_JS)
        self.assertIn("payload[control.name].push(value);", DASHBOARD_JS)

    def test_populated_doi_detail_renders_governed_evidence_in_plain_order(self) -> None:
        text = render_dashboard_page(
            "doi_detail",
            _populated_doi_detail(),
            CSRF,
        ).decode("utf-8")
        ordered_headings = (
            "Required human action",
            "Source completeness",
            "Current opportunities and exact scope",
            "Handling flags and current attention",
            "Human facts",
            "Interventions and verification",
            "Resulting-order links",
            "Value and KPI history by currency",
            "Immutable timeline",
        )
        positions = [text.index(heading) for heading in ordered_headings]
        self.assertEqual(positions, sorted(positions))
        for selector in (
            "doi-reason-explanations",
            "doi-source-completeness",
            "doi-opportunity-scope",
            "doi-handling-flags",
            "doi-current-attention-causes",
            "doi-human-fact-events",
            "doi-interventions",
            "doi-intervention-verifications",
            "doi-resulting-order-links",
            "doi-resulting-order-link-revisions",
            "doi-resulting-order-line-mappings",
            "doi-value-events-eur",
            "doi-value-events-usd",
            "doi-retained-kpi-eur",
            "doi-retained-kpi-usd",
        ):
            self.assertIn(f'data-ssa-dashboard-table="{selector}"', text)
        for amount in ("6.00 USD", "7.00 EUR", "5.00 USD", "8.00 EUR"):
            self.assertIn(amount, text)
        self.assertIn("no mixed-currency total", text)
        self.assertIn("2.000", text)
        self.assertNotIn("record_payload", text)
        self.assertNotIn("projection_payload", text)

    def test_detail_explanations_humanize_states_and_retain_exact_codes(self) -> None:
        views = _views()
        sales_credit = render_dashboard_page(
            "sales_credit_detail",
            views["sales_credit_detail"],
            CSRF,
        ).decode("utf-8")
        self.assertIn("Target rep", sales_credit)
        self.assertIn("exact code <code>TARGET_REP</code>", sales_credit)
        self.assertIn("Outbound evidence human review", sales_credit)
        self.assertIn("<code>OUTBOUND_EVIDENCE_HUMAN_REVIEW</code>", sales_credit)
        doi = render_dashboard_page(
            "doi_detail",
            views["doi_detail"],
            CSRF,
        ).decode("utf-8")
        self.assertIn("DOI opportunity", doi)
        self.assertIn("exact code <code>DOI_OPPORTUNITY</code>", doi)
        self.assertIn("Registry labels and descriptions", doi)
        self.assertIn("Potential overlap unresolved", doi)
        self.assertIn("Keep opportunity values separate", doi)
        self.assertIn("RC-087", doi)

    def test_empty_doi_detail_histories_have_explicit_safe_empty_states(self) -> None:
        text = render_dashboard_page(
            "doi_detail",
            _views()["doi_detail"],
            CSRF,
        ).decode("utf-8")
        for message in (
            "No current handling flag is recorded.",
            "No current unresolved attention cause is recorded.",
            "No DOI human fact has been recorded for this case.",
            "No intervention has been recorded for this case.",
            "No resulting-order link has been recorded for this case.",
            "No verified value event has been recorded for this case.",
            "No retained verified KPI contribution is currently recorded.",
        ):
            self.assertIn(message, text)

    def test_doi_detail_additive_contract_fails_closed_on_invalid_evidence(self) -> None:
        def add_member(view: dict[str, object]) -> None:
            source = view["source_completeness"][0]
            source["raw_payload"] = "prohibited"

        def uppercase_hash(view: dict[str, object]) -> None:
            view["current_attention_causes"][0]["head_sha256"] = "A" * 64

        def noncanonical_timestamp(view: dict[str, object]) -> None:
            view["human_fact_events"][0]["occurred_at"] = "2026-09-01 12:00:02"

        def wrong_money_binding(view: dict[str, object]) -> None:
            view["value_events"][0]["currency_scale"] = 3

        def wrong_identity_namespace(view: dict[str, object]) -> None:
            view["interventions"][0]["intervention_id"] = ORDER_ID

        def private_record_domain(view: dict[str, object]) -> None:
            view["interventions"][0]["record_domain"] = "C:\\Users\\private"

        def mismatched_source_order(view: dict[str, object]) -> None:
            view["source_completeness"][0]["order_id"] = "SYN-ORDER-M7-OTHER-0001"

        def incoherent_line_counts(view: dict[str, object]) -> None:
            view["source_completeness"][0]["relevant_line_count"] = 3

        mutations = (
            add_member,
            uppercase_hash,
            noncanonical_timestamp,
            wrong_money_binding,
            wrong_identity_namespace,
            private_record_domain,
            mismatched_source_order,
            incoherent_line_counts,
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation.__name__):
                view = _populated_doi_detail()
                mutation(view)
                with self.assertRaises(PortalContractError):
                    render_dashboard_page("doi_detail", view, CSRF)

    def test_action_feedback_remains_visible_and_forms_are_resubmittable(self) -> None:
        self.assertNotIn("window.location.reload", DASHBOARD_JS)
        self.assertNotIn("form.reset", DASHBOARD_JS)
        self.assertIn(
            "Exact replay: the original receipt was returned and no new event was created.",
            DASHBOARD_JS,
        )
        self.assertIn(
            "Local synthetic action recorded. Use the refresh link to view the new projection.",
            DASHBOARD_JS,
        )
        self.assertEqual(
            DASHBOARD_JS.count("if (button) button.disabled = false;"),
            2,
        )

    def test_action_forms_have_explicit_current_projection_refresh_links(self) -> None:
        views = _views()
        cases = (
            (
                "sales_credit_detail",
                views["sales_credit_detail"],
                f'<a href="/sales-credit/{ORDER_ID}">Refresh current projection</a>',
            ),
            (
                "doi_detail",
                views["doi_detail"],
                f'<a href="/doi/{CASE_ID}">Refresh current projection</a>',
            ),
            (
                "database",
                views["database"],
                '<a href="/system/database">Refresh database verification</a>',
            ),
            (
                "backups",
                views["backups"],
                '<a href="/system/backups">Refresh backup receipts</a>',
            ),
        )
        for route, view, expected in cases:
            with self.subTest(route=route):
                text = render_dashboard_page(route, view, CSRF).decode("utf-8")
                self.assertIn(expected, text)

    def test_queue_filters_and_pagination_match_closed_server_query(self) -> None:
        views = _views()
        expected_common = (
            '<input type="hidden" name="page" value="1">',
            'name="q" value="" maxlength="96"',
            '<select name="state">',
            '<select name="direction">',
            '<option value="desc"',
            '<option value="asc"',
            '<select name="page_size">',
            '<option value="10"',
            '<option value="25"',
            '<option value="50"',
        )
        expected_sorts = {
            "sales_credit_queue": ("order_id", "workflow_state", "updated_at"),
            "doi_queue": ("case_id", "order_id", "updated_at", "doi_state"),
        }
        for route, sort_values in expected_sorts.items():
            with self.subTest(route=route):
                text = render_dashboard_page(route, views[route], CSRF).decode("utf-8")
                for expected in expected_common:
                    self.assertIn(expected, text)
                for value in sort_values:
                    self.assertIn(f'<option value="{value}"', text)
                for obsolete in (
                    'name="search"',
                    'name="sort_by"',
                    'name="limit"',
                    'name="offset"',
                    'value="ascending"',
                    'value="descending"',
                    '<option value="100">',
                ):
                    self.assertNotIn(obsolete, text)

        middle = _views()["sales_credit_queue"]
        middle["limit"] = 25
        middle["offset"] = 25
        middle["total_count"] = 60
        text = render_dashboard_page("sales_credit_queue", middle, CSRF).decode("utf-8")
        self.assertIn(
            "/sales-credit?sort=updated_at&amp;direction=desc&amp;page=1&amp;page_size=25",
            text,
        )
        self.assertIn(
            "/sales-credit?sort=updated_at&amp;direction=desc&amp;page=3&amp;page_size=25",
            text,
        )
        self.assertIn("Showing 26–50 of 60", text)

        last = _views()["sales_credit_queue"]
        last["limit"] = 25
        last["offset"] = 50
        last["total_count"] = 60
        text = render_dashboard_page("sales_credit_queue", last, CSRF).decode("utf-8")
        self.assertIn("Showing 51–60 of 60", text)

    def test_queue_controls_and_links_preserve_locked_query_projection(self) -> None:
        view = _views()["sales_credit_queue"]
        view["limit"] = 50
        view["offset"] = 50
        view["total_count"] = 120
        view["query"] = {
            "descending": False,
            "search": ORDER_ID,
            "sort_by": "workflow_state",
            "state": "OUTBOUND_EVIDENCE_HUMAN_REVIEW",
        }
        text = render_dashboard_page(
            "sales_credit_queue",
            view,
            CSRF,
            presentation=True,
        ).decode("utf-8")
        self.assertIn(f'name="q" value="{ORDER_ID}" maxlength="96"', text)
        self.assertIn(
            '<option value="OUTBOUND_EVIDENCE_HUMAN_REVIEW" selected>',
            text,
        )
        self.assertIn('<option value="workflow_state" selected>', text)
        self.assertIn('<option value="asc" selected>Ascending</option>', text)
        self.assertIn('<option value="50" selected>50</option>', text)
        self.assertIn('<input type="hidden" name="page" value="1">', text)
        self.assertIn('<input type="hidden" name="presentation" value="1">', text)
        expected_prefix = (
            f"/sales-credit?q={ORDER_ID}&amp;state=OUTBOUND_EVIDENCE_HUMAN_REVIEW"
            "&amp;sort=workflow_state&amp;direction=asc"
        )
        self.assertIn(
            expected_prefix + "&amp;page=1&amp;page_size=50&amp;presentation=1",
            text,
        )
        self.assertIn(
            expected_prefix + "&amp;page=3&amp;page_size=50&amp;presentation=1",
            text,
        )

    def test_queue_query_injection_fails_closed(self) -> None:
        mutations = (
            ("search", "SYN-ORDER-X&amp;state=MANUAL_REVIEW_REQUIRED"),
            ("state", "DOI_OPPORTUNITY"),
            ("sort_by", "updated_at;drop"),
            ("descending", "false"),
        )
        for member, value in mutations:
            with self.subTest(member=member):
                view = _views()["sales_credit_queue"]
                view["query"][member] = value
                with self.assertRaises(PortalContractError):
                    render_dashboard_page("sales_credit_queue", view, CSRF)

    def test_out_of_range_empty_queue_page_is_truthful_and_recoverable(self) -> None:
        view = _views()["doi_queue"]
        view["items"] = []
        view["offset"] = 75
        view["total_count"] = 60
        text = render_dashboard_page("doi_queue", view, CSRF).decode("utf-8")
        self.assertIn("No results on requested page 4; 60 total.", text)
        self.assertIn(
            "/doi?sort=updated_at&amp;direction=desc&amp;page=3&amp;page_size=25",
            text,
        )

    def test_queue_view_rejects_server_incompatible_pagination(self) -> None:
        for limit, offset in ((20, 0), (25, 13)):
            with self.subTest(limit=limit, offset=offset):
                view = _views()["sales_credit_queue"]
                view["limit"] = limit
                view["offset"] = offset
                with self.assertRaisesRegex(
                    PortalContractError,
                    "DASHBOARD_SC_QUEUE_INVALID_PAGINATION",
                ):
                    render_dashboard_page("sales_credit_queue", view, CSRF)

    def test_partial_manager_outcome_money_is_currency_exact(self) -> None:
        view = _views()["sales_credit_detail"]
        view["summary"]["manager_outcome"] = "PARTIAL"
        view["summary"]["unresolved_human_review"] = False
        view["manager_outcomes"] = [
            {
                "actor_id": "SYN-REP-M2-MANAGER-0001",
                "amount_minor_units": 1250,
                "currency_code": "USD",
                "currency_registry_version": (
                    "synthetic-iso-style-currency-registry/v1"
                ),
                "currency_scale": 2,
                "decided_at": "2026-09-01T12:01:00Z",
                "occurrence_id": "SYN-EVIDENCE-M7-OUTCOME-0001",
                "outcome": "PARTIAL",
            }
        ]
        text = render_dashboard_page(
            "sales_credit_detail",
            view,
            CSRF,
        ).decode("utf-8")
        self.assertIn("Exact approved amount / currency", text)
        self.assertIn("12.50 USD", text)

    def test_sales_credit_retained_detail_is_closed_bound_and_read_only(self) -> None:
        text = render_dashboard_page(
            "sales_credit_detail",
            _views()["sales_credit_detail"],
            CSRF,
        ).decode("utf-8")
        for selector in (
            "sales-credit-snapshots",
            "sales-credit-search-runs",
            "sales-credit-interactions",
            "sales-credit-evidence",
        ):
            self.assertIn(f'data-ssa-dashboard-table="{selector}"', text)
        for retained in (
            "SYN-SNAPSHOT-M7-SC-CURRENT-0001",
            "SYN-RUN-M7-SC-0001",
            "SYN-INTERACTION-M7-SC-0001",
            "SYN-EVIDENCE-M7-SC-EVIDENCE-0001",
            "sales-credit-parser/v0",
            "synthetic-search-adapter/v1",
        ):
            self.assertIn(retained, text)
        self.assertNotIn("canonical_bytes", text)
        self.assertNotIn("normalized_value", text)

        def extra_evaluation_member(view: dict[str, object]) -> None:
            view["current_evaluation"]["raw_payload"] = "prohibited"

        def uppercase_material_hash(view: dict[str, object]) -> None:
            view["current_evaluation"]["material_sha256"] = "A" * 64

        def unbound_current_snapshot(view: dict[str, object]) -> None:
            view["snapshots"][0]["is_current"] = False

        def unbound_evidence_interaction(view: dict[str, object]) -> None:
            view["evidence"][0]["interaction_id"] = (
                "SYN-INTERACTION-M7-SC-UNBOUND-0001"
            )

        def invalid_parser_version(view: dict[str, object]) -> None:
            view["snapshots"][0]["parser_version"] = "C:\\Users\\private"

        for mutation in (
            extra_evaluation_member,
            uppercase_material_hash,
            unbound_current_snapshot,
            unbound_evidence_interaction,
            invalid_parser_version,
        ):
            with self.subTest(mutation=mutation.__name__):
                view = _views()["sales_credit_detail"]
                mutation(view)
                with self.assertRaises(PortalContractError):
                    render_dashboard_page("sales_credit_detail", view, CSRF)

    def test_doi_locked_detail_bindings_and_selected_scenario_render(self) -> None:
        selected = _views()["doi_detail"]
        selected["summary"]["aggregate_potential_state"] = "AVAILABLE"
        selected["summary"]["scenario_selection_state"] = "SELECTED"
        selected["scenario_selection"] = {
            "option_opportunity_ids": [OPPORTUNITY_A, OPPORTUNITY_B],
            "selected_opportunity_id": OPPORTUNITY_A,
            "selection_id": "SYN-EVIDENCE-M7-DOI-SELECTION-0001",
        }
        text = render_dashboard_page("doi_detail", selected, CSRF).decode("utf-8")
        self.assertIn('data-ssa-dashboard-evidence="doi-evaluation-binding"', text)
        self.assertIn('data-ssa-dashboard-evidence="doi-scenario-selection"', text)
        self.assertIn("SYN-EVIDENCE-M7-DOI-SELECTION-0001", text)
        self.assertIn("Potential overlap unresolved", text)
        self.assertNotIn('data-ssa-dashboard-action="doi-scenario-selection"', text)

        def wrong_registry_description(view: dict[str, object]) -> None:
            view["reason_explanations"][0]["description"] = "Synthetic but ungoverned."

        def uppercase_input_hash(view: dict[str, object]) -> None:
            view["current_evaluation"]["input_sha256"] = "A" * 64

        def mismatched_evaluation_state(view: dict[str, object]) -> None:
            view["current_evaluation"]["top_level_state"] = "DOI_MONITOR"

        def invalid_scope_sequence(view: dict[str, object]) -> None:
            view["opportunities"][0]["scope_components"] = [
                {
                    "line_snapshot_id": "SYN-EVIDENCE-M7-DOI-LINE-0001",
                    "ordinal": 2,
                    "quantity_text": "2",
                    "role": "AVAILABLE",
                }
            ]

        def unexpected_selection(view: dict[str, object]) -> None:
            view["scenario_selection"] = {
                "option_opportunity_ids": [OPPORTUNITY_A, OPPORTUNITY_B],
                "selected_opportunity_id": OPPORTUNITY_A,
                "selection_id": "SYN-EVIDENCE-M7-DOI-SELECTION-0001",
            }

        for mutation in (
            wrong_registry_description,
            uppercase_input_hash,
            mismatched_evaluation_state,
            invalid_scope_sequence,
            unexpected_selection,
        ):
            with self.subTest(mutation=mutation.__name__):
                view = _views()["doi_detail"]
                mutation(view)
                with self.assertRaises(PortalContractError):
                    render_dashboard_page("doi_detail", view, CSRF)

    def test_evaluation_audit_and_doi_proof_hash_events_are_governed(self) -> None:
        evaluation = {
            "events": [
                {
                    "event_id": EVALUATION_ID,
                    "event_kind": "EVALUATION_RECORDED",
                    "occurred_at": "2026-09-01T12:00:00Z",
                    "sequence": 1,
                    "state": "DOI_OPPORTUNITY",
                    "transition_id": None,
                }
            ],
            "schema_version": CONTROL_CENTER_SCHEMA_VERSION,
            "subject_id": EVALUATION_ID,
            "subject_kind": "EVALUATION",
        }
        text = render_dashboard_page("audit", evaluation, CSRF).decode("utf-8")
        self.assertIn('data-ssa-dashboard-timeline="EVALUATION"', text)

        doi = _views()["doi_detail"]
        doi["timeline"].insert(
            0,
            {
                "event_id": "9" * 64,
                "event_kind": "COMPLETENESS_PROOF",
                "occurred_at": "2026-09-01T11:59:00Z",
                "sequence": 0,
                "state": "COMPLETENESS_PROOF",
                "transition_id": None,
            },
        )
        rendered = render_dashboard_page("doi_detail", doi, CSRF).decode("utf-8")
        self.assertIn("9" * 64, rendered)

    def test_unsupported_high_authority_controls_are_absent(self) -> None:
        doi = render_dashboard_page(
            "doi_detail",
            _views()["doi_detail"],
            CSRF,
        ).decode("utf-8")
        for action in (
            "resolve-attention",
            "verify-intervention",
            "link-resulting-order",
            "append-value",
            "generic-human-fact",
        ):
            self.assertNotIn(f'data-ssa-dashboard-action="{action}"', doi)
        system = render_dashboard_page(
            "system",
            _views()["system"],
            CSRF,
        ).decode("utf-8")
        self.assertNotIn('data-ssa-dashboard-action="restore"', system)
        self.assertNotIn('data-ssa-dashboard-action="reset"', system)

    def test_current_projection_history_and_currency_labels_are_explicit(self) -> None:
        views = _views()
        overview = render_dashboard_page("overview", views["overview"], CSRF).decode(
            "utf-8"
        )
        self.assertIn("Current projections versus immutable history", overview)
        self.assertIn("History receipts; not new evaluations", overview)
        telemetry = render_dashboard_page(
            "telemetry",
            views["telemetry"],
            CSRF,
        ).decode("utf-8")
        self.assertIn("12.50 USD", telemetry)
        self.assertIn("unresolved overlap", telemetry)
        self.assertIn("empty denominator displays N/A", telemetry)
        self.assertIn("Numerator", telemetry)
        self.assertIn("Denominator", telemetry)

    def test_system_and_telemetry_render_closed_operational_evidence(self) -> None:
        views = _views()
        system = render_dashboard_page("system", views["system"], CSRF).decode("utf-8")
        telemetry = render_dashboard_page(
            "telemetry",
            views["telemetry"],
            CSRF,
        ).decode("utf-8")
        for text in (system, telemetry):
            self.assertIn("synthetic-sales-assist-milestone4-benchmark/v1", text)
            self.assertIn("226.490150", text)
            self.assertIn("545.652600", text)
            self.assertIn("4.409734", text)
            self.assertIn("SYN-EVIDENCE-RESTORE-M7-0001", text)
            self.assertIn("2026-09-01T12:06:00Z", text)
            self.assertNotIn("canonical_bytes", text)
            self.assertNotIn("C:\\Users\\", text)
        self.assertIn("SAFE_VALIDATION_FAILURE", system)
        self.assertIn("no raw payload, stack trace, or path", system)
        self.assertIn("Database-error requests", telemetry)
        self.assertIn("Closed result and current-projection distributions", telemetry)
        self.assertIn("Terminal request result", telemetry)
        self.assertIn("Delta from M4 benchmark reference", telemetry)
        self.assertIn("-78573568", telemetry)

    def test_all_five_extension_states_render_truthfully(self) -> None:
        now = datetime.now(timezone.utc)
        fresh = (now - timedelta(seconds=1)).isoformat(timespec="microseconds")
        stale = (now - timedelta(seconds=301)).isoformat(timespec="microseconds")
        fresh = fresh.replace("+00:00", "Z")
        stale = stale.replace("+00:00", "Z")
        for state in (
            "EXPECTED_PACKAGE_ONLY",
            "LAST_SEEN_HEALTHY",
            "LAST_SEEN_STALE",
            "VERSION_MISMATCH",
            "UNKNOWN",
        ):
            view = _views()["extension"]
            extension = dict(view["extension"])
            extension["state"] = state
            if state != "EXPECTED_PACKAGE_ONLY":
                extension["last_seen_at"] = (
                    stale if state == "LAST_SEEN_STALE" else fresh
                )
                extension["observed_version"] = (
                    "0.2.0" if state == "VERSION_MISMATCH" else "0.1.2"
                )
            if state == "UNKNOWN":
                extension["last_seen_at"] = None
                extension["observed_version"] = None
            view["extension"] = extension
            text = render_dashboard_page("extension", view, CSRF).decode("utf-8")
            self.assertIn(state, text)
            self.assertIn("Package presence is not installation evidence", text)

    def test_doi_run_audit_accepts_only_governed_hash_event_identity(self) -> None:
        run_id = "SYN-RUN-M7-AUDIT-0001"
        record_sha256 = "e" * 64
        view = {
            "events": [
                {
                    "event_id": record_sha256,
                    "event_kind": "RUN_STARTED",
                    "occurred_at": "2026-09-01T12:00:00Z",
                    "sequence": 1,
                    "state": "RUN_STARTED",
                    "transition_id": None,
                }
            ],
            "schema_version": CONTROL_CENTER_SCHEMA_VERSION,
            "subject_id": run_id,
            "subject_kind": "DOI_RUN",
        }
        text = render_dashboard_page("audit", view, CSRF).decode("utf-8")
        self.assertIn(record_sha256, text)
        view["subject_kind"] = "DOI_CASE"
        with self.assertRaisesRegex(
            PortalContractError,
            "DASHBOARD_AUDIT_SUBJECT_INVALID",
        ):
            render_dashboard_page("audit", view, CSRF)

    def test_escaping_closed_members_and_private_paths_fail_closed(self) -> None:
        view = _views()["sales_credit_detail"]
        view["reason_codes"] = ["RC-&lt;-<script>"]
        with self.assertRaisesRegex(
            PortalContractError,
            "DASHBOARD_SC_REASON_INVALID",
        ):
            render_dashboard_page("sales_credit_detail", view, CSRF)
        private = _views()["database"]
        database = dict(private["database"])
        database["database_location_class"] = "C:\\Users\\person\\private.sqlite3"
        private["database"] = database
        with self.assertRaisesRegex(
            PortalContractError,
            "DASHBOARD_PRIVATE_PATH_PROHIBITED",
        ):
            render_dashboard_page("database", private, CSRF)

    def test_wrong_shape_version_route_and_csrf_fail_closed(self) -> None:
        view = _views()["overview"]
        view["extra"] = "not closed"
        with self.assertRaises(PortalContractError):
            render_dashboard_page("overview", view, CSRF)
        with self.assertRaises(PortalContractError):
            render_dashboard_page("not-a-route", {}, CSRF)
        with self.assertRaises(PortalContractError):
            render_dashboard_page("overview", _views()["overview"], "short")

    def test_presentation_mode_is_machine_readable_and_privacy_safe(self) -> None:
        text = render_dashboard_page(
            "system",
            _views()["system"],
            CSRF,
            presentation=True,
        ).decode("utf-8")
        self.assertIn('data-ssa-dashboard-presentation="true"', text)
        self.assertIn("LOCAL_FILESYSTEM", text)
        self.assertNotIn("C:\\Users\\", text)

    def test_system_origin_accepts_only_exact_loopback_http_authority(self) -> None:
        http_scheme = "http" + "://"
        https_scheme = "https" + "://"
        for origin in (
            https_scheme + "127.0.0.1:8765/",
            http_scheme + "example.invalid:8765/",
            http_scheme + "user" + "@" + "127.0.0.1:8765/",
            http_scheme + "127.0.0.1:8765/?next=elsewhere",
            http_scheme + "127.0.0.1:99999/",
            "\\\\server\\share",
        ):
            with self.subTest(origin=origin):
                view = _views()["system"]
                view["service_origin"] = origin
                with self.assertRaisesRegex(
                    PortalContractError,
                    "DASHBOARD_PRIVATE_PATH_PROHIBITED",
                ):
                    render_dashboard_page("system", view, CSRF)

    def test_overview_semantic_mutations_fail_closed(self) -> None:
        failed_service = _views()["overview"]
        _replace_path(failed_service, ("system", "service_status"), "FAIL")
        render_dashboard_page("overview", failed_service, CSRF)

        self._assert_mutations_rejected(
            "overview",
            (
                (
                    "requests-received-type",
                    lambda view: _replace_path(
                        view,
                        ("metrics", "requests_received"),
                        {"count": 3},
                    ),
                ),
                (
                    "reconciliation-type",
                    lambda view: _replace_path(
                        view,
                        ("reconciliation", "active_doi_cases"),
                        "1",
                    ),
                ),
                (
                    "reconciliation-count-mismatch",
                    lambda view: _replace_path(
                        view,
                        ("reconciliation", "unique_evaluations"),
                        1,
                    ),
                ),
                (
                    "database-status",
                    lambda view: _replace_path(
                        view,
                        ("system", "database_status"),
                        "TRUST_ME",
                    ),
                ),
                (
                    "service-database-coherence",
                    lambda view: _replace_path(
                        view,
                        ("system", "database_status"),
                        "UNHEALTHY",
                    ),
                ),
                (
                    "active-sales-credit-without-history",
                    lambda view: _replace_path(
                        view,
                        ("reconciliation", "sales_credit_history_events"),
                        0,
                    ),
                ),
                (
                    "active-doi-without-history",
                    lambda view: _replace_path(
                        view,
                        ("reconciliation", "doi_history_events"),
                        0,
                    ),
                ),
                (
                    "extension-status",
                    lambda view: _replace_path(
                        view,
                        ("system", "extension_status"),
                        "INSTALLED",
                    ),
                ),
            ),
        )

    def test_review_domain_and_authority_mutations_fail_closed(self) -> None:
        def closed_sales_credit_review(view: dict[str, object]) -> None:
            _replace_path(view, ("items", 0, "system_state"), "CLOSED")
            _replace_path(view, ("items", 0, "reason_codes"), ["CLOSED"])

        def duplicate_review_subject(view: dict[str, object]) -> None:
            items = view["items"]
            assert type(items) is list and type(items[0]) is dict
            items.append(dict(items[0]))
            view["total_count"] = 2

        def unevaluated_doi_overlap_action(view: dict[str, object]) -> None:
            view["items"] = [
                {
                    "action_available": True,
                    "audit_subject_kind": "DOI_CASE",
                    "domain": "DOI",
                    "order_id": ORDER_ID,
                    "reason_codes": ["RC-087"],
                    "required_action": "SELECT_OVERLAP_SCENARIO",
                    "source_completeness_state": "COMPLETE_EVALUATION_RECORDED",
                    "subject_id": CASE_ID,
                    "system_state": "UNEVALUATED",
                }
            ]

        self._assert_mutations_rejected(
            "review",
            (
                (
                    "boolean-string",
                    lambda view: _replace_path(
                        view,
                        ("items", 0, "action_available"),
                        "false",
                    ),
                ),
                (
                    "wrong-subject-namespace",
                    lambda view: _replace_path(
                        view,
                        ("items", 0, "subject_id"),
                        "SYN-SNAPSHOT-M7-WRONG-SUBJECT-0001",
                    ),
                ),
                (
                    "source-state",
                    lambda view: _replace_path(
                        view,
                        ("items", 0, "source_completeness_state"),
                        "COMPLETE",
                    ),
                ),
                (
                    "authority-action",
                    lambda view: _replace_path(
                        view,
                        ("items", 0, "required_action"),
                        "SELECT_OVERLAP_SCENARIO",
                    ),
                ),
                (
                    "reason-state-binding",
                    lambda view: _replace_path(
                        view,
                        ("items", 0, "reason_codes"),
                        ["MANUAL_REVIEW_REQUIRED"],
                    ),
                ),
                ("closed-sales-credit-review", closed_sales_credit_review),
                ("duplicate-review-subject", duplicate_review_subject),
                ("unevaluated-doi-overlap-action", unevaluated_doi_overlap_action),
            ),
        )

    def test_audit_namespace_event_and_transition_mutations_fail_closed(self) -> None:
        def sales_credit_run_event_id(view: dict[str, object]) -> None:
            _replace_path(
                view,
                ("events", 0, "event_id"),
                "SYN-RUN-M7-WRONG-SC-EVENT-0001",
            )

        def duplicate_event_id(view: dict[str, object]) -> None:
            events = view["events"]
            assert type(events) is list and type(events[0]) is dict
            events.append({**events[0], "sequence": 2})

        self._assert_mutations_rejected(
            "audit",
            (
                (
                    "wrong-subject-namespace",
                    lambda view: _replace_path(
                        view,
                        ("subject_id",),
                        "SYN-SNAPSHOT-M7-WRONG-AUDIT-0001",
                    ),
                ),
                (
                    "unknown-event-kind",
                    lambda view: _replace_path(
                        view,
                        ("events", 0, "event_kind"),
                        "MADE_UP_EVENT",
                    ),
                ),
                (
                    "unknown-state",
                    lambda view: _replace_path(
                        view,
                        ("events", 0, "state"),
                        "MADE_UP_STATE",
                    ),
                ),
                ("sales-credit-run-event-id", sales_credit_run_event_id),
                ("duplicate-event-id", duplicate_event_id),
            ),
        )
        doi_event = {
            "event_id": EVENT_ID,
            "event_kind": "CASE",
            "occurred_at": "2026-09-01T12:00:00Z",
            "sequence": 1,
            "state": "ACTIVE",
            "transition_id": "TR-007",
        }
        doi_audit = {
            "events": [doi_event],
            "schema_version": CONTROL_CENTER_SCHEMA_VERSION,
            "subject_id": CASE_ID,
            "subject_kind": "DOI_CASE",
        }
        render_dashboard_page("audit", doi_audit, CSRF)
        for transition, state in (
            ("TR-000", "ACTIVE"),
            ("TR-116", "ACTIVE"),
            ("TR-007", "CLOSED_HARD"),
        ):
            with self.subTest(transition=transition, state=state):
                mutated = {
                    **doi_audit,
                    "events": [{**doi_event, "state": state, "transition_id": transition}],
                }
                with self.assertRaises(PortalContractError):
                    render_dashboard_page("audit", mutated, CSRF)

        evaluation_audit = {
            "events": [
                {
                    "event_id": EVALUATION_ID,
                    "event_kind": "EVALUATION_RECORDED",
                    "occurred_at": "2026-09-01T12:00:00Z",
                    "sequence": 1,
                    "state": "OUTBOUND_EVIDENCE_HUMAN_REVIEW",
                    "transition_id": None,
                }
            ],
            "schema_version": CONTROL_CENTER_SCHEMA_VERSION,
            "subject_id": EVALUATION_ID,
            "subject_kind": "EVALUATION",
        }
        render_dashboard_page("audit", evaluation_audit, CSRF)
        for label, events in (
            ("empty", []),
            (
                "wrong-event-id",
                [{**evaluation_audit["events"][0], "event_id": "SYN-EVALUATION-M7-OTHER"}],
            ),
            (
                "wrong-sequence",
                [{**evaluation_audit["events"][0], "sequence": 9}],
            ),
        ):
            with self.subTest(evaluation=label):
                with self.assertRaises(PortalContractError):
                    render_dashboard_page(
                        "audit",
                        {**evaluation_audit, "events": events},
                        CSRF,
                    )

        run_audit = {
            "events": [
                {
                    "event_id": "a" * 64,
                    "event_kind": "RUN_STARTED",
                    "occurred_at": "2026-09-01T12:00:00Z",
                    "sequence": 1,
                    "state": "RUN_STARTED",
                    "transition_id": None,
                }
            ],
            "schema_version": CONTROL_CENTER_SCHEMA_VERSION,
            "subject_id": "SYN-RUN-M7-AUDIT-0001",
            "subject_kind": "DOI_RUN",
        }
        render_dashboard_page("audit", run_audit, CSRF)
        terminal_only = {
            **run_audit,
            "events": [
                {
                    **run_audit["events"][0],
                    "event_id": "b" * 64,
                    "event_kind": "RUN_TERMINAL",
                    "state": "RUN_TERMINAL",
                }
            ],
        }
        with self.assertRaises(PortalContractError):
            render_dashboard_page("audit", terminal_only, CSRF)

    def test_system_component_semantic_mutations_fail_closed(self) -> None:
        def unhealthy_database_with_passing_service(
            view: dict[str, object],
        ) -> None:
            _replace_path(
                view,
                ("database", "database_status"),
                "UNHEALTHY",
            )
            _replace_path(
                view,
                ("database", "foreign_key_status"),
                "VIOLATIONS",
            )

        unhealthy_system = _views()["system"]
        _replace_path(unhealthy_system, ("service_status",), "FAIL")
        _replace_path(
            unhealthy_system,
            ("database", "database_status"),
            "UNHEALTHY",
        )
        _replace_path(
            unhealthy_system,
            ("database", "foreign_key_status"),
            "VIOLATIONS",
        )
        render_dashboard_page("system", unhealthy_system, CSRF)

        projection_drift = _views()["system"]
        _replace_path(projection_drift, ("service_status",), "FAIL")
        _replace_path(
            projection_drift,
            ("database", "projection_status"),
            "DRIFT",
        )
        render_dashboard_page("system", projection_drift, CSRF)

        self._assert_mutations_rejected(
            "system",
            (
                (
                    "service-status",
                    lambda view: _replace_path(
                        view,
                        ("service_status",),
                        "RUNNING",
                    ),
                ),
                (
                    "network-policy",
                    lambda view: _replace_path(
                        view,
                        ("network_policy",),
                        "LOOPBACK_ONLY",
                    ),
                ),
                (
                    "runtime-class",
                    lambda view: _replace_path(
                        view,
                        ("runtime_directory_class",),
                        "REPOSITORY_LOCAL",
                    ),
                ),
                (
                    "owned-pid-type",
                    lambda view: _replace_path(
                        view,
                        ("owned_pid",),
                        {"pid": 4242},
                    ),
                ),
                (
                    "api-version",
                    lambda view: _replace_path(
                        view,
                        ("api_schema_version",),
                        "synthetic-sales-assist-api/v2",
                    ),
                ),
                (
                    "application-version",
                    lambda view: _replace_path(
                        view,
                        ("application_version",),
                        "9.9.9",
                    ),
                ),
                (
                    "service-database-coherence",
                    unhealthy_database_with_passing_service,
                ),
                (
                    "healthy-database-with-failed-service",
                    lambda view: _replace_path(
                        view,
                        ("service_status",),
                        "FAIL",
                    ),
                ),
                (
                    "too-many-safe-errors",
                    lambda view: _replace_path(
                        view,
                        ("recent_safe_errors",),
                        [view["recent_safe_errors"][0]] * 11,
                    ),
                ),
            ),
        )

    def test_database_and_backup_semantic_mutations_fail_closed(self) -> None:
        unhealthy = _views()["database"]
        _replace_path(
            unhealthy,
            ("database", "database_status"),
            "UNHEALTHY",
        )
        _replace_path(
            unhealthy,
            ("database", "foreign_key_status"),
            "VIOLATIONS",
        )
        render_dashboard_page("database", unhealthy, CSRF)

        projection_drift = _views()["database"]
        _replace_path(
            projection_drift,
            ("database", "projection_status"),
            "DRIFT",
        )
        render_dashboard_page("database", projection_drift, CSRF)

        writer_timestamp = _views()["database"]
        _replace_path(
            writer_timestamp,
            ("database", "migrations", 0, "applied_at_utc"),
            "2026-09-01T12:00:01.000000Z",
        )
        render_dashboard_page("database", writer_timestamp, CSRF)

        database_mutations = (
            ("schema", ("database", "schema_version"), 99),
            ("status", ("database", "database_status"), "TRUST_ME"),
            ("location", ("database", "database_location_class"), "OWNED"),
            ("size-type", ("database", "database_size_bytes"), "4096"),
            ("quick-check", ("database", "quick_check"), "PASS"),
            ("integrity", ("database", "integrity_check"), "UNKNOWN"),
            ("foreign-key", ("database", "foreign_key_status"), "PASS"),
            ("projection", ("database", "projection_status"), "PASS"),
            (
                "healthy-foreign-key-violation",
                ("database", "foreign_key_status"),
                "VIOLATIONS",
            ),
            (
                "unhealthy-with-passing-checks",
                ("database", "database_status"),
                "UNHEALTHY",
            ),
            ("migration-version", ("database", "migrations", 0, "version"), 0),
            ("migration-name", ("database", "migrations", 0, "name"), "other"),
            ("migration-hash", ("database", "migrations", 0, "sha256"), "a" * 64),
            (
                "migration-time",
                ("database", "migrations", 0, "applied_at_utc"),
                "yesterday",
            ),
            ("migration-order", ("database", "migrations", 0, "version"), 2),
            (
                "safety-inventory",
                ("database", "safety_counters"),
                {f"BOGUS_{index}": 1 for index in range(9)},
            ),
            (
                "observation-time-mismatch",
                ("database", "safety_observed_at"),
                "2026-09-01T12:06:01Z",
            ),
            (
                "restore-id-kind",
                ("database", "latest_restore", "restore_id"),
                "SYN-EVIDENCE-REPORT-M7-0001",
            ),
            (
                "pre-restore-backup-id-kind",
                ("database", "latest_restore", "pre_restore_backup_id"),
                "SYN-EVIDENCE-REPORT-M7-0002",
            ),
        )
        mutations = tuple(
            (
                label,
                lambda view, path=path, value=value: _replace_path(
                    view,
                    path,
                    value,
                ),
            )
            for label, path, value in database_mutations
        )
        self._assert_mutations_rejected("database", mutations)

        failed = _views()["backups"]
        _replace_path(failed, ("items", 0, "status"), "FAILED")
        _replace_path(failed, ("items", 0, "quick_check"), "failed")
        _replace_path(failed, ("items", 0, "foreign_key_check"), "not_run")
        render_dashboard_page("backups", failed, CSRF)

        failed_after_foreign_key_check = _views()["backups"]
        _replace_path(
            failed_after_foreign_key_check,
            ("items", 0, "status"),
            "FAILED",
        )
        _replace_path(
            failed_after_foreign_key_check,
            ("items", 0, "quick_check"),
            "ok",
        )
        _replace_path(
            failed_after_foreign_key_check,
            ("items", 0, "foreign_key_check"),
            "failed",
        )
        render_dashboard_page("backups", failed_after_foreign_key_check, CSRF)

        def failed_with_no_evidence(view: dict[str, object]) -> None:
            _replace_path(view, ("items", 0, "status"), "FAILED")
            _replace_path(view, ("items", 0, "completed_at"), None)
            _replace_path(view, ("items", 0, "backup_sha256"), None)
            _replace_path(view, ("items", 0, "quick_check"), "not_run")
            _replace_path(view, ("items", 0, "foreign_key_check"), "not_run")

        def failed_with_success_evidence(view: dict[str, object]) -> None:
            _replace_path(view, ("items", 0, "status"), "FAILED")

        def started_with_completed_evidence(view: dict[str, object]) -> None:
            _replace_path(view, ("items", 0, "status"), "STARTED")

        def completed_with_failed_check(view: dict[str, object]) -> None:
            _replace_path(view, ("items", 0, "quick_check"), "failed")

        def completed_without_timestamp(view: dict[str, object]) -> None:
            _replace_path(view, ("items", 0, "completed_at"), None)

        def duplicate_backup_receipt(view: dict[str, object]) -> None:
            items = view["items"]
            assert type(items) is list and type(items[0]) is dict
            items.append(dict(items[0]))
            view["total_count"] = 2

        def too_many_backup_receipts(view: dict[str, object]) -> None:
            view["items"] = [
                {
                    **_backup(),
                    "backup_id": f"SYN-EVIDENCE-BACKUP-M7-{index:04d}",
                }
                for index in range(26)
            ]
            view["total_count"] = 26

        self._assert_mutations_rejected(
            "backups",
            (
                (
                    "backup-schema",
                    lambda view: _replace_path(
                        view,
                        ("items", 0, "schema_version"),
                        99,
                    ),
                ),
                ("failed-no-evidence", failed_with_no_evidence),
                ("failed-success-evidence", failed_with_success_evidence),
                ("started-completed-evidence", started_with_completed_evidence),
                ("completed-failed-check", completed_with_failed_check),
                ("completed-no-timestamp", completed_without_timestamp),
                (
                    "backup-id-kind",
                    lambda view: _replace_path(
                        view,
                        ("items", 0, "backup_id"),
                        "SYN-EVIDENCE-REPORT-M7-0001",
                    ),
                ),
                ("duplicate-backup-receipt", duplicate_backup_receipt),
                ("too-many-backup-receipts", too_many_backup_receipts),
            ),
        )

    def test_extension_semantic_and_coherence_mutations_fail_closed(self) -> None:
        def add_matching_observation(view: dict[str, object]) -> None:
            _replace_path(
                view,
                ("extension", "last_seen_at"),
                "2026-09-01T12:00:00Z",
            )
            _replace_path(view, ("extension", "observed_version"), "0.1.2")

        def package_only_with_observation(view: dict[str, object]) -> None:
            add_matching_observation(view)

        def mismatch_with_matching_version(view: dict[str, object]) -> None:
            add_matching_observation(view)
            _replace_path(view, ("extension", "state"), "VERSION_MISMATCH")

        def healthy_with_ancient_observation(view: dict[str, object]) -> None:
            _replace_path(view, ("extension", "state"), "LAST_SEEN_HEALTHY")
            _replace_path(view, ("extension", "observed_version"), "0.1.2")
            _replace_path(
                view,
                ("extension", "last_seen_at"),
                "2000-01-01T00:00:00Z",
            )

        def stale_with_future_observation(view: dict[str, object]) -> None:
            _replace_path(view, ("extension", "state"), "LAST_SEEN_STALE")
            _replace_path(view, ("extension", "observed_version"), "0.1.2")
            _replace_path(
                view,
                ("extension", "last_seen_at"),
                "2099-01-01T00:00:00Z",
            )

        self._assert_mutations_rejected(
            "extension",
            (
                (
                    "expected-version-type",
                    lambda view: _replace_path(
                        view,
                        ("extension", "expected_version"),
                        {"version": "0.1.2"},
                    ),
                ),
                (
                    "expected-version",
                    lambda view: _replace_path(
                        view,
                        ("extension", "expected_version"),
                        "9.9.9",
                    ),
                ),
                (
                    "expected-hash",
                    lambda view: _replace_path(
                        view,
                        ("extension", "expected_package_sha256"),
                        "a" * 64,
                    ),
                ),
                (
                    "observed-version",
                    lambda view: _replace_path(
                        view,
                        ("extension", "observed_version"),
                        "release-candidate",
                    ),
                ),
                (
                    "last-seen",
                    lambda view: _replace_path(
                        view,
                        ("extension", "last_seen_at"),
                        "not-a-time",
                    ),
                ),
                (
                    "stale-after-type",
                    lambda view: _replace_path(
                        view,
                        ("extension", "stale_after_seconds"),
                        "300",
                    ),
                ),
                (
                    "unknown-state",
                    lambda view: _replace_path(
                        view,
                        ("extension", "state"),
                        "INSTALLED",
                    ),
                ),
                ("package-only-observation", package_only_with_observation),
                ("mismatch-matching-version", mismatch_with_matching_version),
                ("healthy-ancient-observation", healthy_with_ancient_observation),
                ("stale-future-observation", stale_with_future_observation),
            ),
        )

    def test_telemetry_semantic_mutations_fail_closed(self) -> None:
        def current_reviews_exceed_active_cases(view: dict[str, object]) -> None:
            _replace_path(view, ("metrics", "current_human_review_items"), 3)

        def negative_realized_total(view: dict[str, object]) -> None:
            _replace_path(
                view,
                ("metrics", "realized_by_currency"),
                [
                    {
                        "amount_minor_units": -1,
                        "currency_code": "USD",
                        "currency_registry_version": (
                            "synthetic-iso-style-currency-registry/v1"
                        ),
                        "currency_scale": 2,
                        "item_count": 1,
                    }
                ],
            )

        self._assert_mutations_rejected(
            "telemetry",
            (
                (
                    "count-type",
                    lambda view: _replace_path(
                        view,
                        ("metrics", "requests_received"),
                        "3",
                    ),
                ),
                (
                    "rate-coherence",
                    lambda view: _replace_path(
                        view,
                        ("metrics", "successful_request_rate"),
                        {
                            "defined": False,
                            "display": "BOGUS",
                            "denominator": 4,
                            "numerator": 9,
                        },
                    ),
                ),
                (
                    "empty-denominator-registry",
                    lambda view: _replace_path(
                        view,
                        ("denominator_registry", "metrics"),
                        [],
                    ),
                ),
                (
                    "denominator-id",
                    lambda view: _replace_path(
                        view,
                        ("denominator_registry", "metrics", 0, "metric_id"),
                        "made_up_metric",
                    ),
                ),
                (
                    "currency-registry",
                    lambda view: _replace_path(
                        view,
                        ("metrics", "potential_by_currency", 0,
                         "currency_registry_version"),
                        "synthetic-currency-registry/v2",
                    ),
                ),
                (
                    "currency-item-count",
                    lambda view: _replace_path(
                        view,
                        ("metrics", "potential_by_currency", 0, "item_count"),
                        "1",
                    ),
                ),
                (
                    "metric-window",
                    lambda view: _replace_path(
                        view,
                        ("metrics", "window"),
                        "FOREVER",
                    ),
                ),
                (
                    "safety-inventory",
                    lambda view: _replace_path(
                        view,
                        ("metrics", "safety_counters"),
                        {f"BOGUS_{index}": 1 for index in range(9)},
                    ),
                ),
                (
                    "operational-observation-time-mismatch",
                    lambda view: _replace_path(
                        view,
                        ("operational_status", "safety_observed_at"),
                        "2026-09-01T12:06:01Z",
                    ),
                ),
                (
                    "negative-potential-total",
                    lambda view: _replace_path(
                        view,
                        (
                            "metrics",
                            "potential_by_currency",
                            0,
                            "amount_minor_units",
                        ),
                        -1,
                    ),
                ),
                ("negative-realized-total", negative_realized_total),
                (
                    "current-reviews-exceed-active-cases",
                    current_reviews_exceed_active_cases,
                ),
            ),
        )

    def test_bounded_window_may_span_evaluation_and_terminal_request_times(self) -> None:
        view = _views()["telemetry"]
        _replace_path(view, ("metrics", "unique_evaluations"), 5)
        _replace_path(
            view,
            ("metrics", "sales_credit_result_distribution"),
            {"OUTBOUND_EVIDENCE_HUMAN_REVIEW": 4},
        )
        _replace_path(view, ("metrics", "human_review_rate"), _rate(2, 5))
        _replace_path(
            view,
            ("metrics", "window"),
            "[2026-09-01T12:00:00Z, 2026-09-01T13:00:00Z)",
        )
        rendered = render_dashboard_page("telemetry", view, CSRF)
        self.assertIn(b"2026-09-01T12:00:00Z", rendered)

    def test_assets_are_local_static_and_accessibility_safe(self) -> None:
        self.assertEqual(
            set(DASHBOARD_STATIC_ASSETS),
            {"/static/ssa-dashboard.css", "/static/ssa-dashboard.js"},
        )
        self.assertIn("prefers-reduced-motion", DASHBOARD_CSS)
        self.assertIn("focus-visible", DASHBOARD_CSS)
        self.assertIn("min-width: 320px", DASHBOARD_CSS)
        self.assertIn("same-origin", DASHBOARD_JS)
        self.assertIn("endpointPattern", DASHBOARD_JS)
        for prohibited in (
            "eval(",
            "innerHTML",
            "document.write",
            "http://",
            "https://",
            "WebSocket",
            "localStorage",
            "sessionStorage",
        ):
            self.assertNotIn(prohibited, DASHBOARD_JS)


if __name__ == "__main__":
    unittest.main()
