"""Repository-owned static assets for the localhost Control Center.

The assets deliberately contain no remote references, inline-event helpers, arbitrary URL
navigation, source-page mutation, or business classification logic.  JavaScript is limited to
transporting explicitly confirmed, closed local form fields to a route embedded by the trusted
server renderer.
"""

from __future__ import annotations

from typing import Final


DASHBOARD_ASSET_MARKER: Final = "SYNTHETIC-SALES-ASSIST-AUTHORED-M7"

DASHBOARD_CSS: Final = f"""/* {DASHBOARD_ASSET_MARKER} */
:root {{
  color-scheme: light;
  font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  background: #edf3f5;
  color: #17242d;
}}
* {{ box-sizing: border-box; }}
html {{ min-width: 320px; }}
body {{ margin: 0; overflow-wrap: anywhere; }}
a {{ color: #075f76; text-underline-offset: .16em; }}
a:hover {{ color: #034a5d; }}
a:focus-visible,
button:focus-visible,
input:focus-visible,
select:focus-visible {{
  outline: 3px solid #08a0c6;
  outline-offset: 3px;
}}
.dashboard-skip-link {{
  background: #fff;
  border: 3px solid #08a0c6;
  left: .75rem;
  padding: .65rem 1rem;
  position: fixed;
  top: -8rem;
  z-index: 10;
}}
.dashboard-skip-link:focus {{ top: .75rem; }}
.dashboard-synthetic-banner {{
  background: #063b4b;
  color: #fff;
  font-weight: 800;
  letter-spacing: .055em;
  padding: .65rem 1rem;
  text-align: center;
}}
.dashboard-header {{
  align-items: center;
  background: #fff;
  border-bottom: 1px solid #b9cbd2;
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  justify-content: space-between;
  padding: .9rem clamp(.9rem, 4vw, 3rem);
}}
.dashboard-brand {{ color: #063b4b; font-weight: 800; }}
.dashboard-nav {{ display: flex; flex-wrap: wrap; gap: .4rem 1rem; }}
.dashboard-nav a[aria-current="page"] {{ font-weight: 800; }}
.dashboard-service-status {{
  background: #dceef1;
  border-bottom: 1px solid #b9cbd2;
  color: #29434d;
  padding: .55rem clamp(.9rem, 4vw, 3rem);
}}
.dashboard-main {{ margin: 0 auto; max-width: 1240px; padding: 1.25rem; }}
h1, h2, h3 {{ color: #063b4b; line-height: 1.22; }}
h1 {{ font-size: clamp(1.7rem, 4vw, 2.45rem); margin-top: 0; }}
h2 {{ font-size: 1.3rem; }}
h3 {{ font-size: 1.05rem; }}
.dashboard-lede {{ color: #425a65; max-width: 78ch; }}
.dashboard-grid {{
  display: grid;
  gap: 1rem;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 16rem), 1fr));
}}
.dashboard-card,
.dashboard-panel {{
  background: #fff;
  border: 1px solid #b9cbd2;
  border-radius: .55rem;
  box-shadow: 0 2px 8px rgb(6 59 75 / 8%);
  padding: 1rem;
}}
.dashboard-card h2,
.dashboard-card h3 {{ margin-top: 0; }}
.dashboard-value {{
  color: #063b4b;
  display: block;
  font-size: 1.85rem;
  font-variant-numeric: tabular-nums;
  font-weight: 800;
  margin: .35rem 0;
}}
.dashboard-meta {{ color: #4b626c; font-size: .9rem; }}
.dashboard-state {{
  background: #dceef1;
  border-radius: 999px;
  color: #075f76;
  display: inline-block;
  font-size: .8rem;
  font-weight: 800;
  padding: .25rem .6rem;
}}
.dashboard-state[data-severity="attention"] {{ background: #fff0c2; color: #634900; }}
.dashboard-state[data-severity="error"] {{ background: #fbdede; color: #7b1d1d; }}
.dashboard-state[data-severity="success"] {{ background: #dcefdc; color: #225f28; }}
.dashboard-callout {{ border-left: 5px solid #087f8c; }}
.dashboard-warning {{ border-left: 5px solid #b98500; }}
.dashboard-error {{ border-left: 5px solid #9a2525; }}
.dashboard-stack {{ display: grid; gap: 1rem; }}
.dashboard-split {{
  display: grid;
  gap: 1rem;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 22rem), 1fr));
}}
.dashboard-table-wrap {{ overflow-x: auto; }}
table {{ border-collapse: collapse; min-width: 46rem; width: 100%; }}
caption {{ font-weight: 800; padding: .6rem 0; text-align: left; }}
th, td {{
  border-bottom: 1px solid #d7e1e5;
  padding: .65rem;
  text-align: left;
  vertical-align: top;
}}
th {{ background: #e8f1f3; color: #063b4b; }}
tbody tr:focus-within {{ background: #f0f8fa; }}
dl {{
  display: grid;
  gap: .5rem 1rem;
  grid-template-columns: minmax(10rem, auto) 1fr;
}}
dt {{ font-weight: 800; }}
dd {{ margin: 0; }}
.dashboard-form {{ display: grid; gap: .85rem; max-width: 48rem; }}
.dashboard-field {{ display: grid; gap: .3rem; }}
.dashboard-field > span:first-child {{ font-weight: 750; }}
.dashboard-field-hint {{ color: #4b626c; font-size: .88rem; }}
input, select {{
  background: #fff;
  border: 1px solid #718c98;
  border-radius: .35rem;
  font: inherit;
  max-width: 100%;
  padding: .55rem;
}}
input[type="checkbox"], input[type="radio"] {{ height: 1.15rem; width: 1.15rem; }}
.dashboard-confirmation {{
  align-items: start;
  background: #fff8dc;
  border: 1px solid #d1b45b;
  border-radius: .35rem;
  display: flex;
  gap: .55rem;
  padding: .75rem;
}}
button {{
  background: #087f8c;
  border: 0;
  border-radius: .35rem;
  color: #fff;
  cursor: pointer;
  font: inherit;
  font-weight: 800;
  justify-self: start;
  padding: .65rem .9rem;
}}
button:hover {{ background: #066874; }}
button[disabled] {{ cursor: wait; opacity: .62; }}
.dashboard-live-region {{ min-height: 1.65rem; padding: .25rem 0; }}
.dashboard-filter {{
  align-items: end;
  display: flex;
  flex-wrap: wrap;
  gap: .7rem;
}}
.dashboard-filter .dashboard-field {{ min-width: min(100%, 11rem); }}
.dashboard-pagination {{ display: flex; flex-wrap: wrap; gap: .8rem; margin-top: 1rem; }}
.dashboard-empty {{ color: #4b626c; font-style: italic; }}
.dashboard-code {{ font-family: ui-monospace, "Cascadia Mono", Consolas, monospace; }}
.dashboard-footer {{ color: #4b626c; padding: 2rem 1rem; text-align: center; }}
[data-ssa-dashboard-id] {{ overflow-wrap: anywhere; }}
body[data-ssa-dashboard-presentation="true"] .dashboard-volatile {{ display: none; }}
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
    return payload;
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
