"""Independent review regressions for store ownership and closed HTTP boundaries."""

from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from synthetic_sales_assist.campaign_replies.history_fixtures import demo_history_export
from synthetic_sales_assist.campaign_replies.reply_fixtures import demo_contact, demo_snapshot
from synthetic_sales_assist.campaign_replies.store import Store
from synthetic_sales_assist.campaign_replies.web import (
    MAX_WORKSPACE_BODY_BYTES,
    WORKSPACE_API_ROUTE,
    WorkspaceError,
    WorkspaceWeb,
    page,
)
from synthetic_sales_assist.safety.repository import (
    scan_prohibited_repository_content,
    scan_secret_material,
)


class CompanionReferenceBoundaryTests(unittest.TestCase):
    def test_only_exact_reference_bytes_at_test_paths_are_allowed(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        relative = Path('tests/fixtures/campaign_replies/companion-reference/drafts-core.js')
        raw = (repository / relative).read_bytes()
        with tempfile.TemporaryDirectory(prefix='ssa-reference-boundary-') as directory:
            root = Path(directory)
            approved = root / relative
            approved.parent.mkdir(parents=True)
            approved.write_bytes(raw)
            self.assertEqual(scan_prohibited_repository_content(root), ())
            self.assertEqual(scan_secret_material(root), ())
            approved.write_bytes(raw + b'\n// altered reference\n')
            self.assertTrue(scan_prohibited_repository_content(root))
            approved.write_bytes(raw)
            copied = root / 'tests/elsewhere.js'
            copied.write_bytes(raw)
            self.assertTrue(scan_prohibited_repository_content(root))
            copied.write_text('token = ' + 'synthetic-canary-123456789', encoding='utf-8')
            self.assertTrue(scan_secret_material(root))
            approved.write_text('token = ' + 'synthetic-canary-123456789', encoding='utf-8')
            self.assertIn(relative.as_posix(), {item.path for item in scan_secret_material(root)})


class WorkspaceStoreReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory(prefix="ssa-workspace-review-")
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def test_unrelated_sqlite_is_rejected_without_schema_or_journal_mutation(self) -> None:
        path = self.root / "unrelated.sqlite3"
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute("CREATE TABLE preserved (value TEXT)")
            connection.execute("INSERT INTO preserved VALUES ('synthetic existing content')")
        before = path.read_bytes()
        members = set(self.root.iterdir())
        with self.assertRaisesRegex(ValueError, "WORKSPACE_FORMAT_INVALID"):
            Store(path)
        self.assertEqual(before, path.read_bytes())
        self.assertEqual(members, set(self.root.iterdir()))
        with closing(sqlite3.connect(path)) as connection, connection:
            self.assertEqual(connection.execute("PRAGMA journal_mode").fetchone()[0], "delete")
            self.assertEqual(connection.execute("SELECT * FROM preserved").fetchall(),
                             [("synthetic existing content",)])
            self.assertIsNone(connection.execute(
                "SELECT name FROM sqlite_master WHERE name='workspace_metadata'"
            ).fetchone())

    def test_existing_empty_or_non_sqlite_file_is_not_claimed(self) -> None:
        for content in (b"", b"Synthetic existing text file"):
            with self.subTest(content=content):
                path = self.root / f"existing-{len(content)}.sqlite3"
                path.write_bytes(content)
                with self.assertRaises(ValueError):
                    Store(path)
                self.assertEqual(path.read_bytes(), content)

    def test_foreign_metadata_format_is_rejected_unchanged(self) -> None:
        path = self.root / "foreign.sqlite3"
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute("CREATE TABLE workspace_metadata(singleton INTEGER,format TEXT)")
            connection.execute("INSERT INTO workspace_metadata VALUES(1,'synthetic-other-format')")
        before = path.read_bytes()
        with self.assertRaisesRegex(ValueError, "WORKSPACE_FORMAT_INVALID"):
            Store(path)
        self.assertEqual(before, path.read_bytes())

    def test_existing_store_reopens_and_rolls_back_failed_transaction(self) -> None:
        path = self.root / "workspace.sqlite3"
        store = Store(path)
        with store.transaction() as connection:
            connection.execute("CREATE TABLE test_rows(value TEXT)")
            connection.execute("INSERT INTO test_rows VALUES('preserved synthetic')")
        with self.assertRaisesRegex(RuntimeError, "injected"):
            with store.transaction() as connection:
                connection.execute("INSERT INTO test_rows VALUES('rollback synthetic')")
                raise RuntimeError("injected")
        with Store(path).read() as connection:
            self.assertEqual([tuple(row) for row in connection.execute("SELECT * FROM test_rows")],
                             [("preserved synthetic",)])

    def test_deleted_owned_store_is_not_silently_recreated(self) -> None:
        path = self.root / "workspace.sqlite3"
        store = Store(path)
        path.unlink()
        with self.assertRaisesRegex(ValueError, "WORKSPACE_STORE_UNAVAILABLE"):
            with store.transaction():
                self.fail("Deleted store must not be recreated implicitly")
        self.assertFalse(path.exists())

    def test_replaced_database_is_rejected_before_writable_connection(self) -> None:
        path = self.root / "workspace.sqlite3"
        store = Store(path)
        path.unlink()
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute("CREATE TABLE other_content(value TEXT)")
        before = path.read_bytes()
        with self.assertRaisesRegex(ValueError, "WORKSPACE_FORMAT_INVALID"):
            with store.transaction():
                self.fail("Replaced store must not be written")
        self.assertEqual(before, path.read_bytes())

    def test_concurrent_initializers_preserve_one_valid_store(self) -> None:
        path = self.root / "workspace.sqlite3"
        with ThreadPoolExecutor(max_workers=4) as executor:
            stores = list(executor.map(lambda _: Store(path), range(4)))
        with stores[0].read() as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM workspace_metadata").fetchone()[0], 1,
            )

    def test_relative_repository_and_network_paths_are_rejected(self) -> None:
        invalid = ["relative.sqlite3", Path(__file__).resolve().parents[1] / "review.sqlite3",
                   "\\\\synthetic-host\\share\\workspace.sqlite3"]
        for path in invalid:
            with self.subTest(path=path), self.assertRaises(ValueError):
                Store(path)


class WorkspaceWebReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory(prefix="ssa-workspace-web-review-")
        self.addCleanup(directory.cleanup)
        self.web = WorkspaceWeb(Path(directory.name) / "workspace.sqlite3")

    def test_closed_routes_reject_suffix_and_unknown_route(self) -> None:
        for path in ("/arbitrary.js", "/arbitrary.css", "/arbitrary", "/api/other"):
            with self.subTest(path=path), self.assertRaisesRegex(
                WorkspaceError, "WORKSPACE_ROUTE_INVALID",
            ):
                self.web.get(path, "", "a" * 64)

    def test_json_duplicate_keys_nonfinite_values_and_deep_nesting_rejected(self) -> None:
        payloads = [b'{"action":"demo","action":"demo"}', b'{"action":NaN}',
                    b'{"action":Infinity}', b'{"action":-Infinity}',
                    b"[" * 2000 + b"0" + b"]" * 2000, b"\xff"]
        for payload in payloads:
            with self.subTest(payload=payload[:50]), self.assertRaises(WorkspaceError):
                self.web.post(payload)
        self.assertEqual(self.web.application.campaigns.list_campaigns(), [])

    def test_direct_boundary_enforces_same_body_limit_as_http_server(self) -> None:
        with self.assertRaisesRegex(WorkspaceError, "WORKSPACE_REQUEST_SIZE_INVALID"):
            self.web.post(b" " * (MAX_WORKSPACE_BODY_BYTES + 1))

    def test_query_duplicates_unknown_scope_and_wrong_action_are_rejected(self) -> None:
        queries = ["view=campaigns&view=history", "view=queue&profile=production",
                   "view=queue&needs_reply=maybe", "view=queue&offset=-1",
                   "view=queue&offset=100001",
                   "view=campaigns&broken", "&".join(["view=queue"] * 10)]
        for query in queries:
            with self.subTest(query=query), self.assertRaises(WorkspaceError):
                self.web.get(WORKSPACE_API_ROUTE, query, "a" * 64)
        for payload in ({"action": "send-live"}, {"action": "demo", "profile": "production"}):
            with self.subTest(payload=payload), self.assertRaises(WorkspaceError):
                self.web.post(json.dumps(payload).encode())

    def test_evidence_is_returned_only_as_json_not_interpolated_into_html(self) -> None:
        inert = '<img src="/synthetic-missing" onerror="syntheticTest()">'
        with patch.object(self.web.application, "get", return_value={"body": inert}):
            content_type, body = self.web.get(
                WORKSPACE_API_ROUTE, "view=conversation&id=x", "a" * 64,
            )
        self.assertEqual(content_type, "application/json; charset=utf-8")
        self.assertEqual(json.loads(body)["data"]["body"], inert)
        self.assertNotIn(inert.encode(), page("a" * 64))
        with self.assertRaises(WorkspaceError):
            page(inert)

    def test_conversation_renders_attachment_metadata_and_review_notes_as_inert_text(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node runtime unavailable; workspace rendering requires Node")
        snapshot = demo_snapshot(1)
        snapshot["contacts"] = [demo_contact(3, variation=True)]
        self.web.application.replies.import_snapshot(snapshot)
        contact = snapshot["contacts"][0]
        detail = self.web.application.replies.detail(contact["conversation_id"])
        queue = self.web.application.replies.list_queue()
        inert = '<img onerror="syntheticTest()">'
        detail["proposal"]["notes"].append(inert)
        script = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
class Element {
  constructor(tag) {
    this.tag = tag; this.children = []; this.textContent = ''; this.value = '';
    this.listeners = {};
  }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; }
  addEventListener(name, callback) { this.listeners[name] = callback; }
  setAttribute() {}
  set innerHTML(value) { throw Error('Inert evidence must never enter innerHTML'); }
}
const nodes = new Map();
const document = {
  createElement: tag => new Element(tag),
  getElementById: id => {
    if (!nodes.has(id)) nodes.set(id, new Element('section'));
    return nodes.get(id);
  },
  querySelector: () => ({content: 'a'.repeat(64)}),
  querySelectorAll: () => [],
};
document.getElementById('sort').value = 'priority';
document.getElementById('needs-reply').value = 'true';
const fetch = async url => {
  const view = new URL(url, 'http://127.0.0.1').searchParams.get('view');
  assert.ok(['queue', 'conversation'].includes(view));
  return {ok: true, json: async () => ({data: view === 'queue' ? input.queue : input.detail})};
};
const walk = node => [node, ...node.children.flatMap(walk)];
const visibleText = node => node.tag === 'details' ? '' :
  node.textContent + '\n' + node.children.map(visibleText).join('\n');
const settle = async () => { for (let i=0;i<5;i++) await new Promise(setImmediate); };
(async () => {
  vm.runInNewContext(fs.readFileSync(process.argv[1], 'utf8'), {
    document, location: {pathname: '/replies'}, fetch, URLSearchParams, Intl,
  });
  await settle();
  const open = walk(document.getElementById('reply-queue')).find(n => n.tag === 'button');
  assert.ok(open);
  open.listeners.click();
  await settle();
  const root = document.getElementById('conversation');
  const visible = visibleText(root);
  for (const attachment of input.detail.threads.flatMap(t => t._embedded.attachments)) {
    assert.ok(visible.includes(attachment.filename),
      'Attachment filename must be visible outside collapsed evidence');
    assert.ok(visible.includes(String(attachment.size)), 'Attachment size must be visible');
    assert.ok(visible.includes(attachment.state), 'Attachment state must be visible');
  }
  for (const note of input.detail.proposal.notes) {
    assert.ok(visible.includes(note), 'Proposal review note must be visible');
  }
  assert.ok(visible.includes('contents are unseen'));
  assert.equal(walk(root).some(n => n.tag === 'img'), false);
  assert.equal(walk(root).find(n => n.tag === 'textarea').value, input.detail.proposal.body);
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
        asset = Path(__file__).resolve().parents[1] / "src/synthetic_sales_assist/portal"
        result = subprocess.run(
            [node, "-e", script, str(asset / "campaign_workspace.js")],
            input=json.dumps({"queue": queue, "detail": detail}), text=True,
            capture_output=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_unexpected_service_error_does_not_echo_rejected_payload(self) -> None:
        with patch.object(self.web.application, "get", side_effect=ValueError("untrusted details")):
            with self.assertRaisesRegex(WorkspaceError, "^WORKSPACE_INPUT_REJECTED$"):
                self.web.get(WORKSPACE_API_ROUTE, "view=campaigns", "a" * 64)

    def test_history_offset_pages_existing_records_without_regeneration(self) -> None:
        self.web.application.history.import_export(**demo_history_export())
        _, body = self.web.get(WORKSPACE_API_ROUTE, "view=history&offset=2", "a" * 64)
        data = json.loads(body)["data"]
        self.assertEqual(data["candidates"]["offset"], 2)
        self.assertEqual(data["candidates"]["total"], 10)
        self.assertEqual(len(data["candidates"]["items"]), 8)
        self.assertEqual(data["candidates"]["items"][0]["thread_id"],
                         "SYN-INTERACTION-HISTORY-003")
        self.assertEqual(data["summary"]["counts"]["imports"], 1)
        _, body = self.web.get(WORKSPACE_API_ROUTE, "view=history&offset=100000", "a" * 64)
        self.assertEqual(json.loads(body)["data"]["candidates"]["items"], [])

    def test_history_offset_and_view_members_are_closed(self) -> None:
        for offset in ("-1", "100001", "invalid", "1" * 50, "", "1.5"):
            with self.subTest(offset=offset), self.assertRaisesRegex(
                WorkspaceError, "WORKSPACE_OFFSET_INVALID",
            ):
                self.web.get(WORKSPACE_API_ROUTE, "view=history&offset=" + offset, "a" * 64)
        for query in ("view=history&campaign_id=SYN-EVIDENCE-CAMPAIGN",
                      "view=suppressions&offset=0", "view=suppressions&id=SYN-EVIDENCE-CAMPAIGN"):
            with self.subTest(query=query), self.assertRaises(WorkspaceError):
                self.web.get(WORKSPACE_API_ROUTE, query, "a" * 64)

    def test_suppression_view_and_campaign_evidence_remain_read_only_candidates(self) -> None:
        demo = json.loads(self.web.post(b'{"action":"demo"}'))["data"]
        _, body = self.web.get(WORKSPACE_API_ROUTE, "view=suppressions", "a" * 64)
        candidates = json.loads(body)["data"]
        self.assertFalse(candidates["enforced_by_running_sender"])
        self.assertTrue(candidates["requires_adapter_review"])
        self.assertGreater(len(candidates["candidates"]), 0)
        self.assertTrue(all(item["category"] in {"optout", "bounce"}
                            for item in candidates["candidates"]))
        _, body = self.web.get(
            WORKSPACE_API_ROUTE, "view=campaign&id=" + demo["campaign_id"], "a" * 64,
        )
        self.assertEqual(json.loads(body)["data"]["suppression_candidates"], candidates)
