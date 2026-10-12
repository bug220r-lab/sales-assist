"""Build deterministic offline demo/source archives from one immutable local commit."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import stat
import subprocess
import sys
import tarfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
LAUNCHERS = (
    "START.cmd",
    "STOP.cmd",
    "STATUS.cmd",
    "BACKUP.cmd",
    "RESET.cmd",
    "REMOVE.cmd",
    "UPGRADE.cmd",
)
RUNTIME_PREFIXES = ("src/", "specs/", "reference/", "migrations/", "chrome_extension/", "scripts/")
RUNTIME_FILES = frozenset(
    {
        *LAUNCHERS,
        "README.md",
        "BUNDLE_MANIFEST.json",
        "SHA256SUMS.txt",
        "pyproject.toml",
        "tools/prepare_milestone7_demo.py",
        "tools/release_support.py",
        "tools/measure_demo_release.py",
        "tools/daily_policy.py",
        "docs/m8/START_HERE.txt",
        "docs/m8/MANAGER_DEMO.md",
        "docs/m8/KNOWN_LIMITATIONS.md",
        "docs/m8/THEME_PROVENANCE.md",
        "docs/doi-v7/DAILY_README.md",
        "docs/doi-v7/PRIVATE_CONFIGURATION.md",
        "docs/doi-draft-transfer.md",
        "docs/doi-draft-launch.md",
        "docs/doi-draft-transfer-readiness.md",
        "docs/doi-draft-transfer-auth-proposal.md",
        "docs/helpscout-credit-evidence.md",
        "docs/single-owner-pilots.md",
        "docs/adr/0044-isolated-helpscout-credit-evidence.md",
        "docs/adr/0045-cached-read-only-evidence-pilot.md",
        "docs/adr/0046-single-owner-two-pilot-coordinator.md",
        "docs/adr/0047-bounded-doi-combined-inputs.md",
        "docs/consolidated-review-candidate.md",
    }
)


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode()


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def safe_member(name: str) -> str:
    path = PurePosixPath(name)
    if (
        not name
        or name != path.as_posix()
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or any(character in name for character in "\\:\x00")
        or any(part.endswith((".", " ")) for part in path.parts)
        or any(
            re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", part)
            for part in path.parts
        )
    ):
        raise ValueError("RELEASE_MEMBER_PATH_INVALID")
    return name


def _git(*arguments: str) -> bytes:
    return subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", *arguments],
        cwd=ROOT,
        capture_output=True,
        check=True,
    ).stdout


def snapshot(commit: str) -> tuple[dict[str, bytes], str, int]:
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise ValueError("EXACT_COMMIT_REQUIRED")
    resolved = _git("rev-parse", "--verify", f"{commit}^{{commit}}").decode().strip()
    if resolved != commit:
        raise ValueError("COMMIT_IDENTITY_MISMATCH")
    tree = _git("rev-parse", f"{commit}^{{tree}}").decode().strip()
    timestamp = int(_git("show", "-s", "--format=%ct", commit))
    raw = _git("archive", "--format=tar", commit)
    files: dict[str, bytes] = {}
    folded: set[str] = set()
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
        for member in archive:
            if member.isdir():
                continue
            name = safe_member(member.name)
            if not member.isfile() or name.casefold() in folded:
                raise ValueError("RELEASE_LINK_OR_COLLISION_PROHIBITED")
            folded.add(name.casefold())
            if member.size > 32 * 1024 * 1024:
                raise ValueError("RELEASE_FILE_TOO_LARGE")
            stream = archive.extractfile(member)
            assert stream is not None
            files[name] = stream.read()
    return files, tree, timestamp


def zip_bytes(files: dict[str, bytes], timestamp: int, *, casefold_order: bool = False) -> bytes:
    moment = datetime.fromtimestamp(max(timestamp, 315532800), timezone.utc)
    date_time = (
        moment.year,
        moment.month,
        moment.day,
        moment.hour,
        moment.minute,
        moment.second - moment.second % 2,
    )
    output = io.BytesIO()
    seen: set[str] = set()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        ordered = (
            sorted(files.items(), key=lambda item: item[0].casefold())
            if casefold_order
            else sorted(files.items())
        )
        for name, raw in ordered:
            safe_member(name)
            if name.casefold() in seen:
                raise ValueError("RELEASE_CASE_COLLISION")
            seen.add(name.casefold())
            info = zipfile.ZipInfo(name, date_time)
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, raw, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return output.getvalue()


def build_payloads(
    files: dict[str, bytes],
    commit: str,
    tree: str,
    timestamp: int,
) -> tuple[dict[str, bytes], dict[str, object]]:
    version = re.search(rb'^version = "([0-9.]+)"', files["pyproject.toml"], re.MULTILINE)
    if version is None:
        raise ValueError("APP_VERSION_MISSING")
    app_version = version.group(1).decode()
    extension_manifest = json.loads(files["chrome_extension/manifest.json"])
    if extension_manifest["permissions"] != ["sidePanel"] or extension_manifest[
        "host_permissions"
    ] != ["http://127.0.0.1/*", "http://localhost/*"]:
        raise ValueError("EXTENSION_PERMISSION_MISMATCH")
    extension_version = extension_manifest["version"]
    extension = {
        name.removeprefix("chrome_extension/"): raw
        for name, raw in files.items()
        if name.startswith("chrome_extension/")
    }
    # The extension's published archive format uses the fixed DOS epoch and regular mode.
    extension_raw = zip_bytes(extension, 315532800, casefold_order=True)
    from tools.package_milestone6_extension import SnapshotFile, check_package

    captured_extension = tuple(
        SnapshotFile(name, raw)
        for name, raw in sorted(extension.items(), key=lambda item: item[0].casefold())
    )
    check_package(captured_extension)
    metadata: dict[str, object] = {
        "schema": "synthetic-sales-assist-release-build/v1",
        "source_commit": commit,
        "source_tree": tree,
        "source_timestamp_epoch": timestamp,
        "application_version": app_version,
        "extension_version": extension_version,
        "database_schema": 4,
        "migrations": [1, 2, 3, 4],
        "api": "synthetic-sales-assist-api/v1",
        "dom": "synthetic-sales-assist-dom/v1",
        "build_label": "synthetic-sales-assist-m8/v1",
        "runtime_tier": "WINDOWS_DEVELOPMENT_DEMO_EXTERNAL_CPYTHON_3_12",
        "codex_fallback": "DEVELOPMENT/NONPORTABLE",
        "windows_timezone_prerequisite": "tzdata==2026.3 (Apache-2.0; not bundled)",
        "release_id": f"demo-{app_version}-{commit[:12]}",
    }
    runtime = {
        name: raw
        for name, raw in files.items()
        if name in RUNTIME_FILES or name.startswith(RUNTIME_PREFIXES)
    }
    runtime = {
        name: raw.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        if name.endswith((".cmd", ".ps1"))
        else raw
        for name, raw in runtime.items()
    }
    for name in LAUNCHERS:
        if name not in runtime:
            raise ValueError("RELEASE_LAUNCHER_MISSING")
    for name in ("START_HERE.txt", "MANAGER_DEMO.md", "KNOWN_LIMITATIONS.md"):
        runtime[name] = files[f"docs/m8/{name}"]
    for name in ("DAILY_README.md", "PRIVATE_CONFIGURATION.md"):
        runtime[name] = files[f"docs/doi-v7/{name}"]
    # Bind private-policy receipts to this source snapshot, never a copied live manifest.
    source_inventory = {
        name: digest(raw)
        for name, raw in sorted(files.items())
        if name.startswith(("src/", "specs/", "migrations/", "scripts/"))
        or name in {"pyproject.toml", "tools/daily_policy.py"}
    }
    metadata.update(
        {
            "distribution_revision": "doi-v7-daily-local-20261006",
            "doi_source_payload_sha256": digest(canonical(source_inventory)),
            "daily_launch_requires_private_policy": True,
        }
    )
    runtime["release-build.json"] = canonical(metadata)
    runtime["release-payload.json"] = canonical(
        {
            "schema": "synthetic-sales-assist-release-payload/v1",
            "source_commit": commit,
            "files": {name: digest(raw) for name, raw in sorted(runtime.items())},
            "excluded_self": "release-payload.json",
        }
    )
    artifacts = {
        f"synthetic-sales-assist-{app_version}-windows-demo.zip": zip_bytes(runtime, timestamp),
        f"synthetic-sales-assist-{app_version}-source.zip": zip_bytes(files, timestamp),
        f"synthetic-sales-assist-m6-extension-{extension_version}.zip": extension_raw,
    }
    return artifacts, metadata


def build(commit: str, output: Path) -> dict[str, object]:
    # Output is external and new: an old failed build is never overwritten.
    from tools.release_support import validate_external_directory

    output = validate_external_directory(output, ROOT)
    if output.exists():
        raise ValueError("NEW_RELEASE_DIRECTORY_REQUIRED")
    files, tree, timestamp = snapshot(commit)
    artifacts, metadata = build_payloads(files, commit, tree, timestamp)
    output.mkdir(parents=True)
    for name, raw in artifacts.items():
        (output / name).write_bytes(raw)
    result = {
        **metadata,
        "artifacts": {
            name: {"sha256": digest(raw), "bytes": len(raw)} for name, raw in artifacts.items()
        },
    }
    (output / "build-manifest.json").write_bytes(canonical(result))
    (output / "SHA256SUMS.txt").write_text(
        "".join(f"{digest(raw)}  {name}\n" for name, raw in sorted(artifacts.items())),
        encoding="ascii",
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    arguments = parser.parse_args()
    print(json.dumps(build(arguments.commit, arguments.output_dir), sort_keys=True))
