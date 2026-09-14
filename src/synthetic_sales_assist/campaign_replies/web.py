"""Closed feature routes carried by the existing authenticated loopback server."""

from __future__ import annotations

import json
import re
from html import escape
from pathlib import Path
from urllib.parse import parse_qsl


WORKSPACE_API_ROUTE = "/api/v1/campaign-workspace"
WORKSPACE_ACTION_ROUTE = WORKSPACE_API_ROUTE + "/actions"
MAX_WORKSPACE_BODY_BYTES = 8 * 1024 * 1024
ASSET_ROOT = Path(__file__).resolve().parents[1] / "portal"
WORKSPACE_GET_ROUTES = frozenset({
    "/campaigns", "/replies", "/writing-history", WORKSPACE_API_ROUTE,
    "/static/ssa-campaign-workspace.js", "/static/ssa-campaign-workspace.css",
})


class WorkspaceError(ValueError):
    def __init__(self, code: str, category: str = "INVALID") -> None:
        super().__init__(code)
        self.code = code
        self.category = category


def _json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, allow_nan=False).encode("utf-8")


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise WorkspaceError("DUPLICATE_JSON_MEMBER")
        result[key] = value
    return result


def page(csrf: str) -> bytes:
    if not re.fullmatch(r"[0-9a-f]{64}", csrf):
        raise WorkspaceError("CSRF_TOKEN_INVALID")
    doctype = "<!" + "doctype html>"
    html_open = "<" + 'html lang="en">'
    document = doctype + """
<!-- SYNTHETIC-SALES-ASSIST-AUTHORED-M5 -->
HTML_OPEN<head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="ssa-csrf-token" content="TOKEN">
<title>Campaigns and Replies · Sales Assist</title>
<link rel="stylesheet" href="/static/ssa-dashboard.css">
<link rel="stylesheet" href="/static/ssa-campaign-workspace.css">
<script src="/static/ssa-campaign-workspace.js" defer></script></head><body>
<a class="dashboard-skip-link" href="#workspace">Skip to workspace</a>
<div class="dashboard-synthetic-banner">Synthetic demo · Localhost only · No live connection</div>
<header class="dashboard-header"><span class="dashboard-brand">ECS Sales Assist</span>
<nav class="dashboard-nav" aria-label="Primary">
<a href="/overview">Overview</a><a href="/sales-credit">Sales Credit</a><a href="/doi">DOI</a>
<a href="/review">Human review</a>
<a href="/campaigns">Campaigns</a><a href="/replies">Replies</a>
<a href="/writing-history">Writing history</a>
<a href="/campaign-replies">Campaign Replies</a><a href="/system">System</a></nav></header>
<main id="workspace" class="dashboard-main dashboard-stack">
<header class="workspace-heading"><div><p class="eyebrow">LOCAL CAMPAIGN WORKSPACE</p>
<h1 id="page-title">Campaigns and Replies</h1>
<p id="page-description">Prepare outreach, inspect evidence, and review local drafts.</p></div>
<button id="load-demo" type="button">Load synthetic demo</button></header>
<p id="message" class="workspace-message" role="status" aria-live="polite"></p>
<div id="summary" class="workspace-summary"></div>
<section id="campaign-section" hidden><h2>Prepared campaigns</h2>
<p>Local simulation worker. The independent PowerShell sender is not connected.</p>
<div id="campaign-list"></div><div id="campaign-detail"></div>
<details><summary>Import synthetic audience or immutable send state</summary>
<p>New preparation preserves original rank and content bindings.
Continuation imports protections.</p>
<label>Import kind <select id="campaign-import-kind"><option value="prepare">
New audience manifest</option><option value="send-state">Send-state bundle</option>
</select></label>
<label>Generated synthetic JSON file <input id="campaign-file" type="file" accept=".json"></label>
<button id="campaign-import" type="button">Validate and import</button></details></section>
<section id="reply-section" hidden><div class="workspace-filters">
<label>Needs reply <select id="needs-reply"><option value="">All</option>
<option value="true" selected>Unanswered</option><option value="false">Resolved / waiting</option>
</select></label><label>Category <input id="category" placeholder="All categories"></label>
<label>Owner <input id="owner" placeholder="All synthetic owners"></label>
<label>Order <select id="sort"><option value="priority">Attention priority</option>
<option value="cart">Highest recorded cart value</option><option value="age">Oldest request</option>
</select></label><button id="filter" type="button">Apply filters</button></div>
<p id="sync-status"></p><div class="workspace-columns"><section aria-label="Reply queue">
<div id="reply-queue"></div><div class="workspace-actions"><button id="previous">Previous</button>
<span id="page-info"></span><button id="next">Next</button></div></section>
<section id="conversation" aria-label="Conversation review"><h2>Choose a conversation</h2>
<p>Inspect customer requests and source evidence before reviewing a local draft.</p></section></div>
<details><summary>Import a complete synthetic reply snapshot</summary>
<label>Snapshot JSON <input id="snapshot-file" type="file" accept=".json"></label>
<button id="snapshot-import">Validate and import snapshot</button></details></section>
<section id="history-section" hidden><h2>Writing preparation</h2>
<p>Candidate writing is not verified personal authorship. Preparation is deterministic;
no model training or AI API is connected.</p><div id="history-summary"></div>
<details><summary>Import extracted synthetic history</summary>
<p>Select exporter 2.1.0 report.json and sent-emails-*.json files, at most 8 MB combined.
Real history requires a separate future production profile and store.</p>
<label>Extracted JSON files
<input id="history-files" type="file" accept=".json" multiple></label>
<button id="history-import">Validate and prepare</button></details>
<h2>Versioned style configuration</h2><div id="style-profile"></div>
<label>Approved synthetic style-profile JSON
<textarea id="profile-json" rows="7"></textarea></label>
<button id="profile-save">Save style configuration</button>
<p>Changing the configuration invalidates review and preserves accepted draft text.</p>
<h2>Inspectable candidates</h2><div id="history-candidates"></div>
<div class="workspace-actions"><button id="history-previous" type="button">Previous</button>
<span id="history-page-info"></span><button id="history-next" type="button">Next</button></div>
</section>
<footer>Published acceptance does not prove delivery. Recorded cart value and reported purchases
do not prove recovered revenue. All draft edits stay in this local synthetic store.</footer>
</main></body></html>
"""
    return document.replace("TOKEN", escape(csrf)).replace("HTML_OPEN", html_open).encode("utf-8")


class WorkspaceWeb:
    def __init__(self, path: Path) -> None:
        from synthetic_sales_assist.campaign_replies.application import WorkspaceApplication

        self.application = WorkspaceApplication(path)

    def get(self, path: str, query: str, csrf: str) -> tuple[str, bytes]:
        if path not in WORKSPACE_GET_ROUTES:
            raise WorkspaceError("WORKSPACE_ROUTE_INVALID")
        if path.endswith(".js") or path.endswith(".css"):
            suffix = ".js" if path.endswith(".js") else ".css"
            mime = "text/javascript" if suffix == ".js" else "text/css"
            asset = ASSET_ROOT / ("campaign_workspace" + suffix)
            return mime + "; charset=utf-8", asset.read_bytes()
        if path != WORKSPACE_API_ROUTE:
            return "text/html; charset=utf-8", page(csrf)
        try:
            pairs = parse_qsl(
                query, keep_blank_values=True, strict_parsing=True, max_num_fields=9,
            )
        except ValueError:
            raise WorkspaceError("WORKSPACE_QUERY_INVALID") from None
        allowed = {
            "view", "id", "campaign_id", "needs_reply", "category", "owner", "sort", "offset",
        }
        if len(pairs) > 9 or any(key not in allowed for key, _ in pairs):
            raise WorkspaceError("WORKSPACE_QUERY_INVALID")
        params = _pairs(pairs)
        return "application/json; charset=utf-8", self._call("get", params)

    def post(self, raw: bytes) -> bytes:
        if not isinstance(raw, bytes) or len(raw) > MAX_WORKSPACE_BODY_BYTES:
            raise WorkspaceError("WORKSPACE_REQUEST_SIZE_INVALID")

        def reject_constant(_value: str) -> object:
            raise WorkspaceError("WORKSPACE_JSON_CONSTANT_INVALID")

        try:
            payload = json.loads(raw, object_pairs_hook=_pairs, parse_constant=reject_constant)
        except (ValueError, UnicodeDecodeError, RecursionError):
            raise WorkspaceError("WORKSPACE_JSON_INVALID") from None
        if type(payload) is not dict:
            raise WorkspaceError("WORKSPACE_REQUEST_INVALID")
        return self._call("post", payload)

    def _call(self, method: str, payload: dict) -> bytes:
        try:
            result = getattr(self.application, method)(payload)
            return _json({"schema_version": "synthetic-campaign-workspace/v1", "data": result})
        except (ValueError, KeyError, TypeError, RuntimeError) as exc:
            if isinstance(exc, WorkspaceError):
                raise
            raw_code = str(getattr(exc, "code", str(exc)))
            code = raw_code if re.fullmatch(r"[A-Z][A-Z0-9_]{0,95}", raw_code) else (
                "WORKSPACE_INPUT_REJECTED"
            )
            category = "CONFLICT" if any(
                part in code for part in ("CONFLICT", "STALE", "REVISION")
            ) else "INVALID"
            raise WorkspaceError(code, category) from None
