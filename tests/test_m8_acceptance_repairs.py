"""Regressions from agent-executed M7 acceptance and separate source review."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

from synthetic_sales_assist.application.control_center import (
    ControlCenterApplication,
    MetricWindow,
)
from synthetic_sales_assist.application.scenarios import ScenarioApplication
from synthetic_sales_assist.portal.dashboard_assets import DASHBOARD_JS
from synthetic_sales_assist.portal.dashboard_rendering import _manager_outcome_form
from tests.test_milestone6_security import _node_executable


class _Controls(HTMLParser):
    def __init__(self, html: str) -> None:
        super().__init__()
        self.controls: list[dict[str, object]] = []
        self.feed(html)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag not in {"input", "select"} or "name" not in values:
            return
        self.controls.append({
            "name": values["name"],
            "value": values.get("value", ""),
            "type": values.get("type", "text"),
            "disabled": "disabled" in values,
            "required": "required" in values,
            "dataset": {
                "ssaOptional": values.get("data-ssa-optional", ""),
                "ssaValueType": values.get("data-ssa-value-type", "string"),
            },
        })


_FORM_HARNESS = r"""
const vm = require('node:vm');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const controls = input.controls;
const fields = Object.fromEntries(controls.map(c => [c.name, c]));
for (const control of controls) {
  control.checked = false;
  control.label = {hidden: false};
  control.closest = () => control.label;
}
const status = {textContent: '', focus() {}};
const summary = {textContent: ''};
const button = {disabled: false};
const requests = [];
const form = {
  dataset: {ssaDashboardAction: 'manager-outcome',
    ssaDashboardEndpoint: '/api/v1/dashboard/sales-credit/SYN-ORDER-M8-FORM/manager-outcome'},
  listeners: {},
  addEventListener(name, handler) {this.listeners[name] = handler;},
  querySelectorAll(selector) {
    assert.equal(selector, '[name]');
    return controls;
  },
  querySelector(selector) {
    if (selector === '[data-ssa-dashboard-action-status]') return status;
    if (selector === '[data-ssa-manager-confirmation]') return summary;
    if (selector === 'button[type="submit"]') return button;
    const match = selector.match(/^\[name="([a-z_]+)"\]$/);
    assert.ok(match, selector);
    return fields[match[1]];
  }
};
const document = {
  querySelector() {return {content: 'synthetic-form-test'};},
  querySelectorAll() {return [form];}
};
vm.runInNewContext(input.script, {document, fetch: async (url, options) => {
  requests.push(JSON.parse(options.body));
  return {ok: true, json: async () => ({data: {replayed: false}})};
}});
function change(name, value) {
  fields[name].value = value;
  if (form.listeners.change) form.listeners.change({target: fields[name]});
}
async function submit() {
  await form.listeners.submit({preventDefault() {}});
}
(async () => {
  fields.request_key.value = 'm8-form-regression';
  fields.decided_at.value = '2026-09-01T12:00:00Z';
  for (const outcome of ['APPROVED', 'DENIED', 'OTHER_REP', 'NOT_PURSUED']) {
    change('outcome', 'PARTIAL');
    assert.equal(fields.amount_minor_units.required, true);
    assert.equal(fields.currency_code.required, true);
    change('amount_minor_units', '1250');
    change('currency_code', 'USD');
    fields.confirmed.checked = true;
    change('outcome', outcome);
    assert.equal(fields.amount_minor_units.value, '');
    assert.equal(fields.currency_code.value, '');
    assert.equal(fields.amount_minor_units.label.hidden, true);
    assert.equal(fields.confirmed.checked, false);
    assert.ok(summary.textContent.includes(outcome));
    assert.ok(summary.textContent.includes(fields.actor_id.value));
    // Request construction must also resist stale/autofilled hidden values.
    fields.amount_minor_units.value = '999';
    fields.currency_code.value = 'USD';
    fields.confirmed.checked = true;
    await submit();
    assert.equal(requests.at(-1).amount_minor_units, null);
    assert.equal(requests.at(-1).currency_code, null);
  }
  change('outcome', 'PARTIAL');
  change('amount_minor_units', '1250');
  change('currency_code', 'USD');
  assert.equal(fields.amount_minor_units.label.hidden, false);
  assert.ok(summary.textContent.includes('1250'));
  assert.ok(summary.textContent.includes('USD'));
  fields.confirmed.checked = true;
  await submit();
  assert.equal(requests.at(-1).amount_minor_units, 1250);
  assert.equal(requests.at(-1).currency_code, 'USD');
  change('amount_minor_units', '0');
  fields.confirmed.checked = true;
  await submit();
  assert.equal(requests.length, 5);
  assert.ok(status.textContent.includes('INTEGER_FIELD_INVALID'));
  process.stdout.write(JSON.stringify(requests));
})().catch(error => {process.stderr.write(String(error.stack)); process.exitCode = 1;});
"""


class AcceptanceRepairTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="synthetic-sales-assist-m8-repair-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_actual_manager_javascript_clears_stale_money_and_binds_confirmation(self) -> None:
        node = _node_executable()
        if node is None:
            self.skipTest("Offline Node runtime unavailable for actual JavaScript execution")
        controls = _Controls(_manager_outcome_form("SYN-ORDER-M8-FORM")).controls
        result = subprocess.run(
            [str(node), "-e", _FORM_HARNESS],
            input=json.dumps({"script": DASHBOARD_JS, "controls": controls}),
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(json.loads(result.stdout)), 5)

    def test_overlap_review_rate_counts_durable_review_requirements(self) -> None:
        scenarios = ScenarioApplication.open(self.root / "doi")
        center = ControlCenterApplication(scenarios.database, scenario_application=scenarios)
        order = scenarios.instantiate("doi-overlap", "m8-review-instance")
        result = scenarios.evaluate(order.order_id, "m8-review-evaluate")
        self.assertTrue(result.human_review_required)
        metrics = center.metrics()
        self.assertEqual(metrics.human_review_rate.numerator, 1)
        self.assertEqual(metrics.human_review_rate.denominator, 1)
        scenarios.evaluate(order.order_id, "m8-review-evaluate")
        self.assertEqual(center.metrics().unique_evaluations, 1)
        self.assertEqual(center.metrics().human_review_rate.numerator, 1)

    def test_manager_outcome_window_excludes_end_and_later_decisions(self) -> None:
        for suffix, decided_at, expected in (
            ("inside", "2026-08-31T12:00:00Z", 1),
            ("end", "2026-09-01T00:00:00Z", 0),
            ("after", "2026-09-02T00:00:00Z", 0),
        ):
            with self.subTest(position=suffix):
                scenarios = ScenarioApplication.open(self.root / suffix)
                center = ControlCenterApplication(
                    scenarios.database, scenario_application=scenarios,
                )
                order = scenarios.instantiate("sales-credit-human-review", "m8-window")
                scenarios.evaluate(order.order_id, "m8-window-evaluation")
                center.record_sales_credit_manager_outcome(
                    order.order_id, actor_id="SYN-REP-M8-MANAGER", outcome="APPROVED",
                    amount_minor_units=None, currency_code=None, request_key="m8-window-outcome",
                    confirmed=True, decided_at=decided_at,
                )
                rate = center.metrics(MetricWindow(
                    "2026-08-20T00:00:00Z", "2026-09-01T00:00:00Z",
                )).manager_outcome_rate
                self.assertEqual(rate.denominator, 1)
                self.assertEqual(rate.numerator, expected)
                self.assertEqual(center.metrics().manager_outcome_rate.numerator, 1)
