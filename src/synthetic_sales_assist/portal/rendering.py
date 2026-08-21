"""Deterministic, escaped HTML rendering for the synthetic localhost portal.

SYNTHETIC-SALES-ASSIST-AUTHORED-M5
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from html import escape
from typing import Final

from synthetic_sales_assist.application.manifest import (
    ordered_line_manifest_digest_from_mappings,
)
from synthetic_sales_assist.domain.canonical import canonical_json_bytes
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp
from synthetic_sales_assist.portal.assets import ASSET_MARKER
from synthetic_sales_assist.portal.contracts import (
    DOM_SCHEMA_VERSION,
    FAIL_CLOSED_RENDER_MODES,
    MAX_RESPONSE_BODY_BYTES,
    PortalContractError,
    public_value,
    validate_alias,
    validate_history_response,
    validate_interaction_response,
    validate_line_mapping,
    validate_lower_sha256,
    validate_order_detail_response,
    validate_order_summaries_response,
    validate_run_response,
    validate_scenarios_response,
    validate_system_status_response,
)
from synthetic_sales_assist.safety.identity import is_reserved_identity


APPLICATION_SCHEMA_VERSION: Final = "synthetic-sales-assist-application/v1"
_ORDER_DETAIL_MEMBERS: Final = frozenset(
    {
        "completeness",
        "created_at",
        "doi_state",
        "evaluated",
        "human_review_required",
        "interaction_ids",
        "latest_evaluation",
        "lines",
        "mode",
        "order_id",
        "order_status",
        "relevant_line_count",
        "rule_pack",
        "sales_credit_state",
        "scenario_alias",
        "schema_version",
        "source_status",
        "updated_at",
    }
)
_COMPLETENESS_MEMBERS: Final = frozenset(
    {
        "declared_relevant_line_count",
        "fixture_version",
        "observed_order_id",
        "ordered_line_manifest_digest",
        "rendered_relevant_line_count",
        "requested_order_id",
        "source_observed_at",
        "source_schema_version",
        "state",
    }
)
_LINE_MEMBERS: Final = frozenset(
    {
        "activity",
        "availability",
        "drop_ship_state",
        "eta",
        "line_id",
        "line_index",
        "line_value",
        "product_id",
        "quantity",
    }
)
_FACT_MEMBERS: Final = frozenset({"reason_code", "tag", "value"})
_ORDER_PAYLOAD_MEMBERS: Final = frozenset(
    {
        "completeness",
        "lines",
        "mode",
        "order_id",
        "scenario_alias",
        "schema_version",
        "source_status",
    }
)
_SYSTEM_STATUS_MEMBERS: Final = frozenset(
    {
        "app_version",
        "build_version",
        "database_schema_version",
        "database_status",
        "evaluated_count",
        "expected_schema_version",
        "integrity_check",
        "migration_status",
        "projection_status",
        "quick_check",
        "registry_capacity",
        "registry_count",
        "safety_counters",
        "schema_version",
    }
)
_EVALUATION_MEMBERS: Final = frozenset(
    {
        "aggregate_potential_status",
        "aggregate_potential_value",
        "case_id",
        "closure_state",
        "command_id",
        "conflict",
        "evaluation_id",
        "explanation",
        "fired_rules",
        "handling_flags",
        "human_review_required",
        "opportunities",
        "order_id",
        "processing_duration_ns",
        "processing_stages",
        "reasons",
        "replayed",
        "rule_pack",
        "rule_pack_version",
        "run_id",
        "scenario_alias",
        "schema_version",
        "snapshot_id",
        "top_level_result",
        "value",
        "value_status",
        "workflow_state",
    }
)
_EXPLANATION_MEMBERS: Final = frozenset(
    {
        "normalized_facts",
        "precedence_decision",
        "reason_ownership",
        "rules_evaluated",
        "supplied_facts",
        "unavailable_facts",
    }
)
_PROCESSING_STAGE_MEMBERS: Final = frozenset({"duration_ns", "stage", "status"})
_OPPORTUNITY_MEMBERS: Final = frozenset(
    {"line_ids", "opportunity_type", "potential_value"}
)
_HISTORY_MEMBERS: Final = frozenset(
    {
        "artifacts",
        "attention_causes",
        "attempt_receipts",
        "conflict_count",
        "events",
        "exact_replay_count",
        "intervention_events",
        "manager_outcomes",
        "order_id",
        "receipts",
        "schema_version",
        "telemetry_event_count",
        "value_events",
    }
)
_HISTORY_EVENT_MEMBERS: Final = frozenset(
    {"evaluation_id", "event_id", "event_kind", "occurred_at", "sequence", "state"}
)
_HISTORY_ARTIFACT_MEMBERS: Final = frozenset(
    {
        "artifact_id",
        "artifact_type",
        "occurred_at",
        "reasons",
        "state",
        "transition_id",
        "value",
    }
)
_RECEIPT_SUMMARY_MEMBERS: Final = frozenset(
    {"command_id", "recorded_at", "replayed"}
)
_ATTEMPT_RECEIPT_MEMBERS: Final = frozenset(
    {
        "attempt_id",
        "command_id",
        "conflict",
        "error_code",
        "outcome",
        "recorded_at",
        "replayed",
        "telemetry_operation_id",
    }
)
_INTERACTION_MEMBERS: Final = frozenset(
    {
        "direction",
        "evidence_classification",
        "identifier_kind",
        "interaction_id",
        "order_id",
        "schema_version",
        "target_rep_participation",
        "timestamp",
        "timestamp_precision",
    }
)
_RUN_MEMBERS: Final = frozenset(
    {
        "completed_at",
        "event_count",
        "order_id",
        "rule_pack",
        "run_id",
        "run_type",
        "schema_version",
        "started_at",
        "status",
    }
)


def _h(value: object) -> str:
    return escape(str(value), quote=True)


def _mapping(value: object, code: str) -> dict[str, object]:
    safe = public_value(value)
    if type(safe) is not dict:
        raise PortalContractError(code, status=500)
    return safe


def _exact_mapping(value: object, members: frozenset[str], code: str) -> dict[str, object]:
    result = _mapping(value, code)
    if frozenset(result) != members:
        raise PortalContractError(code, status=500)
    return result


def _sequence(value: object, code: str) -> list[object]:
    safe = public_value(value)
    if type(safe) is not list:
        raise PortalContractError(code, status=500)
    return safe


def _canonical_attribute(value: object) -> str:
    raw = canonical_json_bytes(public_value(value)).decode("utf-8")
    return _h(raw)


def _field(name: str, value: object, *, element: str = "dd") -> str:
    return (
        f'<{element} data-ssa-field="{_h(name)}" '
        f'data-ssa-value="{_canonical_attribute(value)}">{_h(_display(value))}</{element}>'
    )


def _display(value: object) -> str:
    if value is None:
        return "Not available"
    if type(value) is bool:
        return "Yes" if value else "No"
    if type(value) in {str, int}:
        return str(value)
    if type(value) is list:
        return ", ".join(_display(item) for item in value) if value else "None"
    if type(value) is dict:
        if frozenset(value) == _FACT_MEMBERS:
            tag = str(value["tag"])
            observed = value["value"]
            reason = value["reason_code"]
            if tag == "KNOWN":
                return f"KNOWN · {_display(observed)}"
            if tag == "UNKNOWN":
                return f"UNKNOWN · {_display(reason)}"
            return tag
        if frozenset(value) == frozenset(
            {"amount", "currency_code", "currency_registry_version", "currency_scale"}
        ):
            return f'{value["amount"]} {value["currency_code"]}'
        return ", ".join(f"{key}: {_display(item)}" for key, item in value.items())
    raise PortalContractError("HTML_VALUE_INVALID", status=500)


def _page(
    *,
    title: str,
    page_kind: str,
    body: str,
    csrf_token: str,
    page_attributes: Mapping[str, object] | None = None,
) -> bytes:
    attributes = {
        "data-ssa-page-kind": page_kind,
        "data-ssa-schema-version": DOM_SCHEMA_VERSION,
    }
    if page_attributes:
        attributes.update(page_attributes)
    rendered_attributes = " ".join(
        f'{_h(key)}="{_h(value)}"' for key, value in sorted(attributes.items())
    )
    document = f"""<!doctype html>
<!-- {ASSET_MARKER} -->
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="ssa-csrf-token" content="{_h(csrf_token)}">
  <title>{_h(title)} · Synthetic Sales Assist</title>
  <link rel="stylesheet" href="/static/ssa.css">
  <script src="/static/ssa.js" defer></script>
</head>
<body>
  <div class="synthetic-banner">SYNTHETIC DATA ONLY · LOCALHOST</div>
  <header>
    <strong>Synthetic Sales Assist v0.1</strong>
    <nav aria-label="Primary">
      <a href="/scenarios">Scenarios</a>
      <a href="/orders">Orders</a>
    </nav>
  </header>
  <main {rendered_attributes}>
    {body}
  </main>
  <footer>Fictional local demonstration. No external system access.</footer>
</body>
</html>"""
    return document.encode("utf-8")


def render_scenarios(value: object, csrf_token: str) -> bytes:
    scenarios = validate_scenarios_response(value)
    cards_by_pack: dict[str, list[str]] = {"DOI": [], "SALES_CREDIT": []}
    required = frozenset(
        {
            "alias",
            "allowed_modes",
            "collected_scenario",
            "complexity",
            "description",
            "expected_result",
            "rule_pack",
            "schema_version",
        }
    )
    for raw in scenarios:
        item = _exact_mapping(raw, required, "SCENARIO_VIEW_INVALID")
        if item["schema_version"] != APPLICATION_SCHEMA_VERSION:
            raise PortalContractError("SCENARIO_VIEW_SCHEMA_INVALID", status=500)
        alias = validate_alias(item["alias"])
        rule_pack = item["rule_pack"]
        if type(rule_pack) is not str or rule_pack not in cards_by_pack:
            raise PortalContractError("SCENARIO_RULE_PACK_INVALID", status=500)
        modes = _sequence(item["allowed_modes"], "SCENARIO_MODES_INVALID")
        options = "".join(
            f'<option value="{_h(mode)}">{_h(mode)}</option>' for mode in modes
        )
        cards_by_pack[rule_pack].append(
            f"""<article class="card" data-ssa-scenario-alias="{_h(alias)}">
  <span class="badge">{_h(item['rule_pack'])}</span>
  <h3>{_h(alias)}</h3>
  <p>{_h(item['description'])}</p>
  <dl>
    <dt>Expected</dt><dd>{_h(item['expected_result'])}</dd>
    <dt>Edge case</dt><dd>{_h(item['complexity'])}</dd>
    <dt>Collected scenario</dt><dd>{_h(item['collected_scenario'])}</dd>
  </dl>
  <form data-ssa-action="instantiate" data-ssa-alias="{_h(alias)}">
    <label>Variant <select name="mode">{options}</select></label>
    <label>Request key <input name="request_key" maxlength="128" autocomplete="off"></label>
    <button type="submit">Instantiate fictional order</button>
    <span class="status-message" data-ssa-action-status role="status"></span>
  </form>
</article>"""
        )
    groups = "".join(
        f'<section aria-labelledby="{_h(rule_pack.casefold())}-scenarios">'
        f'<h2 id="{_h(rule_pack.casefold())}-scenarios">'
        f"{_h('DOI' if rule_pack == 'DOI' else 'Sales Credit')}</h2>"
        f'<div class="grid">{"".join(cards_by_pack[rule_pack])}</div></section>'
        for rule_pack in ("SALES_CREDIT", "DOI")
    )
    body = (
        "<h1>Synthetic scenario library</h1>"
        "<p class=\"muted\">Every record is generated from reserved fictional fixtures.</p>"
        f'<div class="stack" aria-label="Available scenarios">{groups}</div>'
    )
    return _page(
        title="Scenarios",
        page_kind="scenarios",
        body=body,
        csrf_token=csrf_token,
    )


def render_orders(value: object, csrf_token: str) -> bytes:
    orders = validate_order_summaries_response(value)
    required = frozenset(
        {
            "doi_state",
            "evaluated",
            "human_review_required",
            "mode",
            "order_id",
            "order_status",
            "relevant_line_count",
            "rule_pack",
            "sales_credit_state",
            "scenario_alias",
            "schema_version",
            "updated_at",
        }
    )
    rows: list[str] = []
    for raw in orders:
        item = _exact_mapping(raw, required, "ORDER_SUMMARY_VIEW_INVALID")
        if item["schema_version"] != APPLICATION_SCHEMA_VERSION or not is_reserved_identity(
            str(item["order_id"]), expected_namespace="ORDER"
        ):
            raise PortalContractError("ORDER_SUMMARY_BINDING_INVALID", status=500)
        rows.append(
            "<tr>"
            f'<td><a href="/orders/{_h(item["order_id"])}">{_h(item["order_id"])}</a></td>'
            f'<td>{_h(item["scenario_alias"])}</td>'
            f'<td>{_h(item["order_status"])}</td>'
            f'<td>{_h(item["relevant_line_count"])}</td>'
            f'<td>{_h(_display(item["doi_state"]))}</td>'
            f'<td>{_h(_display(item["sales_credit_state"]))}</td>'
            f'<td>{"Review" if item["human_review_required"] else "No"}</td>'
            f'<td>{_h(item["updated_at"])}</td>'
            "</tr>"
        )
    body = f"""<h1>Fictional orders</h1>
<section class="panel table-wrap">
<table>
  <caption>{len(rows)} local synthetic record(s)</caption>
  <thead><tr><th>Order</th><th>Scenario</th><th>Status</th><th>Lines</th>
  <th>DOI</th><th>Sales Credit</th><th>Human review</th><th>Updated</th></tr></thead>
  <tbody>{''.join(rows)}</tbody>
</table>
</section>"""
    return _page(
        title="Orders",
        page_kind="orders",
        body=body,
        csrf_token=csrf_token,
    )


def _validated_order(
    value: object,
) -> tuple[dict[str, object], dict[str, object], list[dict[str, object]]]:
    order = validate_order_detail_response(value)
    order = _exact_mapping(order, _ORDER_DETAIL_MEMBERS, "ORDER_DETAIL_VIEW_INVALID")
    if order["schema_version"] != APPLICATION_SCHEMA_VERSION:
        raise PortalContractError("ORDER_DETAIL_SCHEMA_INVALID", status=500)
    if not is_reserved_identity(str(order["order_id"]), expected_namespace="ORDER"):
        raise PortalContractError("ORDER_DETAIL_ID_INVALID", status=500)
    completeness = _exact_mapping(
        order["completeness"],
        _COMPLETENESS_MEMBERS,
        "COMPLETENESS_VIEW_INVALID",
    )
    state = completeness["state"]
    if state not in {"COMPLETE", "INCOMPLETE", "MALFORMED"}:
        raise PortalContractError("COMPLETENESS_STATE_INVALID", status=500)
    if order["source_status"] != state:
        raise PortalContractError("ORDER_SOURCE_STATUS_INVALID", status=500)
    if (
        completeness["requested_order_id"] != order["order_id"]
        or type(completeness["fixture_version"]) is not str
        or not completeness["fixture_version"]
        or type(completeness["source_schema_version"]) is not str
        or not completeness["source_schema_version"]
    ):
        raise PortalContractError("COMPLETENESS_SOURCE_BINDING_INVALID", status=500)
    observed_id = completeness["observed_order_id"]
    if observed_id is not None and not is_reserved_identity(
        str(observed_id), expected_namespace="ORDER"
    ):
        raise PortalContractError("COMPLETENESS_OBSERVED_ID_INVALID", status=500)
    declared_count = completeness["declared_relevant_line_count"]
    rendered_count = completeness["rendered_relevant_line_count"]
    if declared_count is not None and (
        type(declared_count) is not int or declared_count < 0
    ):
        raise PortalContractError("COMPLETENESS_COUNT_INVALID", status=500)
    if type(rendered_count) is not int or rendered_count < 0:
        raise PortalContractError("COMPLETENESS_COUNT_INVALID", status=500)
    observed_at = completeness["source_observed_at"]
    if observed_at is not None:
        if type(observed_at) is not str:
            raise PortalContractError("COMPLETENESS_TIMESTAMP_INVALID", status=500)
        try:
            CanonicalTimestamp(observed_at)
        except ValueError as exc:
            raise PortalContractError(
                "COMPLETENESS_TIMESTAMP_INVALID", status=500
            ) from exc
    digest = completeness["ordered_line_manifest_digest"]
    if digest is not None:
        validate_lower_sha256(digest, "ORDER_MANIFEST_INVALID")
    lines = _sequence(order["lines"], "ORDER_LINES_INVALID")
    validated_lines: list[dict[str, object]] = []
    for index, raw in enumerate(lines, start=1):
        line = _exact_mapping(raw, _LINE_MEMBERS, "ORDER_LINE_VIEW_INVALID")
        validate_line_mapping(line)
        if type(line["line_index"]) is not int or line["line_index"] <= 0:
            raise PortalContractError("ORDER_LINE_INDEX_INVALID", status=500)
        if not is_reserved_identity(str(line["line_id"])):
            raise PortalContractError("ORDER_LINE_ID_INVALID", status=500)
        if not is_reserved_identity(str(line["product_id"])):
            raise PortalContractError("ORDER_PRODUCT_ID_INVALID", status=500)
        if completeness["state"] == "COMPLETE" and line["line_index"] != index:
            raise PortalContractError("ORDER_LINE_INDEX_INVALID", status=500)
        for member in (
            "activity",
            "availability",
            "drop_ship_state",
            "eta",
            "line_value",
            "quantity",
        ):
            _exact_mapping(line[member], _FACT_MEMBERS, "ORDER_FACT_VIEW_INVALID")
        validated_lines.append(line)
    if state == "COMPLETE":
        if (
            completeness["observed_order_id"] != order["order_id"]
            or completeness["declared_relevant_line_count"] != len(validated_lines)
            or completeness["rendered_relevant_line_count"] != len(validated_lines)
            or order["relevant_line_count"] != len(validated_lines)
            or completeness["source_observed_at"] is None
            or len({str(item["line_id"]) for item in validated_lines})
            != len(validated_lines)
        ):
            raise PortalContractError("COMPLETE_ORDER_COHERENCE_INVALID", status=500)
        try:
            expected_digest = ordered_line_manifest_digest_from_mappings(validated_lines)
        except (TypeError, ValueError) as exc:
            raise PortalContractError(
                "COMPLETE_ORDER_MANIFEST_INPUT_INVALID", status=500
            ) from exc
        if completeness["ordered_line_manifest_digest"] != expected_digest:
            raise PortalContractError("COMPLETE_ORDER_MANIFEST_INVALID", status=500)
    return order, completeness, validated_lines


def order_source_payload(value: object) -> dict[str, object]:
    order, completeness, lines = _validated_order(value)
    payload = {
        "completeness": completeness,
        "lines": lines,
        "mode": order["mode"],
        "order_id": order["order_id"],
        "scenario_alias": order["scenario_alias"],
        "schema_version": DOM_SCHEMA_VERSION,
        "source_status": order["source_status"],
    }
    if frozenset(payload) != _ORDER_PAYLOAD_MEMBERS:
        raise PortalContractError("ORDER_PAYLOAD_MEMBERS_INVALID", status=500)
    raw = canonical_json_bytes(payload, expected_members=_ORDER_PAYLOAD_MEMBERS)
    if len(raw) > MAX_RESPONSE_BODY_BYTES:
        raise PortalContractError("ORDER_PAYLOAD_TOO_LARGE", status=500)
    if b"<" in raw or b">" in raw or b"&" in raw:
        raise PortalContractError("ORDER_PAYLOAD_HTML_UNSAFE", status=500)
    return payload


def _render_completeness(completeness: Mapping[str, object]) -> str:
    entries = "".join(
        f"<dt>{_h(member.replace('_', ' ').title())}</dt>"
        + _field(f"completeness.{member}", completeness[member])
        for member in sorted(completeness)
    )
    state = completeness["state"]
    badge_class = "" if state == "COMPLETE" else " warning"
    return f"""<section class="panel" aria-labelledby="completeness-heading"
  data-ssa-completeness="{_h(state)}"
  data-ssa-manifest-digest="{_h(completeness['ordered_line_manifest_digest'])}">
  <h2 id="completeness-heading">Whole-order completeness
    <span class="badge{badge_class}">{_h(state)}</span></h2>
  <dl>{entries}</dl>
</section>"""


def _render_lines(lines: Sequence[object]) -> str:
    rows: list[str] = []
    for raw in lines:
        line = _mapping(raw, "ORDER_LINE_VIEW_INVALID")
        cells = "".join(
            _field(f"line.{member}", line[member], element="td")
            for member in (
                "product_id",
                "quantity",
                "line_value",
                "availability",
                "eta",
                "drop_ship_state",
                "activity",
            )
        )
        rows.append(
            f'<tr data-ssa-line-id="{_h(line["line_id"])}" '
            f'data-ssa-line-index="{_h(line["line_index"])}">'
            + _field("line.line_index", line["line_index"], element="td")
            + _field("line.line_id", line["line_id"], element="td")
            + cells
            + "</tr>"
        )
    return f"""<section class="panel table-wrap">
<table>
  <caption>Complete relevant line universe</caption>
  <thead><tr><th>Index</th><th>Stable line ID</th><th>Product</th><th>Quantity</th>
  <th>Line value</th><th>Availability</th><th>ETA</th><th>DS state</th>
  <th>Activity</th></tr></thead>
  <tbody>{''.join(rows)}</tbody>
</table>
<p data-ssa-field="line-universe-end"
   data-ssa-value="{_canonical_attribute(len(rows))}">
  Final line-universe marker · {len(rows)} rendered line(s)</p>
</section>"""


def _render_evaluation(
    value: object,
    order: Mapping[str, object],
    lines: Sequence[Mapping[str, object]],
) -> str:
    if value is None:
        return '<section class="panel"><h2>Latest evaluation</h2><p>Not evaluated.</p></section>'
    result = _exact_mapping(value, _EVALUATION_MEMBERS, "EVALUATION_VIEW_INVALID")
    if (
        result["schema_version"] != APPLICATION_SCHEMA_VERSION
        or result["order_id"] != order["order_id"]
        or result["scenario_alias"] != order["scenario_alias"]
        or result["rule_pack"] != order["rule_pack"]
        or type(result["processing_duration_ns"]) is not int
        or result["processing_duration_ns"] < 0
    ):
        raise PortalContractError("EVALUATION_SCHEMA_INVALID", status=500)
    available_line_ids = {line["line_id"] for line in lines}
    opportunities = _sequence(
        result["opportunities"], "EVALUATION_OPPORTUNITIES_INVALID"
    )
    rendered_opportunities: list[str] = []
    for raw in opportunities:
        opportunity = _exact_mapping(
            raw, _OPPORTUNITY_MEMBERS, "OPPORTUNITY_VIEW_INVALID"
        )
        line_ids = _sequence(opportunity["line_ids"], "OPPORTUNITY_LINE_IDS_INVALID")
        if any(
            type(line_id) is not str
            or not is_reserved_identity(line_id)
            or line_id not in available_line_ids
            for line_id in line_ids
        ):
            raise PortalContractError("OPPORTUNITY_LINE_SCOPE_INVALID", status=500)
        rendered_opportunities.append(
            "<li>"
            + _h(
                f"{opportunity['opportunity_type']} · "
                f"lines {_display(line_ids)} · "
                f"potential {_display(opportunity['potential_value'])}"
            )
            + "</li>"
        )
    explanation = _exact_mapping(
        result["explanation"], _EXPLANATION_MEMBERS, "EXPLANATION_VIEW_INVALID"
    )
    stages = _sequence(result["processing_stages"], "PROCESSING_STAGES_INVALID")
    stage_rows: list[str] = []
    for raw in stages:
        stage = _exact_mapping(
            raw, _PROCESSING_STAGE_MEMBERS, "PROCESSING_STAGE_VIEW_INVALID"
        )
        if type(stage["duration_ns"]) is not int or stage["duration_ns"] < 0:
            raise PortalContractError("PROCESSING_STAGE_DURATION_INVALID", status=500)
        stage_rows.append(
            "<tr>"
            f"<td>{_h(stage['stage'])}</td>"
            f"<td>{_h(stage['status'])}</td>"
            f"<td>{_h(stage['duration_ns'])}</td>"
            "</tr>"
        )
    details = (
        ("Top-level result", result.get("top_level_result")),
        ("Workflow state", result.get("workflow_state")),
        ("Reasons", result.get("reasons")),
        ("Fired rules", result.get("fired_rules")),
        ("Aggregate potential status", result.get("aggregate_potential_status")),
        ("Aggregate potential value", result.get("aggregate_potential_value")),
        ("Value status", result.get("value_status")),
        ("Value", result.get("value")),
        ("Human review", result.get("human_review_required")),
        ("Handling flags", result.get("handling_flags")),
        ("Closure state", result.get("closure_state")),
        ("Exact replay", result.get("replayed")),
        ("Conflict", result.get("conflict")),
        ("Rule pack version", result.get("rule_pack_version")),
        ("Processing duration (ns)", result.get("processing_duration_ns")),
        ("Run ID", result.get("run_id")),
        ("Command ID", result.get("command_id")),
        ("Case ID", result.get("case_id")),
        ("Snapshot ID", result.get("snapshot_id")),
        ("Evaluation ID", result.get("evaluation_id")),
    )
    entries = "".join(
        f"<dt>{_h(label)}</dt><dd>{_h(_display(item))}</dd>" for label, item in details
    )
    explanation_entries = "".join(
        f"<dt>{_h(member.replace('_', ' ').title())}</dt>"
        f"<dd>{_h(_display(explanation[member]))}</dd>"
        for member in sorted(explanation)
    )
    opportunity_rows = "".join(rendered_opportunities)
    return f"""<section class="panel result"><h2>Latest evaluation</h2><dl>{entries}</dl>
<p><a href="#history">View persisted history</a></p>
<h3>Explanation</h3><dl>{explanation_entries}</dl>
<h3>Separately retained DOI opportunities</h3><ul>{opportunity_rows or '<li>None</li>'}</ul>
<h3>Processing stages</h3><table><thead><tr><th>Stage</th><th>Status</th>
<th>Duration (ns)</th></tr></thead><tbody>{''.join(stage_rows)}</tbody></table>
</section>"""


def _render_history(value: object, expected_order_id: object) -> str:
    history = validate_history_response(value)
    history = _exact_mapping(history, _HISTORY_MEMBERS, "HISTORY_VIEW_INVALID")
    if (
        history["schema_version"] != APPLICATION_SCHEMA_VERSION
        or history["order_id"] != expected_order_id
    ):
        raise PortalContractError("HISTORY_ORDER_BINDING_INVALID", status=500)
    events = _sequence(history["events"], "HISTORY_EVENTS_INVALID")
    event_rows: list[str] = []
    for raw in events:
        event = _exact_mapping(raw, _HISTORY_EVENT_MEMBERS, "HISTORY_EVENT_INVALID")
        event_rows.append(
            "<tr>"
            f"<td>{_h(event['sequence'])}</td>"
            f"<td>{_h(event['event_kind'])}</td>"
            f"<td>{_h(event['state'])}</td>"
            f"<td>{_h(event['occurred_at'])}</td>"
            f"<td>{_h(_display(event['evaluation_id']))}</td>"
            "</tr>"
        )

    artifact_sections: list[str] = []
    for member, label in (
        ("artifacts", "Snapshots and evaluations"),
        ("attention_causes", "Attention causes"),
        ("intervention_events", "Intervention history"),
        ("value_events", "Value history"),
        ("manager_outcomes", "Manager outcomes"),
    ):
        artifacts = _sequence(history[member], "HISTORY_ARTIFACTS_INVALID")
        artifact_rows: list[str] = []
        for raw in artifacts:
            artifact = _exact_mapping(
                raw, _HISTORY_ARTIFACT_MEMBERS, "HISTORY_ARTIFACT_INVALID"
            )
            artifact_rows.append(
                "<li>"
                + _h(
                    f"{artifact['artifact_type']} · {_display(artifact['artifact_id'])} · "
                    f"{artifact['state']} · "
                    f"{artifact['occurred_at']} · reasons "
                    f"{_display(artifact['reasons'])} · transition "
                    f"{_display(artifact['transition_id'])} · value "
                    f"{_display(artifact['value'])}"
                )
                + "</li>"
            )
        artifact_sections.append(
            f"<h3>{_h(label)}</h3><ul>{''.join(artifact_rows) or '<li>None</li>'}</ul>"
        )

    receipts = _sequence(history["receipts"], "HISTORY_RECEIPTS_INVALID")
    receipt_rows: list[str] = []
    for raw in receipts:
        receipt = _exact_mapping(
            raw, _RECEIPT_SUMMARY_MEMBERS, "HISTORY_RECEIPT_INVALID"
        )
        receipt_rows.append(
            "<li>"
            + _h(
                f"{receipt['command_id']} · replay {_display(receipt['replayed'])} · "
                f"{receipt['recorded_at']}"
            )
            + "</li>"
        )
    attempts = _sequence(
        history["attempt_receipts"],
        "HISTORY_ATTEMPT_RECEIPTS_INVALID",
    )
    attempt_rows: list[str] = []
    for raw in attempts:
        attempt = _exact_mapping(
            raw,
            _ATTEMPT_RECEIPT_MEMBERS,
            "HISTORY_ATTEMPT_RECEIPT_INVALID",
        )
        attempt_rows.append(
            "<li>"
            + _h(
                f"{attempt['attempt_id']} · {attempt['outcome']} · "
                f"replay {_display(attempt['replayed'])} · "
                f"conflict {_display(attempt['conflict'])} · "
                f"error {_display(attempt['error_code'])} · "
                f"command {_display(attempt['command_id'])} · "
                f"operation {attempt['telemetry_operation_id']} · "
                f"{attempt['recorded_at']}"
            )
            + "</li>"
        )
    return f"""<section class="panel table-wrap" id="history">
<h2>Persisted privacy-safe history</h2>
<p>Exact replays: {_h(history['exact_replay_count'])} ·
Conflicts: {_h(history['conflict_count'])} ·
Telemetry events: {_h(history['telemetry_event_count'])}</p>
<table><thead><tr><th>Sequence</th><th>Event</th><th>State</th><th>Time</th>
<th>Evaluation</th></tr></thead><tbody>{''.join(event_rows)}</tbody></table>
{''.join(artifact_sections)}<h3>Replay and command receipts</h3>
<ul>{''.join(receipt_rows) or '<li>None</li>'}</ul>
<h3>Durable evaluation attempts</h3>
<ul>{''.join(attempt_rows) or '<li>None</li>'}</ul></section>"""


def _render_local_status(value: object) -> str:
    status = validate_system_status_response(value)
    status = _exact_mapping(
        status,
        _SYSTEM_STATUS_MEMBERS,
        "SYSTEM_STATUS_VIEW_INVALID",
    )
    if (
        status["schema_version"] != APPLICATION_SCHEMA_VERSION
        or type(status["app_version"]) is not str
        or not status["app_version"]
        or type(status["build_version"]) is not str
        or not status["build_version"]
        or type(status["database_schema_version"]) is not int
    ):
        raise PortalContractError("SYSTEM_STATUS_VIEW_INVALID", status=500)
    entries = (
        ("Service", "Loopback-only localhost"),
        ("Application version", status["app_version"]),
        ("Build version", status["build_version"]),
        ("Database schema", status["database_schema_version"]),
        ("Database health", status["database_status"]),
    )
    rows = "".join(
        f"<dt>{_h(label)}</dt><dd>{_h(item)}</dd>" for label, item in entries
    )
    return (
        '<section class="panel local-status"><h2>Local service status</h2>'
        f"<dl>{rows}</dl></section>"
    )


def render_order_detail(
    value: object,
    history: object,
    system_status: object,
    csrf_token: str,
) -> bytes:
    order, completeness, lines = _validated_order(value)
    payload = order_source_payload(order)
    payload_text = canonical_json_bytes(
        payload,
        expected_members=_ORDER_PAYLOAD_MEMBERS,
    ).decode("utf-8")
    interactions = _sequence(order["interaction_ids"], "ORDER_INTERACTIONS_INVALID")
    interaction_links = "".join(
        f'<li><a href="/interactions/{_h(item)}">{_h(item)}</a></li>'
        for item in interactions
    )
    summary = (
        f"<dt>Order</dt>{_field('order_id', order['order_id'])}"
        f"<dt>Scenario</dt>{_field('scenario_alias', order['scenario_alias'])}"
        f"<dt>Variant</dt>{_field('mode', order['mode'])}"
        f"<dt>Source status</dt>{_field('source_status', order['source_status'])}"
        f"<dt>Rule pack</dt><dd>{_h(order['rule_pack'])}</dd>"
        f"<dt>Created</dt><dd>{_h(order['created_at'])}</dd>"
        f"<dt>Updated</dt><dd>{_h(order['updated_at'])}</dd>"
    )
    mode = order["mode"]
    rendered_completeness: Mapping[str, object] = completeness
    if mode == "missing-required-section":
        rendered_lines = (
            '<section class="panel warning"><h2>Line universe unavailable</h2>'
            "<p>Required source section is missing; extraction failed closed.</p></section>"
        )
    elif mode == "dom-payload-mismatch":
        rendered_lines = _render_lines(lines[:-1])
    else:
        rendered_lines = _render_lines(lines)
    if mode == "stale-source-changed":
        rendered_completeness = {
            **completeness,
            "source_observed_at": "1970-01-01T00:00:00Z",
        }
    if (
        completeness["state"] == "COMPLETE"
        and mode not in FAIL_CLOSED_RENDER_MODES
    ):
        evaluation_area = f"""<section class="panel"><h2>Read-only local evaluation</h2>
  <p>Evaluation reads the source facts above and persists through the existing local
  repositories.</p>
  <form data-ssa-action="evaluate" data-ssa-order-id="{_h(order['order_id'])}">
    <label>Request key <input name="request_key" maxlength="128" autocomplete="off"></label>
    <button type="submit">Evaluate synthetic order</button>
    <span class="status-message" data-ssa-action-status role="status"></span>
  </form>
</section>"""
    else:
        evaluation_area = """<section class="panel warning"><h2>Evaluation unavailable</h2>
<p>Source representation is incomplete or malformed. Evaluation is fail-closed.</p></section>"""
    body = f"""<h1>Order {_h(order['order_id'])}</h1>
{_render_local_status(system_status)}
<section class="panel"><h2>Factual summary</h2><dl>{summary}</dl></section>
{rendered_lines}
<section class="panel"><h2>Structured fictional interactions</h2>
<ul>{interaction_links or '<li>None</li>'}</ul></section>
{_render_completeness(rendered_completeness)}
{_render_evaluation(order['latest_evaluation'], order, lines)}
{_render_history(history, order['order_id'])}
{evaluation_area}
<script type="application/json" id="ssa-synthetic-order-payload">{payload_text}</script>"""
    return _page(
        title=f"Order {order['order_id']}",
        page_kind="order-detail",
        body=body,
        csrf_token=csrf_token,
        page_attributes={
            "data-ssa-completeness": completeness["state"],
            "data-ssa-manifest-digest": completeness[
                "ordered_line_manifest_digest"
            ],
            "data-ssa-order-id": order["order_id"],
        },
    )


def render_interaction(value: object, csrf_token: str) -> bytes:
    interaction = validate_interaction_response(value)
    interaction = _exact_mapping(
        interaction,
        _INTERACTION_MEMBERS,
        "INTERACTION_VIEW_INVALID",
    )
    interaction_id = interaction["interaction_id"]
    if (
        interaction["schema_version"] != APPLICATION_SCHEMA_VERSION
        or not is_reserved_identity(
            str(interaction_id), expected_namespace="INTERACTION"
        )
        or not is_reserved_identity(
            str(interaction["order_id"]), expected_namespace="ORDER"
        )
    ):
        raise PortalContractError("INTERACTION_VIEW_ID_INVALID", status=500)
    entries = "".join(
        f"<dt>{_h(member.replace('_', ' ').title())}</dt><dd>{_h(_display(item))}</dd>"
        for member, item in interaction.items()
        if member != "schema_version"
    )
    body = f"""<h1>Fictional interaction {_h(interaction_id)}</h1>
<section class="panel"><dl>{entries}</dl>
<p>No unrestricted message body is retained or displayed.</p></section>"""
    return _page(
        title=f"Interaction {interaction_id}",
        page_kind="interaction-detail",
        body=body,
        csrf_token=csrf_token,
        page_attributes={"data-ssa-interaction-id": interaction_id},
    )


def render_run(value: object, csrf_token: str) -> bytes:
    run = validate_run_response(value)
    run = _exact_mapping(run, _RUN_MEMBERS, "RUN_VIEW_INVALID")
    run_id = run["run_id"]
    if (
        run["schema_version"] != APPLICATION_SCHEMA_VERSION
        or not is_reserved_identity(str(run_id), expected_namespace="RUN")
        or not is_reserved_identity(
            str(run["order_id"]), expected_namespace="ORDER"
        )
    ):
        raise PortalContractError("RUN_VIEW_ID_INVALID", status=500)
    entries = "".join(
        f"<dt>{_h(member.replace('_', ' ').title())}</dt><dd>{_h(_display(item))}</dd>"
        for member, item in run.items()
        if member != "schema_version"
    )
    body = f'<h1>Synthetic run {_h(run_id)}</h1><section class="panel"><dl>{entries}</dl></section>'
    return _page(
        title=f"Run {run_id}",
        page_kind="run-detail",
        body=body,
        csrf_token=csrf_token,
    )


def render_safe_error(code: str, csrf_token: str) -> bytes:
    body = (
        '<section class="panel"><h1>Request unavailable</h1>'
        f'<p class="badge error">{_h(code)}</p>'
        "<p>The synthetic localhost request could not be completed.</p></section>"
    )
    return _page(
        title="Request unavailable",
        page_kind="error",
        body=body,
        csrf_token=csrf_token,
    )


__all__ = [
    "APPLICATION_SCHEMA_VERSION",
    "order_source_payload",
    "render_interaction",
    "render_order_detail",
    "render_orders",
    "render_run",
    "render_safe_error",
    "render_scenarios",
]
