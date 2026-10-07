"""Repository-level prohibited-content and credential-material scanners."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from synthetic_sales_assist.safety.chrome import (
    ChromePermissionViolation,
    validate_chrome_permissions,
)


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
        ".cmd",
        ".bat",
        ".css",
        ".editorconfig",
        ".gitignore",
        ".htm",
        ".html",
        ".ini",
        ".js",
        ".json",
        ".md",
        ".ps1",
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
    "START.cmd",
    "STOP.cmd",
    "STATUS.cmd",
    "BACKUP.cmd",
    "RESET.cmd",
    "REMOVE.cmd",
    "UPGRADE.cmd",
    "chrome_extension",
    "docs",
    "migrations",
    "pyproject.toml",
    "scripts",
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
        ".map",
        ".pem",
        ".png",
        ".sqlite",
        ".sqlite3",
        ".webp",
    }
)

AUTHORED_M5_MARKER = "SYNTHETIC-SALES-ASSIST-AUTHORED-M5"
AUTHORED_M5_PORTAL_ROOTS = (
    "src/synthetic_sales_assist/portal",
    "src/synthetic_sales_assist/static",
)
AUTHORED_M5_PORTAL_SUFFIXES = frozenset({".css", ".htm", ".html", ".js"})
AUTHORED_M5_SCRIPT_PATHS = frozenset(
    {
        "scripts/lifecycle-common.ps1",
        "scripts/reset-demo.ps1",
        "scripts/start.ps1",
        "scripts/status.ps1",
        "scripts/stop.ps1",
    }
)
MAX_AUTHORED_M5_ASSET_BYTES = 512 * 1024
AUTHORED_M8_MARKER = "SYNTHETIC-SALES-ASSIST-AUTHORED-M8"
AUTHORED_M8_SCRIPT_PATHS = frozenset({
    "scripts/demo.ps1", "scripts/setup-daily-private.ps1",
    "START.cmd", "STOP.cmd", "STATUS.cmd", "BACKUP.cmd",
    "RESET.cmd", "REMOVE.cmd", "UPGRADE.cmd",
})
AUTHORED_M6_MARKER = "SYNTHETIC-SALES-ASSIST-AUTHORED-M6"
AUTHORED_M6_EXTENSION_ROOT = "chrome_extension"
AUTHORED_M6_EXTENSION_SUFFIXES = frozenset(
    {".css", ".html", ".js", ".json", ".md", ".ps1", ".txt"}
)
MAX_AUTHORED_M6_ASSET_BYTES = 512 * 1024
COMPANION_TEST_REFERENCE_HASHES = {
    "tests/fixtures/campaign_replies/companion-reference/replies-core.js":
        "0c2107f51084c547721d168eac0055a61e53b34e3eacbefd8d239ab8b32cd577",
    "tests/fixtures/campaign_replies/companion-reference/drafts-core.js":
        "15fa6e90a0475f95d85c46cfd9c3b50896096af2a0c8f91029eb4ae2c9cda4e1",
}
FORBIDDEN_CAPABILITY_PATH_PARTS = frozenset(
    {
        "automation",
        "browser",
        "chrome_extension",
        "connector",
        "control-center",
        "control_center",
        "dashboard",
        "extension",
        "milestone6",
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


def _is_beneath(relative: str, roots: tuple[str, ...]) -> bool:
    return any(relative == root or relative.startswith(root + "/") for root in roots)


def _is_approved_m5_portal_source(relative: str, path: Path, text: str) -> bool:
    if not _is_beneath(relative, AUTHORED_M5_PORTAL_ROOTS):
        return False
    if path.suffix.lower() not in AUTHORED_M5_PORTAL_SUFFIXES | {".py"}:
        return False
    if path.stat().st_size > MAX_AUTHORED_M5_ASSET_BYTES:
        return False
    return AUTHORED_M5_MARKER in text[:8192]


def _is_approved_m5_script(relative: str, path: Path, text: str) -> bool:
    return (
        relative in AUTHORED_M5_SCRIPT_PATHS
        and path.stat().st_size <= MAX_AUTHORED_M5_ASSET_BYTES
        and AUTHORED_M5_MARKER in text[:4096]
    )


def _is_beneath_m6_extension(relative: str) -> bool:
    return relative == AUTHORED_M6_EXTENSION_ROOT or relative.startswith(
        AUTHORED_M6_EXTENSION_ROOT + "/"
    )


def _is_approved_m6_extension_source(relative: str, path: Path, text: str) -> bool:
    return (
        _is_beneath_m6_extension(relative)
        and relative != f"{AUTHORED_M6_EXTENSION_ROOT}/manifest.json"
        and path.suffix.lower() in AUTHORED_M6_EXTENSION_SUFFIXES
        and path.stat().st_size <= MAX_AUTHORED_M6_ASSET_BYTES
        and AUTHORED_M6_MARKER in text[:8192]
    )


def _m6_manifest_is_safe(relative: str, path: Path, text: str | None) -> bool:
    if relative != f"{AUTHORED_M6_EXTENSION_ROOT}/manifest.json" or text is None:
        return False
    if path.stat().st_size > MAX_AUTHORED_M6_ASSET_BYTES:
        return False

    def reject_duplicate_members(
        pairs: list[tuple[str, object]],
    ) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ChromePermissionViolation("manifest JSON members must be unique")
            result[key] = value
        return result

    try:
        manifest = json.loads(text, object_pairs_hook=reject_duplicate_members)
        validate_chrome_permissions(manifest)
    except (json.JSONDecodeError, ChromePermissionViolation):
        return False
    return True


def _has_forbidden_capability_path(relative: str) -> bool:
    parts = tuple(part.lower() for part in Path(relative).parts)
    return any(part in FORBIDDEN_CAPABILITY_PATH_PARTS for part in parts)


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
                # A PowerShell conversion from a variable is code, not a literal
                # credential. Quoted values and literal -String operands still scan.
                tail = text[match.start():].splitlines()[0]
                if category == "credential_assignment" and re.fullmatch(
                    r"Token\s*=\s*ConvertTo-SecureString\s+-String\s+"
                    r"\$[A-Za-z_][A-Za-z0-9_]*\s+-AsPlainText\s+-Force\s*",
                    tail,
                ):
                    continue
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
    extra_launchers = tuple(path.name for path in root.iterdir()
                            if path.suffix.lower() in {".cmd", ".bat"}
                            and path.name not in IMPLEMENTATION_ROOTS)
    for path in _walk_files(root, (*IMPLEMENTATION_ROOTS, *extra_launchers)):
        relative = path.relative_to(root).as_posix() if _is_within(root, path) else path.name
        if path.is_symlink() or not _is_within(root, path):
            findings.add(RepositoryFinding("linked_or_external_path", relative, 0))
            continue
        # These immutable, test-only contracts contain legacy reference strings.
        # Any changed bytes or different location receives the normal full scan.
        expected_reference_hash = COMPANION_TEST_REFERENCE_HASHES.get(relative)
        if (expected_reference_hash is not None
                and path.stat().st_size <= MAX_AUTHORED_M5_ASSET_BYTES
                and hashlib.sha256(path.read_bytes()).hexdigest() == expected_reference_hash):
            continue
        text = _read_text(path)
        approved_extension_manifest = path.name.lower() == "manifest.json" and (
            _m6_manifest_is_safe(relative, path, text)
        )
        if path.name.lower() == "manifest.json" and not approved_extension_manifest:
            findings.add(RepositoryFinding("extension_manifest", relative, 0))
            continue
        approved_extension = (
            text is not None
            and _is_approved_m6_extension_source(relative, path, text)
        )
        if (
            _is_beneath_m6_extension(relative)
            and not approved_extension
            and not approved_extension_manifest
        ):
            findings.add(
                RepositoryFinding("unapproved_extension_artifact", relative, 0)
            )
            continue
        if (
            _has_forbidden_capability_path(relative)
            and not approved_extension
            and not approved_extension_manifest
        ):
            findings.add(RepositoryFinding("prohibited_capability_path", relative, 0))
            continue
        suffix = path.suffix.lower()
        approved_portal = (
            text is not None and _is_approved_m5_portal_source(relative, path, text)
        )
        approved_portal_asset = approved_portal and suffix in AUTHORED_M5_PORTAL_SUFFIXES
        approved_script = text is not None and (
            _is_approved_m5_script(relative, path, text)
            or (relative in AUTHORED_M8_SCRIPT_PATHS and AUTHORED_M8_MARKER in text[:4096]
                and path.stat().st_size <= MAX_AUTHORED_M5_ASSET_BYTES)
        )
        if suffix in {".cmd", ".bat"} and not approved_script:
            findings.add(RepositoryFinding("unapproved_demo_launcher", relative, 0))
            continue
        if relative.startswith("scripts/") and suffix == ".ps1" and not approved_script:
            findings.add(RepositoryFinding("unapproved_lifecycle_script", relative, 0))
            continue
        if (
            suffix in AUTHORED_M5_PORTAL_SUFFIXES
            and not approved_portal_asset
            and not approved_extension
        ):
            findings.add(RepositoryFinding("unapproved_portal_asset", relative, 0))
            continue
        if (
            suffix in PROHIBITED_ARTIFACT_SUFFIXES
            and not approved_portal_asset
            and not approved_extension
        ):
            findings.add(RepositoryFinding("prohibited_artifact_type", relative, 0))
            continue
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
        if (
            not approved_portal
            and not approved_extension
            and not approved_extension_manifest
        ):
            for match in CAPTURED_HTML_PATTERN.finditer(text):
                findings.add(
                    RepositoryFinding(
                        "captured_html",
                        relative,
                        _line_number(text, match.start()),
                    )
                )
    return tuple(sorted(findings))
