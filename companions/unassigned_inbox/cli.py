"""One-shot, read-only Unassigned inbox snapshots, opt-in and self-contained."""
from __future__ import annotations

import argparse
from collections import Counter
from html import escape
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit
import uuid

from .reader import (AuthenticationError, ReaderError, create_reader, positive_id,
                     unassigned_scope_issues, utc_now)
from .support import (ReadLock, configuration, plain_text, read_json,
                      resolve_scope, write_json)


RUN_PATTERN = re.compile(r"unassigned-[0-9a-f]{32}")
SCOPE_KEYS = ("mailbox_id", "mailbox_name", "mailbox_email", "user_id", "user_email")


def safe_error(exc):
    return str(exc) if isinstance(exc, ReaderError) else type(exc).__name__


def web_link(conversation):
    links = conversation.get("_links")
    web = links.get("web") if isinstance(links, dict) else None
    raw = web.get("href", "") if isinstance(web, dict) else ""
    if not isinstance(raw, str):
        return ""
    parsed = urlsplit(raw)
    return raw if (parsed.scheme == "https" and parsed.hostname == "secure.helpscout.net" and
                   parsed.username is None and parsed.password is None and parsed.port is None) else ""


def thread_html(thread):
    label = f"{thread.get('type', 'unknown')} / {thread.get('state', 'unknown')}"
    author = thread.get("createdBy") or thread.get("customer") or {}
    if not isinstance(author, dict):
        author = {}
    author_name = author.get("email") or " ".join(str(author.get(k, "")) for k in ("first", "last"))
    embedded = thread.get("_embedded") if isinstance(thread.get("_embedded"), dict) else {}
    attachments = thread.get("attachments") or embedded.get("attachments") or []
    if not isinstance(attachments, list):
        attachments = []
    files = ""
    if attachments:
        files = "<p>Attachments (contents not downloaded): " + escape(
            ", ".join(str(a.get("filename", a.get("fileName", "unnamed")))
                      for a in attachments if isinstance(a, dict))) + "</p>"
    return ("<section class='thread'><p><strong>" + escape(label) + "</strong> · " +
            escape(str(thread.get("createdAt", ""))) + " · " + escape(str(author_name)) +
            " · Thread " + escape(str(thread.get("id", ""))) + "</p><pre>" +
            escape(plain_text(thread.get("body", ""))) + "</pre>" + files + "</section>")


def write_report(run_dir, work):
    records = {}
    for cid in work["conversation_ids"]:
        path = run_dir / "records" / f"{cid}.json"
        if path.exists():
            record = read_json(path)
            if record.get("conversation_id") != cid:
                raise ValueError("Saved record identifier mismatch")
            records[cid] = record
    counts = Counter(record["outcome"] for record in records.values())
    good = [r for r in records.values() if r["outcome"] == "FULLY_READ"]
    threads = [t for r in good for t in r["context"]["threads"]]
    unread = len(work["conversation_ids"]) - len(records)
    complete = (work["coverage"]["complete"] is True and unread == 0 and
                not counts["READ_FAILED"] and not counts["OUT_OF_SCOPE"])
    report = {
        "run_id": work["run_id"], "mode": "read-only-unassigned", "scope": work["scope"],
        "generated_at_utc": utc_now(), "coverage": work["coverage"],
        "conversation_count": len(work["conversation_ids"]), "fully_read": len(good),
        "unread": unread, "out_of_scope": counts["OUT_OF_SCOPE"], "read_failed": counts["READ_FAILED"],
        "threads_read": len(threads), "listing_complete": work["coverage"]["complete"], "complete": complete,
        "conversations_with_drafts": sum(any(t.get("state") == "draft" for t in r["context"]["threads"]) for r in good),
        "threads_with_attachments": sum(bool(t.get("attachments") or
                                             ((t.get("_embedded") or {}).get("attachments")
                                              if isinstance(t.get("_embedded"), dict) else None)) for t in threads),
        "conversation_write_attempts": 0, "drafts_created": 0, "messages_sent": 0,
        "semantic_review": "Not performed; these are source histories, not reply recommendations",
        "report_path": str(run_dir / "report.html"),
        "items": [{"conversation_id": cid, "outcome": records.get(cid, {}).get("outcome", "UNREAD"),
                   "checked_at_utc": records.get(cid, {}).get("checked_at_utc"),
                   "detail": records.get(cid, {}).get("detail", [])} for cid in work["conversation_ids"]],
    }
    cards = "".join(f"<div><b>{report[key]}</b><span>{label}</span></div>" for key, label in (
        ("conversation_count", "Listed conversations"), ("fully_read", "Full histories read"),
        ("threads_read", "Messages and events"), ("unread", "Not read yet"),
        ("out_of_scope", "Scope changed / mismatch"), ("read_failed", "Read failures")))
    articles = []
    for listed in work["conversations"]:
        cid = listed["id"]
        record = records.get(cid, {})
        context = record.get("context") or {}
        conversation = context.get("conversation") or listed
        customer = conversation.get("primaryCustomer")
        if not isinstance(customer, dict):
            customer = {}
        outcome = record.get("outcome", "UNREAD")
        link = web_link(conversation)
        history = ""
        if outcome == "FULLY_READ":
            history = ("<details><summary>Read full history · " + str(len(context["threads"])) +
                       " messages and events</summary>" + "".join(thread_html(t) for t in context["threads"]) + "</details>")
        articles.append("<article><h2>" + escape(str(conversation.get("subject") or "(No subject)")) +
                        "</h2><p>" + escape(str(customer.get("email", ""))) + " · Conversation " + str(cid) +
                        " · <strong>" + escape(outcome.replace("_", " ").title()) + "</strong></p>" +
                        ("<p>Checked: " + escape(record["checked_at_utc"]) + "</p>" if record.get("checked_at_utc") else "") +
                        ("<p>" + escape("; ".join(record.get("detail", []))) + "</p>" if record.get("detail") else "") +
                        ('<p><a href="' + escape(link, quote=True) + '" rel="noreferrer">Open in Help Scout</a></p>' if link else "") +
                        history + "</article>")
    scope = work["scope"]
    html = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>Unassigned inbox · Local snapshot</title><style>
body{font:16px/1.55 system-ui,sans-serif;margin:0;background:#f3f5f7;color:#172434}
main{max-width:1100px;margin:auto;padding:36px 22px}h1{font-size:32px;line-height:1.2}h2{font-size:20px;overflow-wrap:anywhere}
.eyebrow{font-size:13px;letter-spacing:.12em;color:#345d70}p{margin:10px 0}a{color:#075f84}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:12px;margin:28px 0}
.cards div,article{background:white;border:1px solid #d8dfe6;border-radius:12px;padding:18px}.cards b{display:block;font-size:30px}.cards span{font-size:13px}
article{margin:18px 0}summary{cursor:pointer;font-weight:600;padding:12px 0}.thread{border-top:1px solid #d8dfe6;padding:12px 0}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.6 system-ui,sans-serif}.subtle{color:#536478}
</style></head><body><main><p class="eyebrow">LOCAL READ-ONLY SNAPSHOT</p><h1>Unassigned inbox</h1>"""
    html += ("<p>" + escape(scope["mailbox_name"] + " · " + scope["mailbox_email"]) + "</p>" +
             "<p>Active, unassigned conversations. " + ("All listed histories captured." if complete else "Partial snapshot; see the counts and exceptions below.") +
             "</p><p class='subtle'>" + escape(work["coverage"].get("started_at_utc", "")) +
             " · Listing observed across pages, not a frozen queue. Assignment may change after each read.</p>" + cards +
             "<p>Source histories include customer messages, staff replies, internal notes and existing drafts, labeled by type and state. No reply decisions or drafts were generated. Attachments were not downloaded.</p>" +
             ("<p>Listing limitations: " + escape("; ".join(work["coverage"].get("limitations", []))) + "</p>" if work["coverage"].get("limitations") else "") +
             "".join(articles) + "<p class='subtle'>Run " + escape(work["run_id"]) + " · Zero conversation changes.</p></main></body></html>")
    temp = run_dir / "report.html.tmp"
    temp.write_text(html, encoding="utf-8")
    temp.replace(run_dir / "report.html")
    write_json(run_dir / "report.json", report)
    return report


def scan(cfg, mailbox, max_contexts=30, resume=None, *, reader=None, progress=None):
    if max_contexts is not None and (type(max_contexts) is not int or max_contexts < 1):
        raise ValueError("Maximum contexts must be positive")
    if resume is not None and (not isinstance(resume, str) or not RUN_PATTERN.fullmatch(resume)):
        raise ValueError("Invalid Unassigned run identifier")
    base = cfg["runtime_dir"] / "unassigned" / "runs"
    existing = None
    if resume:
        saved_path = (base / resume / "work-set.json").resolve()
        if base.resolve() not in saved_path.parents:
            raise ValueError("Saved work set must remain inside the external runtime")
        existing = read_json(saved_path)
        if existing.get("run_id") != resume or existing.get("mode") != "read-only-unassigned":
            raise ValueError("This is not an Unassigned reader work set")
        if existing.get("scope", {}).get("mailbox_selector") != mailbox:
            raise ValueError("Resume mailbox differs from saved work set")
        ids = existing.get("conversation_ids")
        rows = existing.get("conversations")
        if (not isinstance(ids, list) or not isinstance(rows, list) or len(ids) != len(rows) or
                len(ids) != len(set(ids)) or
                any(type(cid) is not int or cid < 1 or not isinstance(row, dict) or row.get("id") != cid
                    for cid, row in zip(ids, rows)) or
                not isinstance(existing.get("coverage"), dict) or
                type(existing["coverage"].get("complete")) is not bool):
            raise ValueError("Saved Unassigned work set is invalid")
    reader = reader if reader is not None else create_reader(cfg["auth_path"])
    scope = resolve_scope(reader, cfg, mailbox)
    scope.update(assignment="unassigned", status="active")
    if existing:
        if any(existing["scope"].get(key) != scope[key] for key in SCOPE_KEYS):
            raise ValueError("Live scope differs from saved Unassigned work set")
        work = existing
    else:
        rows, coverage = reader.list_unassigned_conversations(scope["mailbox_id"])
        ids = [positive_id(row["id"]) for row in rows]
        if len(ids) != len(set(ids)):
            raise ValueError("Unassigned reader must return unique conversation IDs")
        work = {"schema_version": 1, "run_id": "unassigned-" + uuid.uuid4().hex,
                "mode": "read-only-unassigned", "scope": scope, "coverage": coverage,
                "conversation_ids": ids, "conversations": rows}
    run_dir = base / work["run_id"]
    run_dir.mkdir(parents=True, exist_ok=True)
    with ReadLock(run_dir / "read.lock"):
        if not existing:
            write_json(run_dir / "work-set.json", work)
        write_report(run_dir, work)
        attempted = 0
        try:
            for listed in work["conversations"]:
                cid = positive_id(listed["id"])
                path = run_dir / "records" / f"{cid}.json"
                if path.exists():
                    continue
                if max_contexts is not None and attempted >= max_contexts:
                    break
                attempted += 1
                record = {"conversation_id": cid, "checked_at_utc": utc_now(), "detail": []}
                stop = False
                try:
                    issues = unassigned_scope_issues(listed, scope["mailbox_id"])
                    if not issues:
                        fresh = reader.get_conversation(cid)
                        issues = unassigned_scope_issues(fresh, scope["mailbox_id"])
                        if fresh.get("id") != cid:
                            issues.append("Conversation identifier differs from work set")
                    if issues:
                        record.update(outcome="OUT_OF_SCOPE", detail=issues)
                    else:
                        context = reader.get_context(cid)
                        if context.get("complete") is not True or (context.get("thread_coverage") or {}).get("complete") is not True:
                            raise ReaderError("Full thread coverage was not verified")
                        issues = unassigned_scope_issues(context["conversation"], scope["mailbox_id"])
                        if context["conversation"].get("id") != cid:
                            issues.append("Conversation identifier differs from work set")
                        record.update(outcome="OUT_OF_SCOPE" if issues else "FULLY_READ", detail=issues,
                                      context=context, checked_at_utc=context.get("checked_at_utc") or utc_now())
                except Exception as exc:
                    record.update(outcome="READ_FAILED", detail=[safe_error(exc)], checked_at_utc=utc_now())
                    stop = isinstance(exc, AuthenticationError)
                write_json(path, record)
                if progress:
                    progress({"run_id": work["run_id"], "attempted_this_call": attempted, "outcome": record["outcome"]})
                if stop:
                    break
        finally:
            report = write_report(run_dir, work)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read active Unassigned conversations into a local report. No conversation writes.")
    parser.add_argument("--config", required=True, help="Absolute path to external local configuration")
    parser.add_argument("--mailbox", required=True, help="Selector from the external configuration")
    bounds = parser.add_mutually_exclusive_group()
    bounds.add_argument("--max-contexts", type=int, default=30, help="Maximum full histories this call (default: 30)")
    bounds.add_argument("--all", action="store_true", help="Read every conversation in the saved work set")
    parser.add_argument("--resume", help="Continue unread IDs from an existing Unassigned run")
    args = parser.parse_args(argv)
    if args.max_contexts < 1:
        parser.error("--max-contexts must be positive")
    try:
        cfg = configuration(args.config)
        report = scan(cfg, args.mailbox, None if args.all else args.max_contexts, args.resume,
                      progress=lambda item: print(json.dumps(item), flush=True))
        print(json.dumps({k: v for k, v in report.items() if k not in {"items", "scope", "coverage"}}, indent=2))
        return 0 if report["listing_complete"] and not report["read_failed"] and not report["out_of_scope"] else 2
    except Exception as exc:
        print(json.dumps({"mode": "read-only-unassigned", "error": safe_error(exc), "conversation_write_attempts": 0}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
