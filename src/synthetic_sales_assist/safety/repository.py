"""Repository-level prohibited-content and credential-material scanners."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


IGNORED_DIRECTORIES = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "build",
        "dist",
    }
)
TEXT_SUFFIXES = frozenset(
    {
        "",
        ".cfg",
        ".css",
        ".editorconfig",
        ".gitignore",
        ".ini",
        ".js",
        ".json",
        ".md",
        ".py",
        ".sql",
        ".toml",
        ".txt",
        ".yaml",
        ".yml",
    }
)
IMPLEMENTATION_ROOTS = (
    ".editorconfig",
    ".gitattributes",
    ".gitignore",
    "DEVELOPMENT.md",
    "docs",
    "migrations",
    "pyproject.toml",
    "src",
    "tests",
    "tools",
)
PROHIBITED_ARTIFACT_SUFFIXES = frozenset(
    {
        ".db",
        ".env",
        ".gif",
        ".har",
        ".htm",
        ".html",
        ".jpeg",
        ".jpg",
        ".key",
        ".log",
        ".pem",
        ".png",
        ".sqlite",
        ".sqlite3",
        ".webp",
    }
)


def _compile_secret_patterns() -> tuple[tuple[str, re.Pattern[str]], ...]:
    private_key = "-" * 5 + "BEGIN " + "PRIVATE" + " KEY" + "-" * 5
    assignment_names = "pass" + "word|pass" + "wd|sec" + "ret|tok" + "en|api[_-]?key"
    return (
        ("private_key", re.compile(re.escape(private_key))),
        ("cloud_access_key", re.compile(r"\bA" + r"KIA[0-9A-Z]{16}\b")),
        ("source_access_token", re.compile(r"\bg" + r"hp_[A-Za-z0-9]{30,}\b")),
        ("chat_access_token", re.compile(r"\bx" + r"ox[baprs]-[A-Za-z0-9-]{20,}\b")),
        (
            "signed_web_token",
            re.compile(r"\be" + r"yJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
        ),
        (
            "credential_assignment",
            re.compile(
                rf"(?i)\b(?:{assignment_names})\b\s*[:=]\s*[\"']?[A-Za-z0-9+/_.-]{{16,}}"
            ),
        ),
        (
            "url_embedded_credential",
            re.compile(r"\b(?:ht" + r"tps?|postgres(?:ql)?|mysql)://[^\s/@:]+:[^\s/@]+@"),
        ),
    )


SECRET_PATTERNS = _compile_secret_patterns()
URL_PATTERN = re.compile(r"\bhttps?://[^\s\"'<>`]+", re.IGNORECASE)
EMAIL_PATTERN = re.compile(
    r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@"
    r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+(?![A-Za-z0-9.-])"
)
CAPTURED_HTML_PATTERN = re.compile(r"<\s*(?:!doctype\s+html|html\b)", re.IGNORECASE)


@dataclass(frozen=True, slots=True, order=True)
class RepositoryFinding:
    category: str
    path: str
    line: int

    def to_dict(self) -> dict[str, object]:
        return {"category": self.category, "path": self.path, "line": self.line}


def _is_within(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root)
    except ValueError:
        return False
    return True


def _walk_files(root: Path, selected: tuple[str, ...] | None = None) -> list[Path]:
    roots = selected or (".",)
    files: set[Path] = set()
    for relative in roots:
        start = root / relative
        if not start.exists():
            continue
        if start.is_file() or start.is_symlink():
            files.add(start)
            continue
        for directory, directory_names, file_names in os.walk(start, followlinks=False):
            current = Path(directory)
            traversable_directories: list[str] = []
            for name in sorted(directory_names):
                candidate = current / name
                if candidate.is_symlink():
                    files.add(candidate)
                elif name not in IGNORED_DIRECTORIES:
                    traversable_directories.append(name)
            directory_names[:] = traversable_directories
            for name in sorted(file_names):
                files.add(current / name)
    return sorted(files)


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _read_text(path: Path) -> str | None:
    if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in TEXT_SUFFIXES:
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def scan_secret_material(root: Path) -> tuple[RepositoryFinding, ...]:
    """Scan all repository text for high-confidence credential material."""

    root = root.resolve()
    findings: set[RepositoryFinding] = set()
    for path in _walk_files(root):
        relative = path.relative_to(root).as_posix() if _is_within(root, path) else path.name
        if path.is_symlink() or not _is_within(root, path):
            findings.add(RepositoryFinding("linked_or_external_path", relative, 0))
            continue
        text = _read_text(path)
        if text is None:
            continue
        for category, pattern in SECRET_PATTERNS:
            for match in pattern.finditer(text):
                findings.add(
                    RepositoryFinding(category, relative, _line_number(text, match.start()))
                )
    return tuple(sorted(findings))


def _url_is_permitted_literal(value: str) -> bool:
    try:
        parsed = urlsplit(value.rstrip(".,);]"))
    except ValueError:
        return False
    return (
        parsed.scheme.lower() in {"http", "https"}
        and parsed.username is None
        and parsed.password is None
        and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    )


def scan_prohibited_repository_content(root: Path) -> tuple[RepositoryFinding, ...]:
    """Scan implementation artifacts while leaving immutable supplied prose untouched."""

    root = root.resolve()
    findings: set[RepositoryFinding] = set()
    for path in _walk_files(root, IMPLEMENTATION_ROOTS):
        relative = path.relative_to(root).as_posix() if _is_within(root, path) else path.name
        if path.is_symlink() or not _is_within(root, path):
            findings.add(RepositoryFinding("linked_or_external_path", relative, 0))
            continue
        if path.suffix.lower() in PROHIBITED_ARTIFACT_SUFFIXES:
            findings.add(RepositoryFinding("prohibited_artifact_type", relative, 0))
            continue
        text = _read_text(path)
        if text is None:
            continue
        for match in URL_PATTERN.finditer(text):
            if not _url_is_permitted_literal(match.group(0)):
                findings.add(
                    RepositoryFinding(
                        "non_localhost_url", relative, _line_number(text, match.start())
                    )
                )
        for match in EMAIL_PATTERN.finditer(text):
            domain = match.group(0).rsplit("@", 1)[1].lower()
            if domain != "example.test":
                findings.add(
                    RepositoryFinding(
                        "non_synthetic_email", relative, _line_number(text, match.start())
                    )
                )
        for match in CAPTURED_HTML_PATTERN.finditer(text):
            findings.add(
                RepositoryFinding("captured_html", relative, _line_number(text, match.start()))
            )
    return tuple(sorted(findings))
