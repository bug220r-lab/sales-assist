"""Repository-owned static assets for the localhost Control Center.

The assets deliberately contain no remote references, inline-event helpers, arbitrary URL
navigation, source-page mutation, or business classification logic.  JavaScript is limited to
transporting explicitly confirmed, closed local form fields to a route embedded by the trusted
server renderer.
"""

from __future__ import annotations

from typing import Final

from synthetic_sales_assist.portal.theme import THEME_CSS


DASHBOARD_ASSET_MARKER: Final = "SYNTHETIC-SALES-ASSIST-AUTHORED-M7"

DASHBOARD_CSS: Final = THEME_CSS + f"""/* {DASHBOARD_ASSET_MARKER} */
:root {{
  color-scheme: light;
  font-family: var(--ssa-font-family);
  background: var(--ssa-color-background);
  color: var(--ssa-color-text);
}}
* {{ box-sizing: border-box; }}
html {{ min-width: 0; }}
body {{ margin: 0; overflow-wrap: anywhere; }}
a {{ color: var(--ssa-color-primary); text-underline-offset: .16em; }}
a:hover {{ color: var(--ssa-color-primary-hover); }}
a:focus-visible,
button:focus-visible,
input:focus-visible,
select:focus-visible {{
  outline: var(--ssa-focus-width) solid var(--ssa-color-focus);
  outline-offset: 3px;
}}
summary:focus-visible {{
  outline: var(--ssa-focus-width) solid var(--ssa-color-focus);
  outline-offset: 3px;
}}
.dashboard-skip-link {{
  background: var(--ssa-color-surface);
  border: var(--ssa-focus-width) solid var(--ssa-color-focus);
  left: .75rem;
  padding: .65rem 1rem;
  position: fixed;
  top: -8rem;
  z-index: 10;
}}
.dashboard-skip-link:focus {{ top: .75rem; }}
.dashboard-synthetic-banner {{
  background: var(--ssa-color-header);
  color: var(--ssa-color-surface);
  font-weight: 800;
  letter-spacing: .055em;
  padding: .65rem 1rem;
  text-align: center;
}}
.dashboard-header {{
  align-items: center;
  background: var(--ssa-color-surface);
  border-bottom: var(--ssa-border-width) solid var(--ssa-color-border);
  display: flex;
  flex-wrap: wrap;
  gap: var(--ssa-space-4);
  justify-content: space-between;
  padding: .9rem clamp(.9rem, 4vw, 3rem);
}}
.dashboard-brand {{ color: var(--ssa-color-header); font-weight: 800; }}
.dashboard-nav {{ display: flex; flex-wrap: wrap; gap: .4rem 1rem; }}
.dashboard-nav a[aria-current="page"] {{ font-weight: 800; }}
.dashboard-service-status {{
  background: var(--ssa-color-info-surface);
  border-bottom: var(--ssa-border-width) solid var(--ssa-color-border);
  color: var(--ssa-color-muted);
  padding: .55rem clamp(.9rem, 4vw, 3rem);
}}
.dashboard-main {{ margin: 0 auto; max-width: 1240px; padding: 1.25rem; }}
h1, h2, h3 {{ color: var(--ssa-color-header); line-height: 1.22; }}
h1 {{ font-size: clamp(1.7rem, 4vw, 2.45rem); margin-top: 0; }}
h2 {{ font-size: 1.3rem; }}
h3 {{ font-size: 1.05rem; }}
.dashboard-lede {{ color: var(--ssa-color-muted); max-width: 78ch; }}
.dashboard-grid {{
  display: grid;
  gap: var(--ssa-space-4);
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 16rem), 1fr));
}}
.dashboard-work-grid {{
  display: grid;
  gap: var(--ssa-space-4);
  grid-template-columns: repeat(2, minmax(0, 1fr));
}}
.dashboard-work-card {{ display: flex; flex-direction: column; align-items: flex-start; }}
.dashboard-work-card .dashboard-value {{ font-size: 3rem; }}
.dashboard-work-card a {{ margin-top: auto; padding-top: .5rem; }}
@media (max-width: 600px) {{
  .dashboard-work-grid {{ grid-template-columns: 1fr; }}
}}
.dashboard-card,
.dashboard-panel {{
  background: var(--ssa-color-surface);
  border: var(--ssa-border-width) solid var(--ssa-color-border);
  border-radius: var(--ssa-radius-surface);
  box-shadow: var(--ssa-shadow-surface);
  padding: var(--ssa-space-4);
}}
.dashboard-card h2,
.dashboard-card h3 {{ margin-top: 0; }}
.dashboard-value {{
  color: var(--ssa-color-header);
  display: block;
  font-size: 1.85rem;
  font-variant-numeric: tabular-nums;
  font-weight: 800;
  margin: .35rem 0;
}}
.dashboard-meta {{ color: var(--ssa-color-muted); font-size: .9rem; }}
.dashboard-state {{
  background: var(--ssa-color-info-surface);
  border-radius: 999px;
  color: var(--ssa-color-primary);
  display: inline-block;
  font-size: .8rem;
  font-weight: 800;
  padding: .25rem .6rem;
}}
.dashboard-state[data-severity="attention"] {{
  background: var(--ssa-color-warning-surface);
  color: var(--ssa-color-warning);
  }}
.dashboard-state[data-severity="error"] {{
  background: var(--ssa-color-error-surface);
  color: var(--ssa-color-error);
  }}
.dashboard-state[data-severity="success"] {{
  background: var(--ssa-color-success-surface);
  color: var(--ssa-color-success);
  }}
.dashboard-callout {{ border-left: 5px solid var(--ssa-color-primary); }}
.dashboard-warning {{ border-left: 5px solid var(--ssa-color-warning-border); }}
.dashboard-error {{ border-left: 5px solid var(--ssa-color-error); }}
.dashboard-stack {{
  display: grid;
  gap: var(--ssa-space-4);
  grid-template-columns: minmax(0, 1fr);
}}
.dashboard-split {{
  display: grid;
  gap: var(--ssa-space-4);
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 22rem), 1fr));
}}
.dashboard-table-wrap {{ overflow-x: auto; }}
.doi-worklist table {{ min-width: 64rem; }}
.doi-worklist td:first-child, .doi-worklist th:first-child {{ white-space: nowrap; overflow-wrap: normal; font-variant-numeric: tabular-nums; }}
.doi-worklist td:nth-child(2) {{ white-space: nowrap; font-variant-numeric: tabular-nums; }}
.doi-worklist td:nth-child(5) {{ min-width: 22rem; }}
.doi-worklist details {{ margin-top: var(--ssa-space-2); }}
.doi-worklist summary {{ cursor: pointer; color: var(--ssa-color-primary); }}
.doi-worklist .doi-next-check {{ margin: 0 0 var(--ssa-space-2); }}
table {{ border-collapse: collapse; min-width: 46rem; width: 100%; }}
caption {{ font-weight: 800; padding: .6rem 0; text-align: left; }}
th, td {{
  border-bottom: var(--ssa-border-width) solid var(--ssa-color-border);
  padding: .65rem;
  text-align: left;
  vertical-align: top;
}}
th {{ background: var(--ssa-color-background); color: var(--ssa-color-header); }}
tbody tr:focus-within {{ background: var(--ssa-color-info-surface); }}
dl {{
  display: grid;
  gap: .5rem 1rem;
  grid-template-columns: minmax(10rem, auto) 1fr;
}}
dt {{ font-weight: 800; }}
dd {{ margin: 0; }}
.dashboard-form {{
  display: grid;
  gap: .85rem;
  grid-template-columns: minmax(0, 1fr);
  max-width: 48rem;
}}
.dashboard-form fieldset {{ min-inline-size: 0; }}
.dashboard-field {{ display: grid; gap: .3rem; grid-template-columns: minmax(0, 1fr); }}
.dashboard-field > span:first-child {{ font-weight: 750; }}
.dashboard-field-hint {{ color: var(--ssa-color-muted); font-size: .88rem; }}
input, select {{
  background: var(--ssa-color-surface);
  border: 1px solid var(--ssa-color-input-border);
  border-radius: var(--ssa-radius-control);
  font: inherit;
  max-width: 100%;
  padding: .55rem;
}}
input[type="checkbox"], input[type="radio"] {{ height: 1.15rem; width: 1.15rem; }}
.dashboard-confirmation {{
  align-items: start;
  background: var(--ssa-color-warning-surface);
  border: 1px solid var(--ssa-color-warning-border);
  border-radius: var(--ssa-radius-control);
  display: flex;
  gap: .55rem;
  padding: .75rem;
}}
button {{
  background: var(--ssa-color-primary);
  border: 0;
  border-radius: var(--ssa-radius-control);
  color: var(--ssa-color-surface);
  cursor: pointer;
  font: inherit;
  font-weight: 800;
  justify-self: start;
  padding: .65rem .9rem;
}}
button:hover {{ background: var(--ssa-color-primary-hover); }}
button[disabled] {{ cursor: wait; opacity: var(--ssa-disabled-opacity); }}
.dashboard-live-region {{ min-height: 1.65rem; padding: .25rem 0; }}
.dashboard-filter {{
  align-items: end;
  display: flex;
  flex-wrap: wrap;
  gap: .7rem;
}}
.dashboard-filter .dashboard-field {{ min-width: min(100%, 11rem); }}
.dashboard-simple-search {{
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: end;
  gap: 1rem;
}}
.dashboard-more-filters {{ grid-column: 1 / -1; }}
.dashboard-more-filters summary {{ cursor: pointer; color: var(--ssa-color-muted); }}
.dashboard-more-filters .dashboard-filter {{ padding-top: 1rem; }}
.dashboard-case-table table {{
  min-width: 0;
  table-layout: fixed;
}}
.dashboard-case-table th:nth-child(1) {{ width: 40%; }}
.dashboard-case-table th:nth-child(2) {{ width: 40%; }}
.dashboard-case-table th:nth-child(3) {{ width: 20%; }}
.dashboard-case-table td {{
  vertical-align: middle;
  padding-top: 1.1rem;
  padding-bottom: 1.1rem;
}}
.dashboard-case-table .dashboard-state {{
  font-size: .95rem;
  font-weight: 600;
}}
.dashboard-review-needed {{ color: var(--ssa-color-warning); font-weight: 700; margin: .5rem 0 0; }}
.dashboard-opportunity-list {{ list-style: none; padding: 0; margin: 0; }}
.dashboard-opportunity-list li + li {{ margin-top: .35rem; }}
.dashboard-case-table .dashboard-state + .dashboard-opportunity-list {{ margin-top: .5rem; }}
.dashboard-case-type {{ margin: .35rem 0 0; }}
.dashboard-case-link {{ display: inline-block; padding: .5rem 0; }}
@media (max-width: 600px) {{
  .dashboard-case-table table,
  .dashboard-case-table tbody,
  .dashboard-case-table tr,
  .dashboard-case-table td {{ display: block; }}
  .dashboard-case-table thead {{
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
  }}
  .dashboard-case-table tr {{
    padding: .75rem 0;
    border-bottom: var(--ssa-border-width) solid var(--ssa-color-border);
  }}
  .dashboard-case-table td {{
    border: 0;
    padding: .4rem 0;
  }}
}}
.dashboard-pagination {{ display: flex; flex-wrap: wrap; gap: .8rem; margin-top: 1rem; }}
.dashboard-empty {{ color: var(--ssa-color-muted); font-style: italic; }}
.dashboard-code {{ font-family: ui-monospace, "Cascadia Mono", Consolas, monospace; }}
.dashboard-footer {{ color: var(--ssa-color-muted); padding: 2rem 1rem; text-align: center; }}
[data-ssa-dashboard-id] {{ overflow-wrap: anywhere; }}
body[data-ssa-dashboard-presentation="true"] .dashboard-volatile {{ display: none; }}
.dashboard-field[hidden] {{ display: none; }}
@media (max-width: 650px) {{
  .dashboard-main {{ padding: .75rem; }}
  dl {{ grid-template-columns: 1fr; }}
  dt {{ margin-top: .35rem; }}
  .dashboard-nav {{ width: 100%; }}
}}
@media (prefers-reduced-motion: reduce) {{
  *, *::before, *::after {{
    animation-duration: .01ms !important;
    animation-iteration-count: 1 !important;
    scroll-behavior: auto !important;
    transition-duration: .01ms !important;
  }}
}}

.dashboard-header {{
  background: var(--ssa-color-header);
  color: var(--ssa-color-surface);
  border-bottom: 3px solid var(--ssa-color-primary);
  }}
.dashboard-brand {{
  color: var(--ssa-color-surface);
  font-size: 1.3rem;
  }}
.dashboard-header a {{
  color: var(--ssa-color-surface);
  }}
.dashboard-header a[aria-current="page"] {{
  text-decoration-color: var(--ssa-color-primary);
  text-decoration-thickness: 3px;
  }}
.dashboard-synthetic-banner {{
  font-size: .85rem;
  letter-spacing: 0;
  }}
h1 {{
  font-size: clamp(1.5rem, 4vw, 2rem);
  }}
button:active {{
  background: var(--ssa-color-primary-active);
  }}
input[type="checkbox"], input[type="radio"] {{
  flex-shrink: 0;
  accent-color: var(--ssa-color-primary);
  }}

body[data-ssa-dashboard-page="campaign-replies"] .dashboard-main {{
  max-width: 1680px; padding: 18px 24px; gap: 12px;
}}
body[data-ssa-dashboard-page="campaign-replies"] .dashboard-main > header h1 {{
  margin-bottom: 4px;
}}
body[data-ssa-dashboard-page="campaign-replies"] .dashboard-lede {{ margin: 0; }}
.dashboard-companion {{ min-width: 0; }}
.dashboard-companion-tools {{
  display: flex; align-items: center; justify-content: space-between; gap: 16px;
  margin-bottom: 12px; font-size: 14px;
}}
.dashboard-companion-tools p {{ margin: 0; }}
.dashboard-companion-tools a {{ white-space: nowrap; }}
.dashboard-companion-frame {{
  display: block; width: 100%; height: calc(100vh - 280px); min-height: 680px;
  border: 1px solid var(--ssa-color-border); border-radius: 8px;
  background: var(--ssa-color-surface);
}}
@media (max-width: 720px) {{
  body[data-ssa-dashboard-page="campaign-replies"] .dashboard-main {{ padding: 16px 12px; }}
  .dashboard-companion-tools {{ align-items: flex-start; flex-direction: column; gap: 8px; }}
  .dashboard-companion-frame {{ height: 1050px; }}
}}
"""

DASHBOARD_JS: Final = f"""/* {DASHBOARD_ASSET_MARKER} */
"use strict";
(function () {{
  const csrfMeta = document.querySelector('meta[name="ssa-csrf-token"]');
  const csrfToken = csrfMeta ? csrfMeta.content : "";
  const endpointPattern = /^\\/api\\/v1\\/dashboard\\/[A-Za-z0-9\\/-]+$/;

  function statusTarget(form) {{
    return form.querySelector("[data-ssa-dashboard-action-status]");
  }}

  function announce(form, message) {{
    const target = statusTarget(form);
    if (target) {{
      target.textContent = message;
      target.focus();
    }}
  }}

  function formPayload(form) {{
    const payload = {{}};
    form.querySelectorAll("[name]").forEach((control) => {{
      if (control.disabled || !control.name) return;
      const optional = control.dataset.ssaOptional === "true";
      const valueType = control.dataset.ssaValueType || "string";
      if ((control.type === "radio" || control.type === "checkbox") && !control.checked) {{
        if (valueType === "boolean") payload[control.name] = false;
        return;
      }}
      if (valueType === "boolean") {{
        payload[control.name] = Boolean(control.checked);
        return;
      }}
      const value = control.value;
      if (optional && value === "") {{
        payload[control.name] = null;
        return;
      }}
      if (valueType === "integer") {{
        if (!/^[0-9]+$/.test(value)) throw new Error("INTEGER_FIELD_INVALID");
        const integerValue = Number(value);
        const jsonSafeIntegerMaximum = 9007199254740991;
        if (!Number.isSafeInteger(integerValue) || integerValue <= 0 ||
            integerValue > jsonSafeIntegerMaximum) {{
          throw new Error("INTEGER_FIELD_INVALID");
        }}
        payload[control.name] = integerValue;
        return;
      }}
      if (valueType === "array") {{
        if (!Object.hasOwn(payload, control.name)) payload[control.name] = [];
        payload[control.name].push(value);
        return;
      }}
      payload[control.name] = value;
    }});
    if (form.dataset.ssaDashboardAction === "manager-outcome" &&
        payload.outcome !== "PARTIAL") {{
      payload.amount_minor_units = null;
      payload.currency_code = null;
    }}
    return payload;
  }}

  function syncManagerOutcome(form, clearConfirmation) {{
    const outcome = form.querySelector('[name="outcome"]');
    const amount = form.querySelector('[name="amount_minor_units"]');
    const currency = form.querySelector('[name="currency_code"]');
    const partial = outcome.value === "PARTIAL";
    [amount, currency].forEach((control) => {{
      control.required = partial;
      control.disabled = !partial;
      control.closest("label").hidden = !partial;
      if (!partial) control.value = "";
    }});
    if (clearConfirmation) form.querySelector('[name="confirmed"]').checked = false;
    const actor = form.querySelector('[name="actor_id"]').value;
    const summary = form.querySelector("[data-ssa-manager-confirmation]");
    if (summary) {{
      summary.textContent = `${{actor}}: ${{outcome.value || "choose an outcome"}}` +
        (partial ? `; ${{amount.value || "enter amount"}} minor units ${{currency.value}}` : "");
    }}
  }}

  async function submitLocal(form) {{
    const endpoint = form.dataset.ssaDashboardEndpoint || "";
    if (!endpointPattern.test(endpoint) || endpoint.includes("//")) {{
      throw new Error("LOCAL_ENDPOINT_INVALID");
    }}
    const response = await fetch(endpoint, {{
      method: "POST",
      credentials: "same-origin",
      headers: {{
        "Content-Type": "application/json",
        "X-SSA-CSRF-Token": csrfToken
      }},
      body: JSON.stringify(formPayload(form))
    }});
    const envelope = await response.json();
    if (!response.ok) {{
      const code = envelope && envelope.error ? envelope.error.code : "SAFE_REQUEST_ERROR";
      throw new Error(code);
    }}
    return envelope.data;
  }}

  document.querySelectorAll("form[data-ssa-dashboard-action]").forEach((form) => {{
    if (form.dataset.ssaDashboardAction === "manager-outcome") {{
      syncManagerOutcome(form, false);
      ["input", "change"].forEach((kind) => form.addEventListener(kind, (event) => {{
        if (event.target.name !== "confirmed") syncManagerOutcome(form, true);
      }}));
    }}
    form.addEventListener("submit", async (event) => {{
      event.preventDefault();
      const button = form.querySelector('button[type="submit"]');
      if (button) button.disabled = true;
      announce(form, "Processing the confirmed local synthetic action…");
      try {{
        const data = await submitLocal(form);
        const replayed = data && data.replayed === true;
        announce(
          form,
          replayed
            ? "Exact replay: the original receipt was returned and no new event was created."
            : "Local synthetic action recorded. Use the refresh link to view the new projection."
        );
        if (button) button.disabled = false;
      }} catch (error) {{
        const code = error instanceof Error ? error.message : "SAFE_REQUEST_ERROR";
        announce(form, `Action not recorded: ${{code}}. Review the fields and try again.`);
        if (button) button.disabled = false;
      }}
    }});
  }});
}})();
"""

DASHBOARD_STATIC_ASSETS: Final = {
    "/static/ssa-dashboard.css": (
        "text/css; charset=utf-8",
        DASHBOARD_CSS.encode("utf-8"),
    ),
    "/static/ssa-dashboard.js": (
        "text/javascript; charset=utf-8",
        DASHBOARD_JS.encode("utf-8"),
    ),
}


__all__ = [
    "DASHBOARD_ASSET_MARKER",
    "DASHBOARD_CSS",
    "DASHBOARD_JS",
    "DASHBOARD_STATIC_ASSETS",
]
