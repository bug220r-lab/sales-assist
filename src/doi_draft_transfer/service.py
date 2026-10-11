"""Explicit import, review, approval and one-row transfer commands."""

from __future__ import annotations

import copy
import secrets
import time
from datetime import datetime, timedelta, timezone

from .contract import (
    CHECKS,
    HEADERS,
    MAILBOX_ID,
    MAX_ROWS,
    USER_ID,
    TransferError,
    approval_binding,
    body_segments,
    digest,
    fresh_review,
    order_id,
    parse_csv,
    rendered_body,
    review_holds,
    row_holds,
    text_hash,
    timestamp,
    validate_review,
    validate_row,
)
from .store import DraftTransferStore, utc_now

FINAL_WRITE_STATES = {"IN_FLIGHT", "UNKNOWN", "CREATED", "CREATED_UNVERIFIED"}
EDITABLE = {"selected_body_text", "recipient_email", "reviewer_notes"}


class DraftTransferService:
    def __init__(self, store: DraftTransferStore | None, client=None):
        self.store, self.client = store, client
        self.pending = None

    def require_store(self):
        if self.store is None:
            raise TransferError("TRANSFER_STORAGE_UNAVAILABLE", 503)
        return self.store

    def index(self):
        store = self.require_store()
        with store.transaction() as con:
            rows = []
            if con is not None:
                identifiers = con.execute(
                    "SELECT order_id FROM drafts ORDER BY order_id"
                ).fetchall()
                rows = [self.summary(store.load(con, item[0])) for item in identifiers]
            return {
                "schema": "doi-draft-transfer/v1",
                "revision": store.revision(con),
                "rows": rows,
                "mailbox_id": MAILBOX_ID,
                "user_id": USER_ID,
                "transfer_configured": self.client is not None,
                "send_ready": False,
            }

    @staticmethod
    def summary(record):
        holds = review_holds(record["row"], record["review"])
        approved = (
            type(record["approval"]) is dict
            and record["approval"].get("binding")
            == approval_binding(record["row"], record["version"], record["review"])
            and not holds
        )
        return {
            "order_id": record["order_id"],
            "version": record["version"],
            "copy_version": record["row"]["copy_version"],
            "selected_body_sha256": record["row"]["selected_body_sha256"],
            "has_selected_copy": bool(record["row"]["selected_body_text"]),
            "holds": holds,
            "approved": approved,
            "review_approval": "APPROVED" if approved else "PENDING",
            "transfer": record["transfer"],
            "send_ready": False,
        }

    def detail(self, oid):
        store = self.require_store()
        with store.transaction() as con:
            record = store.load(con, order_id(oid))
            if record is None:
                raise TransferError("DRAFT_NOT_FOUND", 404)
            result = copy.deepcopy(record)
            result.update(self.summary(record))
            result["approval_binding"] = approval_binding(
                record["row"], record["version"], record["review"]
            )
            result["html_preview"] = rendered_body(record["row"]["selected_body_text"])
            result["preview_segments"] = body_segments(record["row"]["selected_body_text"])
            result["mailbox_id"], result["user_id"] = MAILBOX_ID, USER_ID
            # Return history metadata; original copy remains in the immutable row history.
            result["history"] = [
                dict(item)
                for item in con.execute(
                    "SELECT version,created_at FROM versions WHERE order_id=? ORDER BY version",
                    (oid,),
                )
            ]
            return result

    def preview_import(self, csv_text):
        rows, errors = parse_csv(csv_text)
        self.pending = None
        if errors:
            return {
                "preview_token": None,
                "errors": errors[:100],
                "error_count": len(errors),
                "rows": [],
                "can_commit": False,
            }
        store = self.require_store()
        with store.transaction() as con:
            base = store.revision(con)
            current_count = con.execute("SELECT count(*) FROM drafts").fetchone()[0] if con else 0
            summaries, additions = [], 0
            for row in rows:
                existing = store.load(con, row["order_id"])
                action = (
                    "ADD"
                    if existing is None
                    else ("UNCHANGED" if existing["row"] == row else "CONFLICT_KEEP_LOCAL")
                )
                additions += action == "ADD"
                summaries.append(
                    {
                        "order_id": row["order_id"],
                        "action": action,
                        "incoming_hash": row["selected_body_sha256"],
                        "local_hash": existing["row"]["selected_body_sha256"] if existing else None,
                        "incoming_source_hash": row["source_body_sha256"],
                        "local_source_hash": (
                            existing["row"]["source_body_sha256"] if existing else None
                        ),
                        "holds": row_holds(row),
                        "has_selected_copy": bool(row["selected_body_text"]),
                    }
                )
            if current_count + additions > MAX_ROWS:
                raise TransferError("TRANSFER_ROW_CAPACITY", 409)
        preview_nonce = secrets.token_hex(24)
        self.pending = {
            "token": preview_nonce,
            "revision": base,
            "rows": rows,
            "summaries": summaries,
            "expires": time.monotonic() + 1800,
        }
        return {
            "preview_token": preview_nonce,
            "revision": base,
            "errors": [],
            "error_count": 0,
            "rows": summaries,
            "can_commit": True,
        }

    def cancel_import(self, token):
        if self.pending and secrets.compare_digest(self.pending["token"], token):
            self.pending = None
        return {"canceled": True}

    def commit_import(self, token, revision):
        pending = self.pending
        if (
            not pending
            or type(token) is not str
            or not secrets.compare_digest(pending["token"], token)
            or time.monotonic() > pending["expires"]
        ):
            raise TransferError("IMPORT_PREVIEW_EXPIRED", 409)
        store = self.require_store()
        with store.transaction(write=True) as con:
            if (
                type(revision) is not int
                or revision != pending["revision"]
                or revision != store.revision(con)
            ):
                raise TransferError("IMPORT_REVISION_CONFLICT", 409)
            results = []
            changed = False
            for row, summary in zip(pending["rows"], pending["summaries"], strict=True):
                oid = row["order_id"]
                if summary["action"] == "ADD":
                    store.put(con, oid, 1, row, fresh_review(), None)
                    store.event(con, "IMPORTED", oid, 1, {"source_hash": digest(row)})
                    changed = True
                elif summary["action"] == "CONFLICT_KEEP_LOCAL":
                    existing = store.load(con, oid)
                    store.event(
                        con,
                        "IMPORT_CONFLICT_LOCAL_RETAINED",
                        oid,
                        existing["version"],
                        {"incoming_hash": digest(row), "local_hash": digest(existing["row"])},
                    )
                    changed = True
                results.append({"order_id": oid, "result": summary["action"]})
            if changed:
                store.bump(con)
            new_revision = store.revision(con)
        self.pending = None
        return {"revision": new_revision, "results": results, "approved_count": 0}

    @staticmethod
    def current(store, con, oid, version):
        record = store.load(con, order_id(oid))
        if record is None:
            raise TransferError("DRAFT_NOT_FOUND", 404)
        if type(version) is not int or version != record["version"]:
            raise TransferError("DRAFT_VERSION_CONFLICT", 409)
        return record

    def edit(self, oid, version, fields, review):
        if type(fields) is not dict or set(fields) != EDITABLE:
            raise TransferError("EDIT_FIELDS_INVALID")
        review = validate_review(review)
        store = self.require_store()
        with store.transaction(write=True) as con:
            record = self.current(store, con, oid, version)
            if record["transfer"] and record["transfer"]["state"] in FINAL_WRITE_STATES:
                raise TransferError("TRANSFER_RECORD_FROZEN", 409)
            row = dict(record["row"])
            row.update(fields)
            # Held source rows cannot acquire selected copy by typing into the editor.
            if (
                not record["row"]["selected_body_text"]
                and fields["selected_body_text"]
                or "SOURCE_COPY_HELD" in row_holds(record["row"])
            ):
                raise TransferError("HELD_COPY_CANNOT_BE_SELECTED", 409)
            row["selected_body_sha256"] = text_hash(row["selected_body_text"])
            if validate_row(row):
                raise TransferError("EDIT_ROW_INVALID")
            if row == record["row"] and review == record["review"]:
                return {"version": version, "changed": False}
            if row["recipient_email"] != record["row"]["recipient_email"]:
                review = copy.deepcopy(review)
                review["recipient_verified"], review["recipient_provenance"] = False, ""
            # Editing body cannot carry any order-specific review or content approval forward.
            if row["selected_body_text"] != record["row"]["selected_body_text"]:
                review = fresh_review()
            store.put(con, oid, version + 1, row, review, None)
            store.event(
                con,
                "EDIT_APPROVAL_INVALIDATED",
                oid,
                version + 1,
                {"prior_hash": digest(record["row"]), "current_hash": digest(row)},
            )
            store.bump(con)
        return {"version": version + 1, "changed": True, "approved": False}

    def approve(self, oid, version, binding, confirmation):
        if confirmation != "I_APPROVE_THIS_EXACT_HELP_SCOUT_DRAFT":
            raise TransferError("EXPLICIT_APPROVAL_REQUIRED", 409)
        store = self.require_store()
        with store.transaction(write=True) as con:
            record = self.current(store, con, oid, version)
            expected = approval_binding(record["row"], version, record["review"])
            if type(binding) is not str or not secrets.compare_digest(expected, binding):
                raise TransferError("APPROVAL_CONTENT_CONFLICT", 409)
            if review_holds(record["row"], record["review"]):
                raise TransferError("UNRESOLVED_REVIEW_HOLDS", 409)
            if record["transfer"] and record["transfer"]["state"] in FINAL_WRITE_STATES:
                raise TransferError("TRANSFER_ALREADY_RESERVED", 409)
            if record["approval"] is not None and record["approval"]["binding"] == expected:
                return {"approved": True, "binding": expected, "version": version}
            approval = {
                "binding": expected,
                "selected_body_sha256": record["row"]["selected_body_sha256"],
                "version": version,
                "recipient_email": record["row"]["recipient_email"],
                "mailbox_id": MAILBOX_ID,
                "user_id": USER_ID,
                "at_utc": utc_now(),
            }
            store.put(con, oid, version, record["row"], record["review"], approval)
            store.event(con, "EXACT_DRAFT_APPROVED", oid, version, {"binding": expected})
            store.bump(con)
        return {"approved": True, "binding": expected, "version": version}

    def transfer(self, oid, version, binding, retry=False):
        if self.client is None:
            raise TransferError("HELP_SCOUT_CONFIGURATION_REQUIRED", 503)
        store = self.require_store()
        with store.transaction(write=True) as con:
            record = self.current(store, con, oid, version)
            expected = approval_binding(record["row"], version, record["review"])
            if (
                record["approval"] is None
                or record["approval"]["binding"] != expected
                or binding != expected
                or review_holds(record["row"], record["review"])
            ):
                raise TransferError("CURRENT_EXACT_APPROVAL_REQUIRED", 409)
            previous = record["transfer"]
            if previous:
                if previous["state"] in FINAL_WRITE_STATES:
                    return dict(previous)  # Duplicate clicks/restarts never repeat the POST.
                if not retry or not previous.get("retry_allowed"):
                    raise TransferError("EXPLICIT_RETRY_REQUIRED", 409)
                until = timestamp(previous.get("retry_not_before"))
                if until and datetime.now(timezone.utc) < until:
                    raise TransferError("RATE_LIMIT_WAIT_REQUIRED", 429)
            result = {
                "state": "IN_FLIGHT",
                "retry_allowed": False,
                "operation_id": previous["operation_id"] if previous else secrets.token_hex(24),
                "approval_binding": expected,
                "version": version,
                "attempt": previous["attempt"] + 1 if previous else 1,
                "at_utc": utc_now(),
                "code": "RESERVED_BEFORE_NETWORK",
            }
            store.transfer(con, oid, result)
            store.event(con, "TRANSFER_RESERVED", oid, version, result)
            store.bump(con)
        # The durable reservation is committed before any possible network write.
        try:
            remote = self.client.create_draft(copy.deepcopy(record["row"]))
        except Exception:
            remote = {"state": "UNKNOWN", "retry_allowed": False, "code": "WRITE_OUTCOME_UNKNOWN"}
        result.update(remote)
        result["at_utc"] = utc_now()
        if result["state"] == "RATE_LIMITED":
            result["retry_not_before"] = (
                datetime.now(timezone.utc)
                + timedelta(seconds=result.get("retry_after_seconds", 60))
            ).isoformat()
        with store.transaction(write=True) as con:
            store.transfer(con, oid, result)
            store.event(con, "TRANSFER_RESULT", oid, version, result)
            store.bump(con)
        return result

    def verify_transfer(self, oid, version):
        if self.client is None:
            raise TransferError("HELP_SCOUT_CONFIGURATION_REQUIRED", 503)
        store = self.require_store()
        with store.transaction() as con:
            record = self.current(store, con, oid, version)
            result = record["transfer"]
            if not result or not result.get("conversation_id"):
                raise TransferError("KNOWN_CONVERSATION_REQUIRED", 409)
        updated = self.client.verify_draft(record["row"], result)
        with store.transaction(write=True) as con:
            store.transfer(con, oid, updated)
            store.event(con, "READ_ONLY_TRANSFER_VERIFICATION", oid, version, updated)
            store.bump(con)
        return updated

    def act(self, value):
        if type(value) is not dict or type(value.get("action")) is not str:
            raise TransferError("TRANSFER_REQUEST_INVALID")
        action = value["action"]
        fields = {
            "detail": {"order_id"},
            "preview_import": {"csv_text"},
            "cancel_import": {"preview_token"},
            "commit_import": {"preview_token", "revision"},
            "edit": {"order_id", "version", "fields", "review"},
            "approve": {"order_id", "version", "binding", "confirmation"},
            "transfer": {"order_id", "version", "binding", "retry"},
            "verify_transfer": {"order_id", "version"},
            "check_destination": set(),
        }
        if action not in fields or set(value) != fields[action] | {"action"}:
            raise TransferError("TRANSFER_REQUEST_FIELDS_INVALID")
        args = {k: v for k, v in value.items() if k != "action"}
        if "order_id" in args:
            args["oid"] = args.pop("order_id")
        if "preview_token" in args:
            args["token"] = args.pop("preview_token")
        if action == "transfer" and type(args["retry"]) is not bool:
            raise TransferError("TRANSFER_REQUEST_FIELDS_INVALID")
        if action == "check_destination":
            if self.client is None:
                raise TransferError("HELP_SCOUT_CONFIGURATION_REQUIRED", 503)
            return self.client.check_destination()
        return getattr(self, action)(**args)
