"""Offline exporter 2.1.0 archive and deterministic, reviewable corpus preparation.

No network, model training, attachment fetching, production adapter or ZIP extraction.
Schema validation deliberately precedes and is independent of the synthetic firewall.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
from collections import Counter
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from difflib import SequenceMatcher
from importlib.resources import files
from sqlite3 import Connection
from typing import Any, Protocol

from synthetic_sales_assist.campaign_replies.history_fixtures import SIGNATURE
from synthetic_sales_assist.safety.content import assert_payload_safe
from synthetic_sales_assist.safety.identity import assert_reserved_identity

MAX_BYTES = 32 * 1024 * 1024
MAX_RECORDS = 50_000
_CHUNK = re.compile(r"sent-emails-([0-9]{5})\.json\Z")
_URL = re.compile(r"https?://[^\s<>]+", re.I)
_QUOTE = re.compile(
    r"(?im)^\s*(?:On .{1,300}wrote:|From:\s+.*|[-_]{3,}\s*"
    r"(?:Original Message|Forwarded message)|>.*)$"
)
_GREETING = re.compile(r"(?i)^(?:hello|hi|hey)(?:[ ,!]+(?:SYN-[A-Z0-9-]+))?[,! ]*$")
_CLOSING = re.compile(r"(?i)^(?:thanks|thank you|best regards|regards|sincerely)[,! ]*$")
LIMITATIONS = [
    "Synthetic writing examples; candidate authorship is not proof of personally typed messages.",
    "replyUserIds is a filtered conversation index; initial outbound-only coverage is unverified.",
    "A successful import is never exhaustive all-sent history or proof of delivery.",
    "HTML cleaning, template boundaries and near matches are heuristics requiring review.",
    "Attachments are metadata only; their contents were not downloaded or inspected.",
    "Deterministic corpus preparation is not model training or a completed style analysis.",
    "Unverified saved reply IDs have no confirmed signature-template mapping.",
]


class HistoryError(ValueError):
    """Bounded error without echoing potentially prohibited input."""


class HistoryStore(Protocol):
    def transaction(self) -> AbstractContextManager[Connection]: ...

    def read(self) -> AbstractContextManager[Connection]: ...


def _json(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                          allow_nan=False)
    except (TypeError, ValueError, RecursionError) as exc:
        raise HistoryError("history_invalid_json_value") from exc


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _date(value: Any) -> datetime:
    if not isinstance(value, str) or len(value) > 40:
        raise HistoryError("history_invalid_timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HistoryError("history_invalid_timestamp") from exc
    if parsed.tzinfo is None:
        raise HistoryError("history_timestamp_requires_timezone")
    return parsed.astimezone(UTC)


def _count(value: Any) -> bool:
    return type(value) is int and 0 <= value <= MAX_RECORDS


def validate_export_schema(report: Any, chunks: dict[str, Any]) -> None:
    """Validate exporter structure only; does not assert synthetic or author attribution."""
    if (not isinstance(report, dict) or type(report.get("schema_version")) is not int
            or report["schema_version"] != 1):
        raise HistoryError("history_report_schema_unsupported")
    if report.get("exporter_version") != "2.1.0":
        raise HistoryError("history_exporter_unsupported")
    for field in ("user_id", "scope_id", "server_filter", "coverage_status"):
        if not isinstance(report.get(field), str) or not report[field]:
            raise HistoryError("history_report_field_invalid")
    cutoff = _date(report.get("history_through_utc"))
    _date(report.get("created_at_utc"))
    for field in ("run_completed", "complete_all_sent_history"):
        if type(report.get(field)) is not bool:
            raise HistoryError("history_report_boolean_invalid")
    for field in ("exported_messages", "published_messages", "bounced_attempts"):
        if not _count(report.get(field)):
            raise HistoryError("history_report_count_invalid")
    if report["published_messages"] + report["bounced_attempts"] != report["exported_messages"]:
        raise HistoryError("history_report_counts_inconsistent")
    if not isinstance(chunks, dict) or len(chunks) > 1000:
        raise HistoryError("history_chunk_set_invalid")
    indexes = []
    records = 0
    identities = set()
    for name, chunk in chunks.items():
        match = _CHUNK.fullmatch(name) if isinstance(name, str) else None
        if match is None:
            raise HistoryError("history_extracted_filename_invalid")
        indexes.append(int(match[1]))
        if (not isinstance(chunk, dict) or type(chunk.get("schema_version")) is not int
                or chunk["schema_version"] != 1):
            raise HistoryError("history_chunk_schema_unsupported")
        if chunk.get("user_id") != report["user_id"]:
            raise HistoryError("history_chunk_user_mismatch")
        if _date(chunk.get("history_through_utc")) != cutoff:
            raise HistoryError("history_chunk_cutoff_mismatch")
        messages = chunk.get("messages")
        if not isinstance(messages, list) or not messages:
            raise HistoryError("history_chunk_messages_invalid")
        records += len(messages)
        if records > MAX_RECORDS:
            raise HistoryError("history_record_limit")
        for message in messages:
            if not isinstance(message, dict):
                raise HistoryError("history_record_invalid")
            for field in ("conversation_id", "thread_id", "author_user_id", "mailbox_id",
                          "conversation_type", "conversation_status", "conversation_state",
                          "subject", "source_url", "source_type", "source_via",
                          "body_text", "body_html"):
                if not isinstance(message.get(field), str) or len(message[field]) > 250_000:
                    raise HistoryError("history_record_field_invalid")
            if not message["thread_id"] or not message["author_user_id"]:
                raise HistoryError("history_record_identity_missing")
            if message.get("thread_state") not in {"published", "bounced"}:
                raise HistoryError("history_thread_state_invalid")
            if message.get("thread_type") not in {"message", "forwardparent", "forwardchild"}:
                raise HistoryError("history_thread_type_invalid")
            if "saved_reply_id" not in message or (
                message["saved_reply_id"] is not None
                and (type(message["saved_reply_id"]) is not int or message["saved_reply_id"] <= 0)
            ):
                raise HistoryError("history_saved_reply_metadata_invalid")
            if _date(message.get("sent_at_utc")) > cutoff:
                raise HistoryError("history_record_after_cutoff")
            attachments = message.get("attachments")
            if not isinstance(attachments, list) or len(attachments) > 100:
                raise HistoryError("history_attachments_invalid")
            for attachment in attachments:
                if (not isinstance(attachment, dict)
                        or not isinstance(attachment.get("id"), (str, int))
                        or not isinstance(attachment.get("filename"), str)
                        or not isinstance(attachment.get("mime_type"), str)):
                    raise HistoryError("history_attachment_invalid")
            identities.add(message["thread_id"])
    if sorted(indexes) != list(range(1, len(indexes) + 1)):
        raise HistoryError("history_missing_or_duplicate_chunk")
    if len(identities) != report["exported_messages"]:
        raise HistoryError("history_missing_or_truncated_records")


def _synthetic_gate(report: dict[str, Any], chunks: dict[str, Any]) -> None:
    for envelope in [report, *chunks.values()]:
        if envelope.get("profile") != "synthetic" or envelope.get("synthetic_fixture") is not True:
            raise HistoryError("history_requires_generated_synthetic_profile")
        assert_reserved_identity(envelope["user_id"], expected_namespace="REP")
    assert_payload_safe(report)
    for chunk in chunks.values():
        for message in chunk["messages"]:
            for field, namespace in (("conversation_id", "CONVERSATION"),
                                     ("thread_id", "INTERACTION"),
                                     ("author_user_id", "REP"), ("mailbox_id", "EVIDENCE")):
                assert_reserved_identity(message[field], expected_namespace=namespace)
            # File metadata gets a narrowly bounded synthetic filename validator;
            # the general prose scanner correctly treats arbitrary file-like domains as unsafe.
            safe_message = dict(message)
            safe_attachments = []
            for attachment in message["attachments"]:
                assert_reserved_identity(attachment["id"], expected_namespace="EVIDENCE")
                if not re.fullmatch(r"synthetic-[a-z0-9-]+\.[a-z0-9]{1,8}",
                                    attachment["filename"]):
                    raise HistoryError("history_attachment_filename_not_synthetic")
                safe_attachment = dict(attachment)
                safe_attachment["filename"] = "synthetic attachment"
                safe_attachments.append(safe_attachment)
            safe_message["attachments"] = safe_attachments
            assert_payload_safe(safe_message)
        # Preserve unknown development fields only after checking them too.
        assert_payload_safe({k: v for k, v in chunk.items() if k != "messages"})


def _normalize(text: str) -> str:
    return " ".join(_URL.sub("[link]", html.unescape(text)).casefold().split())


def _substantive(text: str) -> bool:
    return len(re.findall(r"[a-z]+", text.casefold())) >= 7 and len(text) >= 35


def _plain_html(source: str) -> str:
    source = re.split(r"(?is)<blockquote\b|<div\b[^>]*(?:gmail_quote|yahoo_quoted|divRplyFwdMsg)",
                      source, maxsplit=1)[0]
    source = re.sub(r"(?is)<(script|style)\b[^>]*>.*?</\1>", "", source)
    source = re.sub(r"(?i)<br\s*/?>|</(?:p|div|li|tr|h[1-6])\s*>", "\n", source)
    return html.unescape(re.sub(r"(?s)<[^>]*>", "", source)).strip()


def _reference_rules() -> tuple[list[str], list[dict[str, str]]]:
    signatures = SIGNATURE.splitlines()
    references = []
    resource = files("synthetic_sales_assist.campaign_replies").joinpath(
        "data/saved_reply_references.json"
    )
    data = json.loads(resource.read_text(encoding="utf-8-sig"))
    signatures.extend([data["shared_signature"]["identity_line"],
                       data["shared_signature"]["cta_label"]])
    for item in data["templates"]:
        references.append({"name": item["name"], "text": item["text_before_signature"],
                           "source": "immutable handoff saved-reply wording"})
    return signatures, references


def _segments(
    message: dict[str, Any], signatures: list[str],
) -> tuple[list[str], list[dict[str, str]]]:
    body = message["body_text"] or _plain_html(message["body_html"])
    suppressed = []
    quote = _QUOTE.search(body)
    if quote:
        suppressed.append({"reason": "quoted_text", "text": body[quote.start():]})
        body = body[:quote.start()]
    # Even if exporter-cleaned text contains a quoted block, remove its exact text.
    for block in re.findall(r"(?is)<blockquote\b[^>]*>(.*?)</blockquote>", message["body_html"]):
        quoted = _plain_html(block)
        suppressed.append({"reason": "quoted_html", "text": quoted})
        if quoted and quoted in body:
            body = body.replace(quoted, "")
    for signature in signatures:
        pattern = re.compile(r"\s+".join(re.escape(word) for word in signature.split()), re.I)
        for match in pattern.finditer(body):
            suppressed.append({"reason": "signature", "text": match[0]})
        body = pattern.sub("", body)
    lines = []
    for line in body.replace("\r", "").splitlines():
        if not line.strip():
            continue
        if _GREETING.fullmatch(line.strip()) or _CLOSING.fullmatch(line.strip()):
            suppressed.append({"reason": "greeting_or_closing", "text": line})
        else:
            lines.append(line.strip())
    return lines, suppressed


class HistoryService:
    def __init__(self, store: HistoryStore) -> None:
        self.store = store
        self.signatures, self.references = _reference_rules()
        with store.transaction() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS cr_history_imports (
                import_id TEXT PRIMARY KEY, report_json TEXT NOT NULL,
                history_through TEXT NOT NULL, created_at TEXT NOT NULL,
                imported_at TEXT NOT NULL, duplicate_records INTEGER NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS cr_history_files (
                import_id TEXT NOT NULL, filename TEXT NOT NULL, raw_json TEXT NOT NULL,
                PRIMARY KEY(import_id, filename))""")
            db.execute("""CREATE TABLE IF NOT EXISTS cr_history_variants (
                thread_id TEXT NOT NULL, fingerprint TEXT NOT NULL, raw_json TEXT NOT NULL,
                wrong_author INTEGER NOT NULL, PRIMARY KEY(thread_id, fingerprint))""")
            db.execute("""CREATE TABLE IF NOT EXISTS cr_history_provenance (
                import_id TEXT NOT NULL, filename TEXT NOT NULL, ordinal INTEGER NOT NULL,
                thread_id TEXT NOT NULL, fingerprint TEXT NOT NULL,
                PRIMARY KEY(import_id, filename, ordinal))""")
            db.execute("CREATE INDEX IF NOT EXISTS cr_history_provenance_thread "
                       "ON cr_history_provenance(thread_id)")
            db.execute("""CREATE TABLE IF NOT EXISTS cr_history_prepared (
                thread_id TEXT PRIMARY KEY, status TEXT NOT NULL, prepared_json TEXT NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS cr_history_templates (
                fingerprint TEXT PRIMARY KEY, reference_json TEXT NOT NULL)""")

    def import_export(self, report: dict[str, Any], files: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(files, dict):
            raise HistoryError("history_extracted_files_required")
        raw_files = {}
        chunks = {}
        size = len(_json(report).encode("utf-8"))
        if size > MAX_BYTES:
            raise HistoryError("history_input_size_limit")
        for name, value in files.items():
            raw = value if isinstance(value, str) else _json(value)
            size += len(raw.encode("utf-8"))
            if size > MAX_BYTES:
                raise HistoryError("history_input_size_limit")
            try:
                chunk = json.loads(raw, object_pairs_hook=_unique_keys)
            except (ValueError, RecursionError) as exc:
                raise HistoryError("history_malformed_json") from exc
            raw_files[name] = raw
            chunks[name] = chunk
        validate_export_schema(report, chunks)
        _synthetic_gate(report, chunks)
        import_id = _hash(_json({"report": report, "chunks": chunks}))
        seen = set()
        duplicates = 0
        idempotent = False
        with self.store.transaction() as db:
            prior_report = db.execute(
                "SELECT report_json FROM cr_history_imports ORDER BY rowid LIMIT 1"
            ).fetchone()
            if prior_report and json.loads(prior_report[0])["user_id"] != report["user_id"]:
                # Attribution is corpus-scoped. A second writer needs a separate store;
                # never reinterpret immutable variants using a new report's target author.
                raise HistoryError("HISTORY_WRITER_SCOPE_CONFLICT")
            existing = db.execute(
                "SELECT duplicate_records FROM cr_history_imports WHERE import_id=?", (import_id,)
            ).fetchone()
            if existing:
                idempotent = True
                duplicates = existing[0]
            else:
                for name, chunk in chunks.items():
                    db.execute("INSERT INTO cr_history_files VALUES (?,?,?)",
                               (import_id, name, raw_files[name]))
                    for ordinal, message in enumerate(chunk["messages"]):
                        raw = _json(message)
                        fingerprint = _hash(raw)
                        key = (message["thread_id"], fingerprint)
                        if key in seen:
                            duplicates += 1
                        seen.add(key)
                        db.execute("INSERT OR IGNORE INTO cr_history_variants VALUES (?,?,?,?)",
                                   (*key, raw, message["author_user_id"] != report["user_id"]))
                        db.execute("INSERT INTO cr_history_provenance VALUES (?,?,?,?,?)",
                                   (import_id, name, ordinal, *key))
                db.execute("INSERT INTO cr_history_imports VALUES (?,?,?,?,?,?)", (
                    import_id, _json(report), _date(report["history_through_utc"]).isoformat(),
                    _date(report["created_at_utc"]).isoformat(), datetime.now(UTC).isoformat(),
                    duplicates))
                self._prepare(db)
        result = self.summary()
        result.update({"import_id": import_id, "idempotent": idempotent,
                       "duplicate_records": duplicates})
        return result

    def _prepare(self, db: Connection) -> None:
        rows = db.execute(
            "SELECT * FROM cr_history_variants ORDER BY thread_id,fingerprint"
        ).fetchall()
        by_thread: dict[str, list[Any]] = {}
        for row in rows:
            by_thread.setdefault(row["thread_id"], []).append(row)
        segmented = {}
        passage_threads: dict[str, set[str]] = {}
        exemplar: dict[str, str] = {}
        for thread_id, variants in by_thread.items():
            if len(variants) != 1 or variants[0]["wrong_author"]:
                continue
            message = json.loads(variants[0]["raw_json"])
            parts, suppressed = _segments(message, self.signatures)
            segmented[thread_id] = (message, parts, suppressed)
            if message["thread_state"] != "published" or message["thread_type"] != "message":
                continue
            for part in parts:
                normalized = _normalize(part)
                if _substantive(normalized):
                    passage_threads.setdefault(normalized, set()).add(thread_id)
                    exemplar.setdefault(normalized, part)
        templates = {text for text, ids in passage_threads.items() if len(ids) >= 2}
        known = set()
        db.execute("DELETE FROM cr_history_templates")
        for reference in self.references:
            db.execute("INSERT OR IGNORE INTO cr_history_templates VALUES (?,?)",
                       (_hash(_json(reference)), _json(reference)))
            for passage in reference["text"].splitlines():
                if _substantive(passage):
                    known.add(_normalize(passage))
        for normalized in sorted(templates):
            reference = {"name": "Normalized repeated passage", "text": exemplar[normalized],
                         "source": "synthetic archive",
                         "thread_count": len(passage_threads[normalized])}
            db.execute("INSERT INTO cr_history_templates VALUES (?,?)",
                       (_hash(normalized), _json(reference)))
        all_templates = templates | known
        # Bounded near-match candidates: avoid pairwise corpus comparisons.
        buckets: dict[str, list[str]] = {}
        for passage in sorted(all_templates):
            for word in set(re.findall(r"[a-z]{5,}", passage)):
                entries = buckets.setdefault(word, [])
                if len(entries) < 25:
                    entries.append(passage)
        db.execute("DELETE FROM cr_history_prepared")
        for thread_id, variants in by_thread.items():
            reasons = []
            candidate = []
            suppressed: list[dict[str, str]] = []
            status = "included"
            if len(variants) > 1:
                status, reasons = "held", ["conflicting_thread_id"]
            elif variants[0]["wrong_author"]:
                status, reasons = "held", ["wrong_author"]
            else:
                message, parts, suppressed = segmented[thread_id]
                if message["thread_state"] == "bounced":
                    status, reasons = "excluded", ["bounced"]
                elif message["thread_type"] != "message":
                    status, reasons = "excluded", ["forward"]
                for part in parts:
                    normalized = _normalize(part)
                    if normalized in all_templates:
                        suppressed.append({"reason": "repeated_template", "text": part})
                    elif normalized == "[link]" and any(
                        _normalize(other) in all_templates for other in parts
                    ):
                        suppressed.append({"reason": "template_variable_link", "text": part})
                    else:
                        candidate.append(part)
                        if _substantive(normalized):
                            options = set()
                            for word in re.findall(r"[a-z]{5,}", normalized):
                                options.update(buckets.get(word, []))
                            if len(normalized) > 4000:
                                reasons.append("long_passage_requires_review")
                                if status == "included":
                                    status = "held"
                            elif any(
                                len(option) <= 4000
                                and min(len(normalized), len(option))
                                / max(len(normalized), len(option)) >= 0.75
                                and SequenceMatcher(
                                    None, normalized, option, autojunk=False,
                                ).ratio()
                                >= 0.84 for option in sorted(options)[:60]
                            ):
                                reasons.append("near_template_match_requires_review")
                                if status == "included":
                                    status = "held"
                if not candidate and status == "included":
                    status = "excluded"
                    reasons.append("no_substantive_prose")
                if message["source_type"] == "api":
                    reasons.append("account_attributed_api_source")
                if message["attachments"]:
                    reasons.append("attachment_metadata_only")
            prepared = {"thread_id": thread_id, "status": status,
                        "reasons": sorted(set(reasons)), "candidate_text": "\n\n".join(candidate),
                        "suppressed": suppressed, "raw_variant_count": len(variants),
                        "generator": "deterministic heuristic preparation v1",
                        "source_label": "Synthetic writing examples"}
            db.execute("INSERT INTO cr_history_prepared VALUES (?,?,?)",
                       (thread_id, status, _json(prepared)))

    def summary(self) -> dict[str, Any]:
        with self.store.read() as db:
            counts = {"included": 0, "held": 0, "excluded": 0}
            for row in db.execute(
                "SELECT status,COUNT(*) AS n FROM cr_history_prepared GROUP BY status"
            ):
                counts[row["status"]] = row["n"]
            counts["unique_threads"] = sum(counts.values())
            counts["raw_variants"] = db.execute(
                "SELECT COUNT(*) FROM cr_history_variants"
            ).fetchone()[0]
            imports = db.execute(
                "SELECT * FROM cr_history_imports "
                "ORDER BY history_through DESC,created_at DESC,import_id"
            ).fetchall()
            counts["imports"] = len(imports)
            reasons: Counter[str] = Counter()
            for row in db.execute("SELECT prepared_json FROM cr_history_prepared"):
                prepared = json.loads(row[0])
                reasons.update(set(prepared["reasons"]) | {
                    part["reason"] for part in prepared["suppressed"]
                })
            reports = []
            for index, row in enumerate(imports):
                report = json.loads(row["report_json"])
                reports.append({"import_id": row["import_id"], "report": report,
                                "older_than_latest": index > 0 and (
                                    row["history_through"], row["created_at"]) < (
                                    imports[0]["history_through"], imports[0]["created_at"]),
                                "partial": not report["run_completed"] or
                                report["coverage_status"] != "completed_two_pass_scan",
                                "duplicate_records": row["duplicate_records"]})
            references = [json.loads(row[0]) for row in db.execute(
                "SELECT reference_json FROM cr_history_templates ORDER BY fingerprint")]
        return {"schema_version": 1, "label": "Synthetic writing examples", "counts": counts,
                "reasons": dict(reasons), "coverage": reports,
                "complete_all_sent_history": False, "limitations": LIMITATIONS,
                "template_references": references, "analysis_completed": False,
                "generator": "deterministic heuristic preparation v1"}

    def candidates(self, offset: int = 0, limit: int = 50) -> dict[str, Any]:
        if (type(offset) is not int or offset < 0 or type(limit) is not int
                or not 1 <= limit <= 200):
            raise HistoryError("history_pagination_invalid")
        with self.store.read() as db:
            total = db.execute("SELECT COUNT(*) FROM cr_history_prepared").fetchone()[0]
            items = []
            for row in db.execute(
                "SELECT * FROM cr_history_prepared ORDER BY thread_id LIMIT ? OFFSET ?",
                (limit, offset),
            ):
                item = json.loads(row["prepared_json"])
                item["raw_variants"] = [json.loads(variant[0]) for variant in db.execute(
                    "SELECT raw_json FROM cr_history_variants "
                    "WHERE thread_id=? ORDER BY fingerprint",
                    (row["thread_id"],))]
                item["provenance"] = [dict(provenance) for provenance in db.execute(
                    "SELECT import_id,filename,ordinal,fingerprint FROM cr_history_provenance "
                    "WHERE thread_id=? ORDER BY import_id,filename,ordinal", (row["thread_id"],))]
                items.append(item)
        return {"items": items, "total": total, "offset": offset, "limit": limit}


def _unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise HistoryError("history_duplicate_json_key")
        value[key] = item
    return value
