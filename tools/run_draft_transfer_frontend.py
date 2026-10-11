"""Run shipped JavaScript through actual isolated HTTP; mock all Help Scout writes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import threading
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from doi_draft_transfer.contract import text_hash
from doi_draft_transfer.store import DraftTransferStore, FILENAME
from doi_draft_transfer.ui import asset, render_page
from doi_csv_staging.review_marks import ReviewMarkStore
from synthetic_sales_assist.portal.server import PortalHTTPServer, PortalServerConfig
from synthetic_sales_assist.persistence.paths import validate_local_path
from tests.test_doi_draft_transfer import MockClient, csv_text, synthetic_row
from tests.test_doi_draft_transfer_links import expected_html, labeled_row
from doi_draft_transfer.helpscout import body_text
from tests.test_doi_csv_review_ui import fictional_csvs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node", default="node")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output = validate_local_path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    data = output / ("synthetic-" + uuid.uuid4().hex)
    data.mkdir()
    marks = ReviewMarkStore(data / "doi-reviewed-split.json")
    mock = MockClient()
    server = PortalHTTPServer(
        None,
        PortalServerConfig("127.0.0.1", 0),
        csrf_token="a" * 64,
        shutdown_token="b" * 64,
        doi_csv_review_only=True,
        draft_transfer_store=DraftTransferStore(data / FILENAME),
        draft_transfer_client=mock,
        review_mark_store=marks,
    )
    assert server.server_port != 8907
    server.doi_review_session.load(*fictional_csvs(), 0)
    binding = server.doi_review_session.reviewed_snapshot()["orders"][0]
    server.doi_review_session.set_reviewed(
        {
            "revision": 1,
            "storage_revision": 0,
            "order_id": binding["order_id"],
            "evidence_key": binding["evidence_key"],
            "reviewed": True,
        }
    )
    original_marks = hashlib.sha256(marks.path.read_bytes()).hexdigest()
    row = labeled_row()
    for name, hash_name in (
        ("selected_body_text", "selected_body_sha256"),
        ("preserved_original_body_text", "source_body_sha256"),
    ):
        row[name] = row[name].replace("\n", "\r\n")
        row[hash_name] = text_hash(row[name])
    held = synthetic_row("90000002")
    held.update(selected_body_text="", selected_body_sha256=text_hash(""), draft_status="HELD")
    fixture = {
        "origin": server.origin,
        "csrf": "a" * 64,
        "html": render_page("a" * 64).decode(),
        "js": asset("ui.js").decode(),
        "csv_text": csv_text([row, held]),
        "selected_body": row["selected_body_text"],
        "expected_preview": body_text(expected_html(row)),
        "expected_cart_url": json.loads(row["cart_links_json"])[0]["url"],
        "report_path": str(output / "frontend-result.json"),
    }
    inp = output / "frontend-synthetic-input.json"
    inp.write_text(json.dumps(fixture), encoding="utf-8")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        env = {
            k: v
            for k, v in os.environ.items()
            if k.upper() in {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP"}
        }
        result = subprocess.run(
            [args.node, str(ROOT / "tools/check_draft_transfer_frontend.mjs"), str(inp)],
            capture_output=True,
            text=True,
            timeout=90,
            env=env,
        )
        (output / "frontend.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        if result.returncode:
            print(result.stdout + result.stderr)
            return result.returncode
        assert len(mock.calls) == 1
        assert mock.calls[0]["threads"][0]["draft"] is True
        assert hashlib.sha256(marks.path.read_bytes()).hexdigest() == original_marks
        assert server.doi_review_session.snapshot()["revision"] == 1
        report = json.loads((output / "frontend-result.json").read_text())
        report.update(
            mock_help_scout_creates=1,
            real_help_scout_requests=0,
            existing_review_checks_unchanged=True,
            existing_capture_unchanged=True,
        )
        (output / "frontend-result.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report))
        return 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


if __name__ == "__main__":
    raise SystemExit(main())
