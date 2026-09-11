"""Local application facade; HTTP exposes only these explicit synthetic services."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from synthetic_sales_assist.campaign_replies.campaign_fixtures import seed_demo
from synthetic_sales_assist.campaign_replies.campaigns import CampaignService
from synthetic_sales_assist.campaign_replies.history import HistoryService
from synthetic_sales_assist.campaign_replies.history_fixtures import demo_history_export
from synthetic_sales_assist.campaign_replies.replies import RepliesService
from synthetic_sales_assist.campaign_replies.reply_fixtures import (
    demo_snapshot,
    snapshot_from_campaign_records,
)
from synthetic_sales_assist.campaign_replies.store import Store
from synthetic_sales_assist.campaign_replies.web import WorkspaceError


def _closed(payload: dict, required: set[str], optional: set[str] | None = None) -> None:
    if not required <= payload.keys() or set(payload) - required - (optional or set()):
        raise WorkspaceError("WORKSPACE_REQUEST_MEMBERS_INVALID")


def _offset(params: dict) -> int:
    raw = params.get("offset", "0")
    if (not isinstance(raw, str) or not raw.isascii() or not raw.isdigit()
            or len(raw) > 6 or int(raw) > 100_000):
        raise WorkspaceError("WORKSPACE_OFFSET_INVALID")
    return int(raw)


class WorkspaceApplication:
    def __init__(self, path: Path) -> None:
        self.store = Store(path)
        self.campaigns = CampaignService(self.store)
        self.replies = RepliesService(self.store)
        self.history = HistoryService(self.store)

    def get(self, params: dict) -> Any:
        view = params.get("view")
        if view == "campaigns":
            _closed(params, {"view"})
            return {"items": self.campaigns.list_campaigns()}
        if view == "campaign":
            _closed(params, {"view", "id"})
            campaign = self.campaigns.detail(params["id"])
            campaign["suppression_candidates"] = self.replies.suppression_candidates()
            return campaign
        if view == "suppressions":
            _closed(params, {"view"})
            return self.replies.suppression_candidates()
        if view == "preview":
            _closed(params, {"view", "id", "campaign_id"})
            return self.campaigns.preview(params["campaign_id"], params["id"])
        if view == "queue":
            _closed(params, {"view"}, {
                "campaign_id", "needs_reply", "category", "owner", "sort", "offset",
            })
            needs = params.get("needs_reply")
            if needs not in (None, "true", "false"):
                raise WorkspaceError("WORKSPACE_FILTER_INVALID")
            offset = _offset(params)
            sort = {"cart": "value", "age": "oldest"}.get(
                params.get("sort"), params.get("sort", "priority")
            )
            return self.replies.list_queue(
                campaign_id=params.get("campaign_id"),
                needs_reply=None if needs is None else needs == "true",
                category=params.get("category"), owner=params.get("owner"),
                sort=sort, offset=offset, limit=50,
            )
        if view == "conversation":
            _closed(params, {"view", "id"})
            return self.replies.detail(params["id"])
        if view == "history":
            _closed(params, {"view"}, {"offset"})
            offset = _offset(params)
            return {"summary": self.history.summary(),
                    "candidates": self.history.candidates(offset=offset, limit=50),
                    "profile": self.replies.style_profile()}
        raise WorkspaceError("WORKSPACE_VIEW_INVALID")

    def post(self, payload: dict) -> Any:
        action = payload.get("action")
        if action == "demo":
            _closed(payload, {"action"})
            campaign_id = seed_demo(self.campaigns)
            # Replaying these exact generated inputs preserves existing draft edits.
            replies = self.replies.import_snapshot(demo_snapshot())
            history = self.history.import_export(**demo_history_export())
            return {"campaign_id": campaign_id, "replies": replies, "history": history}
        if action in {"launch", "pause", "resume", "step"}:
            _closed(payload, {"action", "campaign_id"})
            return getattr(self.campaigns, action)(payload["campaign_id"])
        if action == "reconcile":
            _closed(payload, {"action", "campaign_id"})
            campaign = self.campaigns.detail(payload["campaign_id"])
            for record in campaign["records"]:
                if record["receipt"]:
                    self.campaigns.reconcile(payload["campaign_id"], record["queue_key"])
            return self.campaigns.detail(payload["campaign_id"])
        if action == "demo-reply":
            _closed(payload, {"action", "campaign_id"})
            records = self.campaigns.detail(payload["campaign_id"])["records"]
            accepted = [record for record in records if record["outcome"] == "SIMULATED_ACCEPTED"]
            if not accepted:
                raise WorkspaceError("SIMULATE_ACCEPTED_OUTREACH_FIRST")
            snapshot = snapshot_from_campaign_records(accepted)
            return self.replies.import_snapshot(snapshot)
        if action in {"prepare", "send-state"}:
            _closed(payload, {"action", "document"})
            if type(payload["document"]) is not dict:
                raise WorkspaceError("WORKSPACE_DOCUMENT_INVALID")
            method = self.campaigns.prepare_audience if action == "prepare" else (
                self.campaigns.import_send_state
            )
            return method(payload["document"])
        if action == "snapshot":
            _closed(payload, {"action", "snapshot"})
            return self.replies.import_snapshot(payload["snapshot"])
        if action == "history":
            _closed(payload, {"action", "report", "files"})
            return self.history.import_export(payload["report"], payload["files"])
        if action == "profile":
            _closed(payload, {"action", "profile"})
            return self.replies.set_style_profile(payload["profile"])
        if action == "save-draft":
            required = {"conversation_id", "text", "expected_revision", "source_fingerprint",
                        "style_version", "reviewed"}
            _closed(payload, {"action", *required})
            return self.replies.save_draft(**{key: payload[key] for key in required})
        if action == "synthetic-job":
            _closed(payload, {"action", "conversation_id"})
            return self.replies.synthetic_job(payload["conversation_id"])
        raise WorkspaceError("WORKSPACE_ACTION_INVALID")
