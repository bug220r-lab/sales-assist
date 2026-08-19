"""Small offline source-quality gate used when optional linters are unavailable."""

from __future__ import annotations

import ast
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = (ROOT / "src", ROOT / "tests", ROOT / "tools")
MAX_LINE_LENGTH = 100


def python_files() -> list[Path]:
    return sorted(path for root in SOURCE_ROOTS for path in root.rglob("*.py"))


def check(path: Path) -> list[str]:
    findings: list[str] = []
    text = path.read_text(encoding="utf-8")
    relative = path.relative_to(ROOT).as_posix()
    if not text.endswith("\n"):
        findings.append(f"{relative}: missing final newline")
    for number, line in enumerate(text.splitlines(), start=1):
        if line.endswith((" ", "\t")):
            findings.append(f"{relative}:{number}: trailing whitespace")
        if "\t" in line:
            findings.append(f"{relative}:{number}: tab character")
        if len(line) > MAX_LINE_LENGTH and "http" not in line:
            findings.append(f"{relative}:{number}: line exceeds {MAX_LINE_LENGTH} characters")
    try:
        ast.parse(text, filename=relative)
    except SyntaxError as error:
        findings.append(f"{relative}:{error.lineno}: {error.msg}")
    return findings


def main() -> int:
    files = python_files()
    findings = [finding for path in files for finding in check(path)]
    if findings:
        for finding in findings:
            print(finding)
        print(f"QUALITY_GATE=FAIL files={len(files)} findings={len(findings)}")
        return 1
    print(f"QUALITY_GATE=PASS files={len(files)} findings=0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
