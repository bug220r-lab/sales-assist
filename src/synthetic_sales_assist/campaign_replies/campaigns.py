"""Local synthetic campaign preparation and conservative one-attempt send ledger.

The packaged PowerShell sender remains reference-only. There is no HTTP client,
credential path, automatic worker, or production transport here. A step performs at
most one local simulation. SQLite ownership coordinates this store only; a copied
store/lock cannot authorize continuation on another PC.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import sqlite3
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, urlsplit

from synthetic_sales_assist.campaign_replies.store import Store
from synthetic_sales_assist.safety.content import assert_payload_safe
from synthetic_sales_assist.safety.identity import assert_reserved_identity, assert_synthetic_email


def encoded(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class CampaignError(ValueError):
    """Non-leaking validation or conservative send-state refusal."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise CampaignError(code)


def _object(raw: str) -> dict[str, Any]:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            require(key not in result, "DUPLICATE_JSON_KEY")
            result[key] = value
        return result
    value = json.loads(raw, object_pairs_hook=unique)
    require(isinstance(value, dict), "OBJECT_REQUIRED")
    return dict(value)


def _manifest(source: dict[str, Any]) -> dict[str, Any]:
    value = _object(encoded(source))
    require(value.get("schema_version") == 1 and value.get("profile") == "synthetic"
            and value.get("synthetic_fixture") is True, "SYNTHETIC_MANIFEST_REQUIRED")
    assert_reserved_identity(value.get("campaign_id"))
    assert_reserved_identity(value.get("sender_id"), expected_namespace="REP")
    assert_reserved_identity(value.get("inbox_id"), expected_namespace="INTERACTION")
    require(isinstance(value.get("subject"), str) and 0 < len(value["subject"]) < 300,
            "SUBJECT_REQUIRED")
    template = value.get("template")
    require(isinstance(template, str) and template.count("{cart_url}") == 1
            and len(template) < 20000, "EXACT_TEMPLATE_REQUIRED")
    records = value.get("records")
    require(isinstance(records, list) and 0 < len(records) <= 20000, "AUDIENCE_REQUIRED")
    seen_keys: set[str] = set()
    seen_emails: set[str] = set()
    seen_ranks: set[int] = set()
    for record in records:
        require(isinstance(record, dict), "RECORD_REQUIRED")
        assert_reserved_identity(record.get("queue_key"))
        assert_reserved_identity(record.get("customer_id"), expected_namespace="CUSTOMER")
        require(isinstance(record.get("email"), str), "EMAIL_REQUIRED")
        record["email"] = record["email"].strip().lower()
        assert_synthetic_email(record["email"])
        require(record["queue_key"] not in seen_keys and record["email"] not in seen_emails,
                "DUPLICATE_RECIPIENT_OR_KEY")
        seen_keys.add(record["queue_key"])
        seen_emails.add(record["email"])
        rank = record.get("original_rank")
        require(type(rank) is int and rank > 0 and rank not in seen_ranks, "ORIGINAL_RANK_INVALID")
        seen_ranks.add(rank)
        cents = record.get("cart_total_cents")
        require(type(cents) is int and 0 <= cents <= 10**12, "CART_TOTAL_INVALID")
        for flag in ("pilot_record", "address_review", "excluded"):
            require(type(record.get(flag)) is bool, "EXPLICIT_ELIGIBILITY_REQUIRED")
        require(record.get("eligibility") in {"eligible", "unknown", "ineligible"},
                "EXPLICIT_ELIGIBILITY_REQUIRED")
        cart = record.get("cart_url")
        require(isinstance(cart, str) and len(cart) < 4000, "CART_URL_REQUIRED")
        parsed = urlsplit(cart)
        require(parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"}
                and not parsed.username and not parsed.password and not parsed.fragment,
                "SYNTHETIC_LOOPBACK_CART_REQUIRED")
        params = parse_qs(parsed.query, strict_parsing=True)
        require(all(key in params for key in ("product", "qty", "pdk", "salesrep")),
                "TAGGED_CART_REQUIRED")
        for product in params["product"]:
            assert_reserved_identity(product, expected_namespace="SKU")
        for config in params["pdk"]:
            assert_reserved_identity(config)
        for rep in params["salesrep"]:
            assert_reserved_identity(rep, expected_namespace="REP")
        require(all(q.isdigit() and 0 < int(q) <= 1000 for q in params["qty"]), "QUANTITY_INVALID")
    # Subject, extra source metadata and all nested content retain the existing firewall.
    assert_payload_safe(value)
    return value


class SimulationTransport:
    """Closed local fake with explicit failure injection for protocol regression tests."""

    def __init__(self) -> None:
        self.posts: list[dict[str, Any]] = []
        self.histories: dict[str, str] = {}
        self.result_mode = "accepted"
        self.ownership_available = True
        self.authorized = True
        self.rate_budget_available = True
        self.on_create: Callable[[], None] | None = None
        self.on_history: Callable[[], None] | None = None

    def history(self, email: str) -> dict[str, Any]:
        if self.on_history:
            self.on_history()
        state = self.histories.get(email, "clear")
        return {"complete": state != "incomplete", "all_statuses": True,
                "matches": 1 if state == "found" else 0, "checked_at": now()}

    def create(self, payload: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
        self.posts.append(json.loads(encoded(payload)))
        if self.on_create:
            self.on_create()
        if self.result_mode == "lost_response":
            raise TimeoutError("SIMULATED_LOST_RESPONSE")
        if self.result_mode in {"429", "500", "missing_resource"}:
            return {"http_status": 201 if self.result_mode == "missing_resource"
                    else int(self.result_mode)}
        if self.result_mode in {"invalid_address", "other_400"}:
            return {"http_status": 400, "resource_id_absent": True,
                    "email_validation_only": self.result_mode == "invalid_address",
                    "fields": [{"path": "customer.email", "code": "Email"
                                if self.result_mode == "invalid_address" else "Other"}]}
        suffix = sha(record["campaign_id"] + record["queue_key"])[:20].upper()
        return {"http_status": 201, "conversation_id": "SYN-CONVERSATION-" + suffix,
                "anchor_thread_id": "SYN-INTERACTION-ANCHOR-" + suffix}

    def observe(self, record: dict[str, Any], receipt: dict[str, Any]) -> dict[str, Any]:
        return {"conversation_id": receipt["conversation_id"],
                "anchor_thread_id": receipt["anchor_thread_id"],
                "customer_id": record["customer_id"], "email": record["email"],
                "sender_id": record["sender_id"], "inbox_id": record["inbox_id"],
                "subject": record["subject"], "body_html": record["body_html"],
                "state": "published", "type": "message", "scheduled": None,
                "cc": [], "bcc": [], "to": [record["email"]], "complete": True,
                "outgoing_message_count": 1, "checked_at": now()}


class CampaignService:
    def __init__(self, store: Store, transport: SimulationTransport | None = None) -> None:
        self.store = store
        self.transport = transport or SimulationTransport()
        require(type(self.transport) is SimulationTransport, "SIMULATION_TRANSPORT_ONLY")
        self.owner = "SYN-RUN-WORKER-" + uuid.uuid4().hex.upper()
        with store.transaction() as db:
            db.execute("CREATE TABLE IF NOT EXISTS cr_campaigns (campaign_id TEXT PRIMARY KEY, "
                       "manifest TEXT NOT NULL, pilot TEXT NOT NULL, recovery TEXT NOT NULL, "
                       "source_hash TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS cr_campaign_records (campaign_id TEXT NOT NULL, "
                       "queue_key TEXT NOT NULL, rank INTEGER NOT NULL, record TEXT NOT NULL, "
                       'outcome TEXT NOT NULL, intent TEXT, receipt TEXT, hold TEXT, '
                       'post_error TEXT, '
                       "observation TEXT, PRIMARY KEY(campaign_id,queue_key), "
                       "FOREIGN KEY(campaign_id) REFERENCES cr_campaigns(campaign_id))")
            db.execute('CREATE TABLE IF NOT EXISTS cr_campaign_events (sequence INTEGER '
            'PRIMARY KEY, '
                       "campaign_id TEXT NOT NULL, queue_key TEXT NOT NULL, kind TEXT NOT NULL, "
                       "evidence TEXT NOT NULL, created_at TEXT NOT NULL)")
            db.execute('CREATE TABLE IF NOT EXISTS cr_campaign_writer (singleton INTEGER '
            'PRIMARY KEY '
                       "CHECK(singleton=1), campaign_id TEXT, owner TEXT, busy INTEGER NOT NULL)")
            db.execute("INSERT OR IGNORE INTO cr_campaign_writer VALUES (1,NULL,NULL,0)")
            db.execute("CREATE TABLE IF NOT EXISTS cr_campaign_transfers (digest TEXT PRIMARY KEY, "
                       "campaign_id TEXT NOT NULL, original_bundle TEXT NOT NULL)")

    def _row(self, db: sqlite3.Connection, campaign_id: str) -> sqlite3.Row:
        row = db.execute("SELECT * FROM cr_campaigns WHERE campaign_id=?", (campaign_id,
            )).fetchone()
        require(row is not None, "CAMPAIGN_NOT_FOUND")
        return row

    def _record(self, db: sqlite3.Connection, campaign_id: str, key: str) -> sqlite3.Row:
        row = db.execute("SELECT * FROM cr_campaign_records WHERE campaign_id=? AND queue_key=?",
                         (campaign_id, key)).fetchone()
        require(row is not None, "QUEUE_RECORD_NOT_FOUND")
        return row

    def _event(self, db: sqlite3.Connection, cid: str, key: str, kind: str, value: Any) -> None:
        db.execute("INSERT INTO cr_campaign_events(campaign_id,queue_key,kind,evidence,created_at) "
                   "VALUES (?,?,?,?,?)", (cid, key, kind, encoded(value), now()))

    def _insert(self, db: sqlite3.Connection, manifest_raw: str, pilot_raw: str,
                recovery_raw: str) -> None:
        manifest = _manifest(_object(manifest_raw))
        pilot = _object(pilot_raw)
        recovery = _object(recovery_raw)
        pilot_records = [r for r in manifest["records"] if r["pilot_record"]]
        require(pilot == {"schema_version": 1, "campaign_id": manifest["campaign_id"],
                          "records": pilot_records}, "PILOT_BINDING_MISMATCH")
        require(recovery.get("schema_version") == 1
                and recovery.get("campaign_id") == manifest["campaign_id"], "RECOVERY_MISMATCH")
        assert_payload_safe(recovery)
        cid = manifest["campaign_id"]
        existing = db.execute("SELECT * FROM cr_campaigns WHERE campaign_id=?", (cid,)).fetchone()
        if existing:
            require(existing["manifest"] == manifest_raw and existing["pilot"] == pilot_raw
                    and existing["recovery"] == recovery_raw, "IMMUTABLE_CAMPAIGN_CHANGED")
            return
        db.execute("INSERT INTO cr_campaigns VALUES (?,?,?,?,?,?,?)",
                   (cid, manifest_raw, pilot_raw, recovery_raw, sha(manifest_raw), "PREPARED",
                   now()))
        ordered = sorted(manifest["records"], key=lambda r: (-r["cart_total_cents"],
            r["original_rank"]))
        for rank, source in enumerate(ordered, 1):
            body = manifest["template"].replace("{cart_url}", source["cart_url"])
            record = {**source, "campaign_id": cid, "rank": rank,
                      "subject": manifest["subject"], "sender_id": manifest["sender_id"],
                      "inbox_id": manifest["inbox_id"], "body_text": body,
                      "body_html": "<div>" + html.escape(body).replace("\n", "<br>") + "</div>",
                      "fixture_sha256": sha(pilot_raw if source["pilot_record"] else manifest_raw),
                      "source_fingerprint": sha(manifest_raw), "recovery_sha256": sha(recovery_raw)}
            reason = ("EXCLUSION_HOLD" if source["excluded"]
                or source["eligibility"] == "ineligible"
                      or source["cart_total_cents"] == 0 else "ADDRESS_REVIEW_HOLD"
                      if source["address_review"] else "ELIGIBILITY_HOLD"
                      if source["eligibility"] == "unknown" else None)
            hold = self._binding(record) | {"kind": reason} if reason else None
            db.execute("INSERT INTO cr_campaign_records VALUES (?,?,?,?,?,NULL,NULL,?,NULL,NULL)",
                       (cid, source["queue_key"], rank, encoded(record), reason or "UNTOUCHED",
                        encoded(hold) if hold else None))

    def prepare_audience(self, source: dict[str, Any]) -> dict[str, Any]:
        """Create a new immutable queue; normalization is trim/lowercase only.

        Eligibility/exclusion inputs must be explicit; unknowns remain held. Missing
        original production exclusion sources cannot be reconstructed by this demo.
        """
        manifest = _manifest(source)
        pilot = {"schema_version": 1, "campaign_id": manifest["campaign_id"],
                 "records": [r for r in manifest["records"] if r["pilot_record"]]}
        recovery = {"schema_version": 1, "campaign_id": manifest["campaign_id"],
                    "known_unknown": None}
        with self.store.transaction() as db:
            self._insert(db, encoded(manifest), encoded(pilot), encoded(recovery))
        return self.detail(manifest["campaign_id"])

    @staticmethod
    def _binding(record: dict[str, Any]) -> dict[str, Any]:
        return {key: record[key] for key in ("campaign_id", "queue_key", "email", "original_rank",
                                            "fixture_sha256", "source_fingerprint")}

    @staticmethod
    def _payload(record: dict[str, Any]) -> dict[str, Any]:
        return {"type": "email", "mailboxId": record["inbox_id"], "subject": record["subject"],
                "status": "pending", "assignTo": record["sender_id"], "user": record["sender_id"],
                "autoReply": False, "customer": {"email": record["email"]},
                "threads": [{"type": "reply", "draft": False, "status": "pending",
                             "user": record["sender_id"], "customer": {"email": record["email"]},
                             "text": record["body_html"]}]}

    def preview(self, campaign_id: str, queue_key: str) -> dict[str, Any]:
        with self.store.read() as db:
            record = json.loads(self._record(db, campaign_id, queue_key)["record"])
        payload = self._payload(record)
        return {"mode": "synthetic_simulation", "record": record, "payload": payload,
                "payload_sha256": sha(encoded(payload)), "delivery": "unverified"}

    def detail(self, campaign_id: str) -> dict[str, Any]:
        with self.store.read() as db:
            campaign = dict(self._row(db, campaign_id))
            rows = db.execute("SELECT * FROM cr_campaign_records WHERE campaign_id=? ORDER BY rank",
                              (campaign_id,)).fetchall()
        records = []
        counts = {"accepted": 0, "unverified_review": 0, "unknown": 0, "held": 0, "untouched": 0}
        for row in rows:
            item = json.loads(row["record"])
            item["outcome"] = row["outcome"]
            for key in ("intent", "receipt", "hold", "post_error", "observation"):
                item[key] = json.loads(row[key]) if row[key] else None
            if item["receipt"]:
                item.update({key: item["receipt"][key] for key in
                             ("conversation_id", "anchor_thread_id", "accepted_at")})
            category = ("accepted" if row["outcome"] == "SIMULATED_ACCEPTED" else
                        "unverified_review" if row["receipt"] else "held" if row["hold"] else
                        "unknown" if row["intent"] else "untouched")
            counts[category] += 1
            records.append(item)
        return {"campaign_id": campaign_id, "status": campaign["status"], "counts": counts,
                "records": records, "source_fingerprint": campaign["source_hash"],
                "mode": "synthetic_simulation", "delivery": "unverified",
                "worker": "local simulated worker; no connection to separate PowerShell sender"}

    def list_campaigns(self) -> list[dict[str, Any]]:
        with self.store.read() as db:
            ids = [r[0] for r in db.execute('SELECT campaign_id FROM cr_campaigns ORDER BY '
            'created_at')]
        return [{key: value for key, value in self.detail(cid).items() if key != "records"}
                for cid in ids]

    def launch(self, campaign_id: str) -> dict[str, Any]:
        require(self.transport.ownership_available, "SIMULATED_OWNERSHIP_UNAVAILABLE")
        with self.store.transaction() as db:
            self._row(db, campaign_id)
            unknown = db.execute(
                "SELECT 1 FROM cr_campaign_records WHERE intent IS NOT NULL "
                "AND receipt IS NULL AND hold IS NULL"
            ).fetchone()
            require(unknown is None, "UNEXPLAINED_INTENT_BLOCKS_CAMPAIGN")
            writer = db.execute("SELECT * FROM cr_campaign_writer").fetchone()
            require(writer["owner"] in {None, self.owner}
                    and writer["campaign_id"] in {None, campaign_id} and not writer["busy"],
                    "LOCAL_WRITER_OWNERSHIP_UNAVAILABLE")
            db.execute("UPDATE cr_campaign_writer SET campaign_id=?,owner=? WHERE singleton=1",
                       (campaign_id, self.owner))
            db.execute("UPDATE cr_campaigns SET status='RUNNING' WHERE campaign_id=?",
                (campaign_id,))
        return self.detail(campaign_id)

    def resume(self, campaign_id: str) -> dict[str, Any]:
        return self.launch(campaign_id)

    def pause(self, campaign_id: str) -> dict[str, Any]:
        with self.store.transaction() as db:
            self._row(db, campaign_id)
            writer = db.execute("SELECT * FROM cr_campaign_writer").fetchone()
            busy = writer["campaign_id"] == campaign_id and writer["busy"]
            db.execute("UPDATE cr_campaigns SET status=? WHERE campaign_id=?",
                       ("PAUSE_REQUESTED" if busy else "PAUSED", campaign_id))
            if not busy and writer["campaign_id"] == campaign_id:
                db.execute("UPDATE cr_campaign_writer SET campaign_id=NULL,owner=NULL,busy=0")
        return self.detail(campaign_id)

    def _finish(self, cid: str, blocked: bool = False) -> None:
        with self.store.transaction() as db:
            campaign = self._row(db, cid)
            status = "BLOCKED" if blocked else "PAUSED" if campaign["status"] == "PAUSE_REQUESTED" \
                else campaign["status"]
            db.execute("UPDATE cr_campaigns SET status=? WHERE campaign_id=?", (status, cid))
            db.execute("UPDATE cr_campaign_writer SET busy=0 WHERE owner=?", (self.owner,))
            if status in {"BLOCKED", "PAUSED", "COMPLETED"}:
                db.execute('UPDATE cr_campaign_writer SET campaign_id=NULL,owner=NULL '
                'WHERE owner=?',
                           (self.owner,))

    def _save_receipt(self, cid: str, key: str, receipt: dict[str, Any]) -> None:
        with self.store.transaction() as db:
            row = self._record(db, cid, key)
            require(row["receipt"] is None, "RECEIPT_IMMUTABLE")
            db.execute("UPDATE cr_campaign_records SET receipt=?,outcome='ACCEPTED_UNVERIFIED' "
                       "WHERE campaign_id=? AND queue_key=?", (encoded(receipt), cid, key))
            self._event(db, cid, key, "receipt", receipt)

    def step(self, campaign_id: str) -> dict[str, Any]:
        """At most one simulated POST; durable intent is the no-retry authority."""
        require(self.transport.ownership_available and self.transport.authorized
                and self.transport.rate_budget_available, "SIMULATED_SEND_PREFLIGHT_BLOCKED")
        with self.store.transaction() as db:
            campaign = self._row(db, campaign_id)
            writer = db.execute("SELECT * FROM cr_campaign_writer").fetchone()
            require(campaign["status"] == "RUNNING" and writer["owner"] == self.owner
                    and writer["campaign_id"] == campaign_id and not writer["busy"],
                    "LOCAL_WORKER_NOT_RUNNING_OR_BUSY")
            unknown = db.execute(
                "SELECT 1 FROM cr_campaign_records WHERE intent IS NOT NULL "
                "AND receipt IS NULL AND hold IS NULL"
            ).fetchone()
            require(unknown is None, "UNEXPLAINED_INTENT_BLOCKS_CAMPAIGN")
            row = db.execute("SELECT * FROM cr_campaign_records WHERE campaign_id=? "
                             "AND intent IS NULL AND receipt IS NULL AND hold IS NULL "
                             "ORDER BY rank LIMIT 1", (campaign_id,)).fetchone()
            if row is None:
                db.execute("UPDATE cr_campaigns SET status='COMPLETED' WHERE campaign_id=?",
                           (campaign_id,))
                db.execute("UPDATE cr_campaign_writer SET campaign_id=NULL,owner=NULL,busy=0")
                record = None
            else:
                record = json.loads(row["record"])
                db.execute("UPDATE cr_campaign_writer SET busy=1 WHERE singleton=1")
        if record is None:
            return self.detail(campaign_id)
        key = record["queue_key"]
        try:
            history = self.transport.history(record["email"])
            require(history.get("complete") is True and history.get("all_statuses") is True
                    and type(history.get("matches")) is int, "FRESH_ALL_STATUS_HISTORY_INCOMPLETE")
            with self.store.transaction() as db:
                self._event(db, campaign_id, key, "fresh_history", history)
                if history["matches"]:
                    hold = self._binding(record) | {"kind": "HISTORY_HOLD", "history": history}
                    db.execute("UPDATE cr_campaign_records SET hold=?,outcome='HISTORY_HOLD' "
                               "WHERE campaign_id=? AND queue_key=?", (encoded(hold),
                               campaign_id, key))
                    admitted = False
                else:
                    admitted = self._row(db, campaign_id)["status"] == "RUNNING"
                    if admitted:
                        require(self.transport.ownership_available and self.transport.authorized
                                and self.transport.rate_budget_available, "SEND_BUDGET_CHANGED")
                        intent = self._binding(record) | {"run_id": self.owner, "created_at": now(),
                                                         "payload_sha256":
                                                         sha(encoded(self._payload(record)))}
                        db.execute("UPDATE cr_campaign_records SET intent=?,outcome='UNKNOWN' "
                                   "WHERE campaign_id=? AND queue_key=? AND intent IS NULL",
                                   (encoded(intent), campaign_id, key))
                        self._event(db, campaign_id, key, "intent", intent)
            if admitted:
                result = self.transport.create(self._payload(record), record)
                if result.get("http_status") == 400:
                    error = self._binding(record) | result | {"intent_sha256": sha(encoded(intent)),
                                                             "run_id": self.owner}
                    valid = self._email_error(error)
                    with self.store.transaction() as db:
                        db.execute('UPDATE cr_campaign_records SET post_error=? WHERE '
                        'campaign_id=? '
                                   "AND queue_key=?", (encoded(error), campaign_id, key))
                        if valid:
                            hold = self._binding(record) | {"kind": "INVALID_ADDRESS_HOLD",
                                "intent_sha256": sha(encoded(intent)), "error_sha256":
                                sha(encoded(error)),
                                "recovery_sha256": record["recovery_sha256"]}
                            db.execute('UPDATE cr_campaign_records SET '
                            "hold=?,outcome='INVALID_ADDRESS_HOLD' "
                                       "WHERE campaign_id=? AND queue_key=?", (encoded(hold),
                                       campaign_id, key))
                        self._event(db, campaign_id, key, "post_error", error)
                    require(valid, "UNSUPPORTED_HTTP400_UNKNOWN_NO_RETRY")
                else:
                    require(result.get("http_status") == 201, "UNCERTAIN_CREATION_NO_RETRY")
                    assert_reserved_identity(result.get("conversation_id"),
                        expected_namespace="CONVERSATION")
                    assert_reserved_identity(result.get("anchor_thread_id"),
                        expected_namespace="INTERACTION")
                    receipt = self._binding(record) | result | {"accepted_at": now(), "run_id":
                        self.owner}
                    self._save_receipt(campaign_id, key, receipt)
                    self.reconcile(campaign_id, key, self.transport.observe(record, receipt))
        except Exception:
            self._finish(campaign_id, blocked=True)
            raise
        self._finish(campaign_id)
        return self.detail(campaign_id)

    @staticmethod
    def _email_error(error: dict[str, Any]) -> bool:
        fields = error.get("fields")
        return (error.get("http_status") == 400 and error.get("resource_id_absent") is True
                and error.get("email_validation_only") is True and isinstance(fields, list)
                and 1 <= len(fields) <= 8 and all(isinstance(f, dict) and f.get("code") == "Email"
                and f.get("path") in {"customer.email", "threads[0].customer.email",
                                      "threads.0.customer.email"} for f in fields)
                and "conversation_id" not in error and len(encoded(error)) <= 65536)

    def _verify(self, record: dict[str, Any], receipt: dict[str, Any], obs: dict[str, Any]) -> str:
        assert_payload_safe(obs)
        for key in ("conversation_id", "anchor_thread_id"):
            require(obs.get(key) == receipt[key], "OBSERVED_ANCHOR_MISMATCH")
        for key in ("customer_id", "email", "sender_id", "inbox_id", "subject", "body_html"):
            require(obs.get(key) == record[key], "OBSERVED_BINDING_MISMATCH")
        require(obs.get("state") == "published" and obs.get("type") == "message"
                and "scheduled" in obs and obs["scheduled"] is None and obs.get("complete") is True
                and obs.get("outgoing_message_count") == 1 and obs.get("cc") == []
                and obs.get("bcc") == [], "PUBLISHED_EVIDENCE_INCOMPLETE")
        require(type(obs.get("to")) is list and obs["to"] in ([], [record["email"]]),
                "TO_HEADER_REQUIRES_REVIEW")
        return (
            "explicit_to_and_submitted_customer" if obs["to"]
            else "submitted_customer_and_published_thread"
        )

    def reconcile(self, campaign_id: str, queue_key: str,
                  observation: dict[str, Any] | None = None) -> dict[str, Any]:
        with self.store.read() as db:
            row = self._record(db, campaign_id, queue_key)
            require(row["intent"] is not None and row["receipt"] is not None,
                    "SAVED_INTENT_AND_RECEIPT_REQUIRED_NO_RETRY")
            record, receipt = json.loads(row["record"]), json.loads(row["receipt"])
        observation = (
            observation if observation is not None else self.transport.observe(record, receipt)
        )
        try:
            basis = self._verify(record, receipt, observation)
        except ValueError:
            with self.store.transaction() as db:
                db.execute("UPDATE cr_campaign_records SET outcome='REVIEW_REQUIRED' "
                           "WHERE campaign_id=? AND queue_key=?", (campaign_id, queue_key))
                self._event(db, campaign_id, queue_key, "review_required", {"reason":
                    "verification_failed"})
            raise
        observation = observation | {"recipient_verification_basis": basis,
                                     "actual_to_header_verified": bool(observation["to"]),
                                     "delivery": "unverified"}
        with self.store.transaction() as db:
            db.execute("UPDATE cr_campaign_records SET observation=?,outcome='SIMULATED_ACCEPTED' "
                       "WHERE campaign_id=? AND queue_key=?", (encoded(observation),
                       campaign_id, queue_key))
            self._event(db, campaign_id, queue_key, "observation", observation)
        return self.detail(campaign_id)

    def export_send_state(self, campaign_id: str) -> dict[str, Any]:
        """Synthetic-only byte-preserving transfer fixture; never a production sender job."""
        with self.store.read() as db:
            campaign = self._row(db, campaign_id)
            files = {"campaign.json": campaign["manifest"], "pilot.json": campaign["pilot"],
                     "recovery.json": campaign["recovery"]}
            events = [dict(row) for row in db.execute(
                "SELECT queue_key,kind,evidence,created_at FROM cr_campaign_events "
                "WHERE campaign_id=? ORDER BY sequence", (campaign_id,)
            )]
            files["audit.json"] = encoded({"events": events})
            rows = db.execute("SELECT * FROM cr_campaign_records WHERE campaign_id=?",
                              (campaign_id,)).fetchall()
            for row in rows:
                for key in ("intent", "receipt", "hold", "post_error", "observation"):
                    if row[key]:
                        files[f"records/{row['queue_key']}/{key}.json"] = row[key]
        return {"schema_version": 1, "profile": "synthetic", "synthetic_fixture": True,
                "complete": True, "files": files, "hashes": {p: sha(v) for p, v in files.items()}}

    def import_send_state(self, bundle: dict[str, Any]) -> dict[str, Any]:
        """Atomically import complete synthetic ledger bytes, never report-derived acceptances.

        Same-ID state may only add evidence; missing/changed intent, receipt or holds
        reject the whole transfer. Pilot records keep their independent fixture hash.
        """
        require(bundle.get("schema_version") == 1 and bundle.get("profile") == "synthetic"
                and bundle.get("synthetic_fixture") is True and bundle.get("complete") is True,
                "COMPLETE_SYNTHETIC_TRANSFER_REQUIRED")
        files, hashes = bundle.get("files"), bundle.get("hashes")
        require(isinstance(files, dict) and isinstance(hashes, dict) and set(files) == set(hashes)
                and len(files) <= 100003, "TRANSFER_INVENTORY_MISMATCH")
        require(sum(len(v) for v in files.values() if isinstance(v, str)) <= 50_000_000,
                "TRANSFER_TOO_LARGE")
        for path, value in files.items():
            require(isinstance(value, str) and sha(value) == hashes[path], "TRANSFER_HASH_MISMATCH")
            require(path in {"campaign.json", "pilot.json", "recovery.json", "audit.json"}
                    or re.fullmatch('records/SYN-[A-Z0-9-]+/(intent|receipt|hold|post_error'
                    '|observation)\\.json', path)
                    is not None, "UNEXPECTED_TRANSFER_PATH")
            _object(value)
        require({"campaign.json", "pilot.json", "recovery.json", "audit.json"} <= set(files),
                "IMMUTABLE_MANIFESTS_REQUIRED")
        manifest = _manifest(_object(files["campaign.json"]))
        cid = manifest["campaign_id"]
        expected_paths = {"campaign.json", "pilot.json", "recovery.json", "audit.json"}
        digest = sha(encoded(bundle))
        with self.store.transaction() as db:
            writer = db.execute("SELECT owner,busy FROM cr_campaign_writer").fetchone()
            require(writer["owner"] is None and not writer["busy"],
                    "PAUSE_LOCAL_WRITER_BEFORE_TRANSFER")
            self._insert(db, files["campaign.json"], files["pilot.json"], files["recovery.json"])
            events = _object(files["audit.json"]).get("events")
            manifest_keys = {r["queue_key"] for r in manifest["records"]}
            require(isinstance(events, list), "AUDIT_EVENTS_REQUIRED")
            existing_events = [dict(row) for row in db.execute(
                "SELECT queue_key,kind,evidence,created_at FROM cr_campaign_events "
                "WHERE campaign_id=? ORDER BY sequence", (cid,)
            )]
            require(events[:len(existing_events)] == existing_events, "STALE_AUDIT_HISTORY")
            for event in events[len(existing_events):]:
                require(isinstance(event, dict) and set(event) == {
                    "queue_key", "kind", "evidence", "created_at"
                }, "AUDIT_EVENT_INVALID")
                assert_reserved_identity(event["queue_key"])
                require(event["queue_key"] in manifest_keys
                        and event["kind"] in {"fresh_history", "intent", "receipt",
                                              "observation", "post_error", "review_required"}
                        and isinstance(event["evidence"], str)
                        and isinstance(event["created_at"], str), "AUDIT_EVENT_INVALID")
                # Ledger fields are independently validated below. Historical bytes
                # remain evidence and never grant send permission.
                evidence = _object(event["evidence"])
                if event["kind"] != "post_error":
                    assert_payload_safe(evidence)
                else:
                    structural = evidence.get("fields")
                    require(isinstance(structural, list), "AUDIT_ERROR_FIELDS_REQUIRED")
                    for field in structural:
                        require(isinstance(field, dict) and set(field) == {"path", "code"}
                                and field["path"] in {"customer.email", "threads[0].customer.email",
                                                      "threads.0.customer.email"}
                                and field["code"] in {"Email", "Other"},
                                "AUDIT_ERROR_FIELD_INVALID")
                    assert_payload_safe(evidence | {"fields": []})
                db.execute(
                    'INSERT INTO '
                    'cr_campaign_events(campaign_id,queue_key,kind,evidence,created_at) '
                    "VALUES (?,?,?,?,?)", (cid, event["queue_key"], event["kind"],
                                          event["evidence"], event["created_at"])
                )
            rows = db.execute("SELECT * FROM cr_campaign_records WHERE campaign_id=?", (cid,
                )).fetchall()
            conversation_ids: set[str] = set()
            latest_events: dict[tuple[str, str], dict[str, Any]] = {}
            latest_verification: dict[str, str] = {}
            for event in events:
                latest_events[(event["queue_key"], event["kind"])] = event
                if event["kind"] in {"observation", "review_required"}:
                    latest_verification[event["queue_key"]] = event["kind"]
            for row in rows:
                record = json.loads(row["record"])
                state: dict[str, Any] = {}
                raw: dict[str, str | None] = {}
                for kind in ("intent", "receipt", "hold", "post_error", "observation"):
                    path = f"records/{row['queue_key']}/{kind}.json"
                    expected_paths.add(path)
                    raw[kind] = files.get(path)
                    state[kind] = _object(files[path]) if path in files else None
                    known_event = latest_events.get((row["queue_key"], kind))
                    if known_event:
                        require(path in files, "AUDIT_REQUIRES_MISSING_LEDGER_FILE")
                        require(files[path] == known_event["evidence"],
                                "AUDIT_LEDGER_BYTES_MISMATCH")
                    # Every saved protection is immutable, including original exact bytes.
                    require(not row[kind] or raw[kind] == row[kind], "STALE_OR_CHANGED_LEDGER")
                    if state[kind]:
                        checked = state[kind]
                        if kind == "post_error" and isinstance(checked.get("fields"), list):
                            # These exact schema paths are tokens, not domain names.
                            checked = checked | {"fields": [
                                field | {"path": "recognized_customer_email_field"}
                                if isinstance(field, dict) and field.get("path") in {
                                    "customer.email", "threads[0].customer.email",
                                    "threads.0.customer.email",
                                } else field for field in checked["fields"]
                            ]}
                        assert_payload_safe(checked)
                        if kind != "observation":
                            require(all(state[kind].get(k) == v for k,
                                v in self._binding(record).items()),
                                    "LEDGER_BINDING_MISMATCH")
                intent, receipt, hold, error = (state[k] for k in ("intent", "receipt", "hold",
                    "post_error"))
                if intent:
                    assert_reserved_identity(intent.get("run_id"), expected_namespace="RUN")
                    require(intent.get("payload_sha256") == sha(encoded(self._payload(record))),
                            "PAYLOAD_BINDING_MISMATCH")
                if receipt:
                    require(intent is not None and not hold and receipt.get("http_status") == 201
                            and receipt.get("run_id") == intent["run_id"],
                            "RECEIPT_WITHOUT_VALID_INTENT")
                    assert_reserved_identity(receipt.get("conversation_id"),
                        expected_namespace="CONVERSATION")
                    assert_reserved_identity(receipt.get("anchor_thread_id"),
                        expected_namespace="INTERACTION")
                    require(isinstance(receipt.get("accepted_at"), str), "RECEIPT_TIME_REQUIRED")
                    require(receipt["conversation_id"] not in conversation_ids,
                            "DUPLICATE_ACCEPTED_CONVERSATION")
                    conversation_ids.add(receipt["conversation_id"])
                if error:
                    require(intent is not None and error.get("intent_sha256")
                        == sha(raw["intent"] or "")
                            and error.get("run_id") == intent["run_id"],
                            "POST_ERROR_BINDING_MISMATCH")
                if hold:
                    require(not receipt, "HOLD_RECEIPT_CONFLICT")
                    kind = hold.get("kind")
                    require(kind in {"HISTORY_HOLD", "ADDRESS_REVIEW_HOLD", "EXCLUSION_HOLD",
                            "ELIGIBILITY_HOLD", "INVALID_ADDRESS_HOLD", "UNKNOWN_REVIEW_HOLD"},
                            "HOLD_KIND_INVALID")
                    if kind in {"INVALID_ADDRESS_HOLD", "UNKNOWN_REVIEW_HOLD"}:
                        require(intent is not None and hold.get("intent_sha256")
                            == sha(raw["intent"] or "")
                                and hold.get("recovery_sha256") == sha(files["recovery.json"]),
                                "REVIEW_INTENT_HASH_MISMATCH")
                        if kind == "INVALID_ADDRESS_HOLD":
                            require(error is not None and self._email_error(error)
                                    and hold.get("error_sha256") == sha(raw["post_error"] or ""),
                                    "REVIEW_ERROR_HASH_MISMATCH")
                        else:
                            known = _object(files["recovery.json"]).get("known_unknown")
                            require(known == {"queue_key": row["queue_key"], "run_id":
                                intent["run_id"],
                                             "intent_sha256": sha(raw["intent"] or "")}
                                    and not error and not hold.get("error_sha256"),
                                    "UNKNOWN_HOLD_NOT_EXACT")
                    else:
                        require(not intent and not error, "UNATTEMPTED_HOLD_CONFLICT")
                history_event = latest_events.get((row["queue_key"], "fresh_history"))
                if history_event and _object(history_event["evidence"]).get("matches"):
                    require(hold is not None and hold["kind"] == "HISTORY_HOLD",
                            "AUDIT_REQUIRES_HISTORY_HOLD")
                obs = state["observation"]
                if obs:
                    require(receipt is not None and intent is not None,
                        "OBSERVATION_WITHOUT_RECEIPT")
                    self._verify(record, receipt, obs)
                outcome = ("SIMULATED_ACCEPTED" if obs else "ACCEPTED_UNVERIFIED" if receipt
                           else hold["kind"] if hold else "UNKNOWN" if intent else "UNTOUCHED")
                if receipt and latest_verification.get(row["queue_key"]) == "review_required":
                    outcome = "REVIEW_REQUIRED"
                db.execute('UPDATE cr_campaign_records SET '
                'outcome=?,intent=?,receipt=?,hold=?,post_error=?,'
                           "observation=? WHERE campaign_id=? AND queue_key=?",
                           (outcome, raw["intent"], raw["receipt"], raw["hold"], raw["post_error"],
                            raw["observation"], cid, row["queue_key"]))
            require(set(files) <= expected_paths, "UNDECLARED_RECORD_STATE")
            db.execute("INSERT OR IGNORE INTO cr_campaign_transfers VALUES (?,?,?)", (digest,
                cid, encoded(bundle)))
        return self.detail(cid)
