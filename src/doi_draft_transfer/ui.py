"""Draft-review page within the existing Sales Assist frame."""

from pathlib import Path

from synthetic_sales_assist.portal.dashboard_rendering import _page


def render_page(csrf_token, *, draft_only=False):
    body = Path(__file__).with_name("ui.html").read_text(encoding="utf-8")
    if draft_only:
        body = body.replace(
            '<p><a href="/doi-csv-review">Back to DOI split review</a></p>\n', "", 1
        )
    return _page(
        route_name="doi_draft_transfer",
        heading="Review drafts for Help Scout",
        lede="Import, review and approve each exact draft. Customer sending is a separate step.",
        csrf_token=csrf_token,
        presentation=False,
        review_only=True,
        draft_only=draft_only,
        body=body,
    )


def asset(name):
    if name not in {"ui.js", "ui.css"}:
        raise ValueError("Invalid draft asset")
    return Path(__file__).with_name(name).read_bytes()
