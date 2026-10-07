"""Disposable synthetic policy files for real daily-launcher integration tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def configure_synthetic_daily_policy(data_dir: Path) -> None:
    """Write a nonempty exact-case policy outside the test application package.

    These invented hashes cannot match customer captures. The numeric order token
    is required by the CSV policy parser and belongs only to this generated fixture.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    policy = {
        "schema": "doi-owner-confirmations/v1",
        "summary_text_sha256": "a" * 64,
        "lines_text_sha256": "b" * 64,
        "decisions": [{
            "order_id": "101",
            "summary_ordinal": 2,
            "record_sha256": "c" * 64,
            "confirmed_at": "2026-01-01T00:00:00Z",
            "evidence_reference": "SYN-DAILY-LAUNCH-TEST",
        }],
    }
    raw = json.dumps(policy, sort_keys=True).encode("utf-8")
    policy_path = data_dir / "synthetic-launch-policy.json"
    policy_path.write_bytes(raw)
    config = {
        "schema": "ssa-doi-private-launch/v1",
        "confirmation_path": str(policy_path),
        "confirmation_sha256": hashlib.sha256(raw).hexdigest(),
        "expected_decision_count": 1,
    }
    (data_dir / "doi-private-launch.json").write_text(
        json.dumps(config, sort_keys=True), encoding="utf-8",
    )
