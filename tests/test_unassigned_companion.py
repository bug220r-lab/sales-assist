"""Synthetic-only checks for the opt-in Unassigned reader companion."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch
import uuid

from companions.unassigned_inbox import cli, reader, support


def conversation(cid, *, mailbox_id=12):
    return {"id": cid, "mailboxId": mailbox_id, "status": "active",
            "assignee": None, "subject": "Synthetic inquiry",
            "primaryCustomer": {"id": 2000 + cid, "email": "buyer@example.test"},
            "createdAt": "2026-01-01T10:00:00Z", "modifiedAt": "2026-01-01T11:00:00Z"}


def context(cid):
    return {"conversation": conversation(cid), "complete": True,
            "checked_at_utc": "2026-01-01T12:00:00Z",
            "thread_coverage": {"complete": True, "ids": [cid * 10, cid * 10 + 1]},
            "threads": [
                {"id": cid * 10, "type": "customer", "state": "published",
                 "createdAt": "2026-01-01T10:00:00Z", "body": "Synthetic customer question."},
                {"id": cid * 10 + 1, "type": "note", "state": "published",
                 "createdAt": "2026-01-01T11:00:00Z", "body": "Synthetic internal note."},
            ]}


class FakeReader:
    def __init__(self, ids=(101, 102)):
        self.rows = [conversation(cid) for cid in ids]
        self.coverage = {"complete": True, "ids": list(ids), "pages_read": [{"page": 1}],
                         "unique_count": len(ids), "limitations": []}
        self.fresh = {cid: conversation(cid) for cid in ids}
        self.contexts = {cid: context(cid) for cid in ids}
        self.calls = []
        self.before_context = None

    def get_identity(self):
        self.calls.append(("identity",))
        return {"id": 73, "firstName": "Example", "lastName": "Agent",
                "email": "agent@example.test", "status": "active", "type": "user"}

    def get_user(self, uid):
        self.calls.append(("user", uid))
        return self.get_identity()

    def get_mailbox(self, mid):
        self.calls.append(("mailbox", mid))
        return {"id": mid, "name": "Example Sales", "email": "sales@example.test"}

    def list_unassigned_conversations(self, mid):
        self.calls.append(("list", mid))
        return deepcopy(self.rows), deepcopy(self.coverage)

    def get_conversation(self, cid):
        self.calls.append(("precheck", cid))
        value = self.fresh[cid]
        if isinstance(value, Exception):
            raise value
        return deepcopy(value)

    def get_context(self, cid):
        self.calls.append(("context", cid))
        if self.before_context:
            self.before_context(cid)
        value = self.contexts[cid]
        if isinstance(value, Exception):
            raise value
        return deepcopy(value)


class CompanionTests(unittest.TestCase):
    def setUp(self):
        self.allowed = Path(__file__).resolve().parents[2] / ".companion-test-runtime"
        self.root = self.allowed / uuid.uuid4().hex
        self.root.mkdir(parents=True)
        self.auth = self.root / "connection.dpapi"
        self.auth.write_bytes(b"synthetic-dpapi-blob")
        self.config_path = self.root / "config.json"
        self.config = {"schema_version": 1, "auth_path": str(self.auth),
                       "runtime_dir": str(self.root / "run"),
                       "expected_user_name": "Example Agent", "user_id_hint": 73,
                       "mailboxes": {"ecs": {"id": 12, "name": "Example Sales",
                                              "email": "sales@example.test"}}}
        self.config_path.write_text(json.dumps(self.config), encoding="utf-8")
        self.cfg = support.configuration(self.config_path)

    def tearDown(self):
        resolved = self.root.resolve()
        if resolved != self.allowed.resolve() and self.allowed.resolve() in resolved.parents:
            shutil.rmtree(resolved)

    def run_dir(self, report):
        return self.cfg["runtime_dir"] / "unassigned" / "runs" / report["run_id"]

    def record(self, report, cid):
        path = self.run_dir(report) / "records" / f"{cid}.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_requires_external_paths_and_explicit_config(self):
        with self.assertRaises(ValueError):
            support.configuration(None)
        invalid = dict(self.config)
        invalid["runtime_dir"] = str(support.REPO_ROOT / "private-runtime")
        self.config_path.write_text(json.dumps(invalid), encoding="utf-8")
        with self.assertRaises(ValueError):
            support.configuration(self.config_path)
        with self.assertRaises(ValueError):
            support.configuration(support.REPO_ROOT / "config.json")

    def test_exact_get_allowlist_rejects_conversation_writes_and_broad_search(self):
        allowed = ("/v2/conversations?mailbox=12&"
                   "query=\u0028assigned%3A%22Unassigned%22\u0029&"
                   "status=active&sortField=createdAt&sortOrder=asc&page=1")
        reader._validate_read_path(allowed)
        for path in ("/v2/conversations/101/reply", "/v2/conversations/101/threads?page=0",
                     "/v2/conversations?mailbox=12&status=active&page=1",
                     "/v2/conversations?mailbox=12&query=anything&status=active&"
                     "sortField=createdAt&sortOrder=asc&page=1"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                reader._validate_read_path(path)
        transport = reader.ReadOnlyTransport(credentials=object())
        with self.assertRaises(ValueError):
            transport.request("POST", "/v2/conversations/101/reply", {"draft": True})

    def test_complete_pagination_and_chronological_threads(self):
        class FakeTransport:
            def request(self, method, path):
                self.last_method = method
                if path.startswith("/v2/conversations/101/threads"):
                    page = int(path.split("page=")[1])
                    batch = [{"id": 1002, "createdAt": "2026-01-01T11:00:00Z"}] if page == 1 else [
                        {"id": 1001, "createdAt": "2026-01-01T10:00:00Z"}]
                    return {"status": 200, "body": {"page": {"totalElements": 2,
                                                                "totalPages": 2, "number": page},
                                                     "_embedded": {"threads": batch}}}
                page = int(path.split("page=")[1])
                batch = [conversation(101)] if page == 1 else [conversation(102)]
                return {"status": 200, "body": {"page": {"totalElements": 2,
                                                            "totalPages": 2, "number": page},
                                                 "_embedded": {"conversations": batch}}}
        client = reader.Reader(FakeTransport())
        rows, coverage = client.list_unassigned_conversations(12)
        self.assertEqual([r["id"] for r in rows], [101, 102])
        self.assertTrue(coverage["complete"])
        self.assertEqual([r["id"] for r in client.get_threads(101)], [1001, 1002])

    def test_durable_work_set_precedes_history_and_resume_uses_original_ids(self):
        fake = FakeReader((101, 102, 103))
        def verify_saved(_cid):
            files = list(self.cfg["runtime_dir"].glob("unassigned/runs/*/work-set.json"))
            self.assertEqual(len(files), 1)
            saved = json.loads(files[0].read_text(encoding="utf-8"))
            self.assertEqual(saved["conversation_ids"], [101, 102, 103])
        fake.before_context = verify_saved
        first = cli.scan(self.cfg, "ecs", max_contexts=1, reader=fake)
        self.assertEqual((first["fully_read"], first["unread"]), (1, 2))
        snapshot = (self.run_dir(first) / "work-set.json").read_bytes()
        fake.rows.append(conversation(104))
        second = cli.scan(self.cfg, "ecs", max_contexts=None, resume=first["run_id"], reader=fake)
        self.assertEqual(second["conversation_count"], 3)
        self.assertEqual(second["fully_read"], 3)
        self.assertEqual(second["threads_read"], 6)
        self.assertEqual((self.run_dir(first) / "work-set.json").read_bytes(), snapshot)
        self.assertEqual([c for c in fake.calls if c[0] == "list"], [("list", 12)])

    def test_assigned_team_or_changed_status_is_out_of_scope(self):
        fake = FakeReader((101, 102, 103))
        fake.fresh[101]["assignee"] = {"id": 9, "type": "team"}
        fake.fresh[102]["team"] = {"id": 8}
        fake.fresh[103]["status"] = "pending"
        report = cli.scan(self.cfg, "ecs", max_contexts=None, reader=fake)
        self.assertEqual(report["out_of_scope"], 3)
        self.assertEqual(report["fully_read"], 0)
        self.assertFalse(any(call[0] == "context" for call in fake.calls))

    def test_post_context_scope_change_and_incomplete_history_fail_closed(self):
        fake = FakeReader((101, 102))
        fake.contexts[101]["conversation"]["assignee"] = {"id": 9}
        fake.contexts[102]["thread_coverage"]["complete"] = False
        report = cli.scan(self.cfg, "ecs", max_contexts=None, reader=fake)
        self.assertEqual((report["out_of_scope"], report["read_failed"]), (1, 1))
        self.assertFalse(report["complete"])

    def test_authentication_failure_stops_remaining_reads_and_sanitizes_error(self):
        fake = FakeReader((101, 102))
        canary = "synthetic-secret-never-log"
        fake.fresh[101] = reader.AuthenticationError("Authentication unavailable")
        report = cli.scan(self.cfg, "ecs", max_contexts=None, reader=fake)
        self.assertEqual((report["read_failed"], report["unread"]), (1, 1))
        self.assertNotIn(("precheck", 102), fake.calls)
        fake2 = FakeReader((101,))
        fake2.contexts[101] = RuntimeError(canary)
        report2 = cli.scan(self.cfg, "ecs", max_contexts=None, reader=fake2)
        for path in self.run_dir(report2).rglob("*"):
            if path.is_file():
                self.assertNotIn(canary, path.read_text(encoding="utf-8"))

    def test_report_escapes_customer_markup_and_never_loads_remote_content(self):
        fake = FakeReader((101,))
        hostile = "<" + "script>synthetic alert</" + "script>"
        fake.contexts[101]["threads"][0]["body"] = hostile
        fake.contexts[101]["conversation"]["subject"] = hostile
        report = cli.scan(self.cfg, "ecs", max_contexts=None, reader=fake)
        html = Path(report["report_path"]).read_text(encoding="utf-8")
        self.assertNotIn(hostile, html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("default-src 'none'", html)

    def test_rejects_resume_traversal_and_scope_mismatch(self):
        fake = FakeReader((101, 102))
        first = cli.scan(self.cfg, "ecs", max_contexts=1, reader=fake)
        for value in ("../escape", "C:\\escape", "unassigned-../../escape"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                cli.scan(self.cfg, "ecs", resume=value, reader=fake)
        changed = dict(self.cfg)
        changed["mailboxes"] = {
            "ecs": {"id": 13, "name": "Example Sales", "email": "sales@example.test"}}
        with self.assertRaises(ValueError):
            cli.scan(changed, "ecs", resume=first["run_id"], reader=fake)

    def test_dpapi_read_only_decoder_is_mockable_without_local_or_network_secret(self):
        self.auth.write_bytes(b"encrypted-synthetic-blob")
        encoded = json.dumps({"access_token": "synthetic-token", "expires_at": 9999999999}).encode()
        with patch.object(reader, "decrypt_dpapi", return_value=encoded) as decoder:
            creds = reader.DPAPICredentials(self.auth)
            self.assertEqual(creds.token(), "synthetic-token")
            decoder.assert_called_once_with(b"encrypted-synthetic-blob")
        self.assertEqual(self.auth.read_bytes(), b"encrypted-synthetic-blob")


if __name__ == "__main__":
    unittest.main()
