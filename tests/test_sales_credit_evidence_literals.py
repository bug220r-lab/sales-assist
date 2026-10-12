"""Exact literal approvals do not exempt files, credentials, or runtime hosts."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from sales_credit_evidence.transport import API_ORIGIN
from synthetic_sales_assist.safety.repository import (
    EMAIL_PATTERN,
    URL_PATTERN,
    _reviewed_source_literal,
    _url_is_permitted_literal,
    scan_prohibited_repository_content,
    scan_secret_material,
)
from synthetic_sales_assist.safety.sales_credit_evidence_literals import (
    REVIEWED_EVIDENCE_LITERALS,
)

ROOT = Path(__file__).resolve().parents[1]
REVIEWED_FILES = (
    "docs/helpscout-credit-evidence.md",
    "src/sales_credit_evidence/demo.py",
    "src/sales_credit_evidence/transport.py",
    "tests/test_sales_credit_evidence_reader.py",
    "tests/test_sales_credit_evidence_transport.py",
)


def _source_literals(relative: str, category: str) -> set[str]:
    content = (ROOT / relative).read_text(encoding="utf-8")
    if category == "non_localhost_url":
        return {
            match.group(0)
            for match in URL_PATTERN.finditer(content)
            if not _url_is_permitted_literal(match.group(0))
        }
    assert category == "non_synthetic_email"
    return {
        match.group(0)
        for match in EMAIL_PATTERN.finditer(content)
        if match.group(0).rsplit("@", 1)[1].lower() != "example.test"
    }


def _write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_registry_contains_only_current_reviewed_paths_categories_and_literal_bytes() -> None:
    assert set(REVIEWED_EVIDENCE_LITERALS) == set(REVIEWED_FILES)
    for relative, categories in REVIEWED_EVIDENCE_LITERALS.items():
        assert set(categories) <= {"non_localhost_url", "non_synthetic_email"}
        for category, digests in categories.items():
            literals = _source_literals(relative, category)
            assert set(digests) == {
                hashlib.sha256(value.encode("utf-8")).hexdigest() for value in literals
            }
            for value in literals:
                assert _reviewed_source_literal(relative, category, value)
                assert not _reviewed_source_literal("src/unreviewed.py", category, value)
                assert not _reviewed_source_literal(relative, "credential_assignment", value)
                assert not _reviewed_source_literal(relative, category, value + "changed")


@pytest.mark.parametrize("relative", REVIEWED_FILES)
def test_registered_files_still_pass_literal_and_credential_scans(
    tmp_path: Path, relative: str
) -> None:
    # Only the five reviewed files are copied, never the surrounding repository.
    _write(tmp_path, relative, (ROOT / relative).read_text(encoding="utf-8"))
    assert scan_prohibited_repository_content(tmp_path) == ()
    assert scan_secret_material(tmp_path) == ()


def test_changed_literal_at_registered_path_remains_prohibited(tmp_path: Path) -> None:
    relative = "src/sales_credit_evidence/transport.py"
    _write(tmp_path, relative, API_ORIGIN + "/unreviewed\n")
    findings = scan_prohibited_repository_content(tmp_path)
    assert [(item.category, item.path) for item in findings] == [
        ("non_localhost_url", relative)
    ]


def test_registered_literal_at_another_path_remains_prohibited(tmp_path: Path) -> None:
    relative = "src/unreviewed.py"
    _write(tmp_path, relative, API_ORIGIN + "\n")
    findings = scan_prohibited_repository_content(tmp_path)
    assert [(item.category, item.path) for item in findings] == [
        ("non_localhost_url", relative)
    ]


def test_credentials_remain_detected_at_registered_paths(tmp_path: Path) -> None:
    relative = "src/sales_credit_evidence/transport.py"
    canary = "tok" + "en = " + repr("synthetic-" + "x" * 24)
    _write(tmp_path, relative, API_ORIGIN + "\n" + canary + "\n")
    assert scan_prohibited_repository_content(tmp_path) == ()
    findings = scan_secret_material(tmp_path)
    assert [(item.category, item.path) for item in findings] == [
        ("credential_assignment", relative)
    ]
    assert canary not in repr(findings)
