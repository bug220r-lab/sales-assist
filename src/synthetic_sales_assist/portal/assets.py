"""Exact local-only static assets for the synthetic portal.

SYNTHETIC-SALES-ASSIST-AUTHORED-M5
"""

from __future__ import annotations

from typing import Final

from synthetic_sales_assist.portal.theme import THEME_CSS


ASSET_MARKER: Final = "SYNTHETIC-SALES-ASSIST-AUTHORED-M5"

PORTAL_CSS: Final = THEME_CSS + f"""/* {ASSET_MARKER} */
:root {{
  color-scheme: light;
  font-family: var(--ssa-font-family);
  background: var(--ssa-color-background);
  color: var(--ssa-color-text);
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; min-width: 0; }}
a {{ color: var(--ssa-color-primary); }}
a:focus-visible, button:focus-visible, input:focus-visible, select:focus-visible {{
  outline: var(--ssa-focus-width) solid var(--ssa-color-focus);
  outline-offset: 2px;
}}
.synthetic-banner {{
  background: var(--ssa-color-header);
  color: var(--ssa-color-surface);
  font-weight: 750;
  letter-spacing: .04em;
  padding: .65rem 1rem;
  text-align: center;
}}
header {{
  align-items: center;
  background: var(--ssa-color-surface);
  border-bottom: var(--ssa-border-width) solid var(--ssa-color-border);
  display: flex;
  flex-wrap: wrap;
  gap: var(--ssa-space-4);
  justify-content: space-between;
  padding: .8rem clamp(1rem, 4vw, 3rem);
}}
nav {{ display: flex; gap: var(--ssa-space-4); }}
main {{ margin: 0 auto; max-width: 1180px; padding: 1.25rem; }}
h1, h2, h3 {{ color: var(--ssa-color-header); line-height: 1.2; }}
.muted {{ color: var(--ssa-color-muted); }}
.grid {{
  display: grid;
  gap: var(--ssa-space-4);
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
}}
.card, .panel {{
  background: var(--ssa-color-surface);
  border: var(--ssa-border-width) solid var(--ssa-color-border);
  border-radius: var(--ssa-radius-surface);
  box-shadow: var(--ssa-shadow-surface);
  padding: var(--ssa-space-4);
}}
.badge {{
  background: var(--ssa-color-info-surface);
  border-radius: 999px;
  color: var(--ssa-color-primary);
  display: inline-block;
  font-size: .78rem;
  font-weight: 700;
  padding: .2rem .55rem;
}}
.badge.warning {{ background: var(--ssa-color-warning-surface); color: var(--ssa-color-warning); }}
.badge.error {{ background: var(--ssa-color-error-surface); color: var(--ssa-color-error); }}
button {{
  background: var(--ssa-color-primary);
  border: 0;
  border-radius: var(--ssa-radius-control);
  color: var(--ssa-color-surface);
  cursor: pointer;
  font: inherit;
  font-weight: 700;
  padding: .55rem .8rem;
}}
button[disabled] {{ cursor: wait; opacity: var(--ssa-disabled-opacity); }}
input, select {{
  border: 1px solid var(--ssa-color-input-border);
  border-radius: var(--ssa-radius-control);
  font: inherit;
  max-width: 100%;
  padding: .5rem;
}}
form {{ display: flex; flex-wrap: wrap; gap: .55rem; margin-top: .8rem; }}
.table-wrap {{ overflow-x: auto; }}
table {{ border-collapse: collapse; min-width: 720px; width: 100%; }}
caption {{ font-weight: 700; padding: .5rem; text-align: left; }}
th, td {{
  border-bottom: var(--ssa-border-width) solid var(--ssa-color-border);
  padding: .6rem;
  text-align: left;
  vertical-align: top;
}}
th {{ background: var(--ssa-color-background); color: var(--ssa-color-header); }}
dl {{ display: grid; gap: .45rem 1rem; grid-template-columns: minmax(9rem, auto) 1fr; }}
dt {{ font-weight: 700; }}
dd {{ margin: 0; overflow-wrap: anywhere; }}
.result {{ border-left: 5px solid var(--ssa-color-primary); overflow-x: auto; }}
.status-message {{ min-height: 1.5rem; padding-top: .45rem; }}
.stack {{ display: grid; gap: var(--ssa-space-4); grid-template-columns: minmax(0, 1fr); }}
footer {{ color: var(--ssa-color-muted); padding: 2rem 1rem; text-align: center; }}
@media (max-width: 600px) {{
  main {{ padding: .75rem; }}
  dl {{ grid-template-columns: 1fr; }}
  dt {{ margin-top: .4rem; }}
}}

body {{
  overflow-wrap: anywhere;
  }}
body > header {{
  background: var(--ssa-color-header);
  color: var(--ssa-color-surface);
  border-bottom: 3px solid var(--ssa-color-primary);
  }}
body > header a {{
  color: var(--ssa-color-surface);
  }}
body > header strong {{
  font-size: 1.3rem;
  }}
nav {{
  flex-wrap: wrap;
  }}
.synthetic-banner {{
  font-size: .85rem;
  letter-spacing: 0;
  }}
h1 {{
  font-size: clamp(1.5rem, 4vw, 2rem);
  }}
.grid {{
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 260px), 1fr));
  }}
button:hover {{
  background: var(--ssa-color-primary-hover);
  }}
button:active {{
  background: var(--ssa-color-primary-active);
  }}
"""

PORTAL_JS: Final = f"""/* {ASSET_MARKER} */
"use strict";
(function () {{
  const csrfMeta = document.querySelector('meta[name="ssa-csrf-token"]');
  const csrfToken = csrfMeta ? csrfMeta.content : "";
  const schemaVersion = "synthetic-sales-assist-api-request/v1";

  function setStatus(form, message) {{
    const target = form.querySelector("[data-ssa-action-status]");
    if (target) target.textContent = message;
  }}

  async function postJson(url, body) {{
    const response = await fetch(url, {{
      method: "POST",
      credentials: "same-origin",
      headers: {{
        "Content-Type": "application/json",
        "X-SSA-CSRF-Token": csrfToken
      }},
      body: JSON.stringify(body)
    }});
    const payload = await response.json();
    if (!response.ok) {{
      const code = payload && payload.error ? payload.error.code : "REQUEST_FAILED";
      throw new Error(code);
    }}
    return payload.data;
  }}

  document.querySelectorAll('form[data-ssa-action="instantiate"]').forEach((form) => {{
    form.addEventListener("submit", async (event) => {{
      event.preventDefault();
      const button = form.querySelector("button");
      if (button) button.disabled = true;
      setStatus(form, "Creating local synthetic order…");
      try {{
        const alias = form.dataset.ssaAlias;
        const modeControl = form.querySelector('[name="mode"]');
        const keyControl = form.querySelector('[name="request_key"]');
        const data = await postJson(`/api/v1/scenarios/${{alias}}/instantiate`, {{
          schema_version: schemaVersion,
          request_key: keyControl && keyControl.value ? keyControl.value : null,
          mode: modeControl ? modeControl.value : "complete"
        }});
        window.location.assign(`/orders/${{data.order_id}}`);
      }} catch (error) {{
        setStatus(form, `Request failed: ${{error.message}}`);
        if (button) button.disabled = false;
      }}
    }});
  }});

  document.querySelectorAll('form[data-ssa-action="evaluate"]').forEach((form) => {{
    form.addEventListener("submit", async (event) => {{
      event.preventDefault();
      const button = form.querySelector("button");
      if (button) button.disabled = true;
      setStatus(form, "Running local synthetic evaluation…");
      try {{
        const keyControl = form.querySelector('[name="request_key"]');
        const data = await postJson(`/api/v1/orders/${{form.dataset.ssaOrderId}}/evaluate`, {{
          schema_version: schemaVersion,
          request_key: keyControl && keyControl.value ? keyControl.value : null
        }});
        setStatus(form, data.replayed ? "Exact replay returned." : "Evaluation persisted.");
        window.location.reload();
      }} catch (error) {{
        setStatus(form, `Request failed: ${{error.message}}`);
        if (button) button.disabled = false;
      }}
    }});
  }});
}})();
"""

STATIC_ASSETS: Final = {
    "/static/ssa.css": ("text/css; charset=utf-8", PORTAL_CSS.encode("utf-8")),
    "/static/ssa.js": ("text/javascript; charset=utf-8", PORTAL_JS.encode("utf-8")),
}


__all__ = ["ASSET_MARKER", "PORTAL_CSS", "PORTAL_JS", "STATIC_ASSETS"]
