"""Exact local-only static assets for the synthetic portal.

SYNTHETIC-SALES-ASSIST-AUTHORED-M5
"""

from __future__ import annotations

from typing import Final


ASSET_MARKER: Final = "SYNTHETIC-SALES-ASSIST-AUTHORED-M5"

PORTAL_CSS: Final = f"""/* {ASSET_MARKER} */
:root {{
  color-scheme: light;
  font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  background: #f4f7f9;
  color: #17212b;
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; min-width: 320px; }}
a {{ color: #075e74; }}
a:focus-visible, button:focus-visible, input:focus-visible, select:focus-visible {{
  outline: 3px solid #0b93b8;
  outline-offset: 2px;
}}
.synthetic-banner {{
  background: #073b4c;
  color: #fff;
  font-weight: 750;
  letter-spacing: .04em;
  padding: .65rem 1rem;
  text-align: center;
}}
header {{
  align-items: center;
  background: #fff;
  border-bottom: 1px solid #cbd7dc;
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  justify-content: space-between;
  padding: .8rem clamp(1rem, 4vw, 3rem);
}}
nav {{ display: flex; gap: 1rem; }}
main {{ margin: 0 auto; max-width: 1180px; padding: 1.25rem; }}
h1, h2, h3 {{ color: #073b4c; line-height: 1.2; }}
.muted {{ color: #4a5c66; }}
.grid {{
  display: grid;
  gap: 1rem;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
}}
.card, .panel {{
  background: #fff;
  border: 1px solid #cbd7dc;
  border-radius: .55rem;
  box-shadow: 0 2px 8px rgb(7 59 76 / 8%);
  padding: 1rem;
}}
.badge {{
  background: #dceff2;
  border-radius: 999px;
  color: #075e74;
  display: inline-block;
  font-size: .78rem;
  font-weight: 700;
  padding: .2rem .55rem;
}}
.badge.warning {{ background: #fff1c7; color: #6d4d00; }}
.badge.error {{ background: #fde2e2; color: #821f1f; }}
button {{
  background: #087e8b;
  border: 0;
  border-radius: .35rem;
  color: #fff;
  cursor: pointer;
  font: inherit;
  font-weight: 700;
  padding: .55rem .8rem;
}}
button[disabled] {{ cursor: wait; opacity: .55; }}
input, select {{
  border: 1px solid #8ba1aa;
  border-radius: .35rem;
  font: inherit;
  max-width: 100%;
  padding: .5rem;
}}
form {{ display: flex; flex-wrap: wrap; gap: .55rem; margin-top: .8rem; }}
.table-wrap {{ overflow-x: auto; }}
table {{ border-collapse: collapse; min-width: 720px; width: 100%; }}
caption {{ font-weight: 700; padding: .5rem; text-align: left; }}
th, td {{
  border-bottom: 1px solid #dce4e8; padding: .6rem; text-align: left; vertical-align: top;
}}
th {{ background: #eaf2f4; color: #073b4c; }}
dl {{ display: grid; gap: .45rem 1rem; grid-template-columns: minmax(9rem, auto) 1fr; }}
dt {{ font-weight: 700; }}
dd {{ margin: 0; overflow-wrap: anywhere; }}
.result {{ border-left: 5px solid #087e8b; }}
.status-message {{ min-height: 1.5rem; padding-top: .45rem; }}
.stack {{ display: grid; gap: 1rem; }}
footer {{ color: #4a5c66; padding: 2rem 1rem; text-align: center; }}
@media (max-width: 600px) {{
  main {{ padding: .75rem; }}
  dl {{ grid-template-columns: 1fr; }}
  dt {{ margin-top: .4rem; }}
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
