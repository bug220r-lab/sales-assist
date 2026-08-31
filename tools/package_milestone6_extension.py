"""SYNTHETIC-SALES-ASSIST-AUTHORED-M6

Validate and deterministically package the localhost-only Milestone 6 extension.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Final


INVENTORY_SCHEMA_VERSION: Final = (
    "synthetic-sales-assist-extension-package-inventory/v1"
)
PACKAGE_SCHEMA_VERSION: Final = "synthetic-sales-assist-extension-package/v1"
AUTHOR_MARKER: Final = "SYNTHETIC-SALES-ASSIST-AUTHORED-M6"
ALLOWED_SUFFIXES: Final = frozenset({".css", ".html", ".js", ".json", ".md"})
EXCLUDED_FROM_INVENTORY: Final = frozenset({"package_inventory.json"})
EXPECTED_PERMISSIONS: Final = ["sidePanel"]
EXPECTED_HOST_PERMISSIONS: Final = [
    "http://127.0.0.1/*",
    "http://localhost/*",
]
EXPECTED_CONTENT_MATCHES: Final = [
    "http://127.0.0.1/orders/*",
    "http://localhost/orders/*",
    "http://127.0.0.1/interactions/*",
    "http://localhost/interactions/*",
]
EXPECTED_CSP: Final = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; "
    "connect-src 'none'; object-src 'none'; base-uri 'none'; "
    "frame-ancestors 'none'"
)
MAX_SOURCE_FILE_BYTES: Final = 2 * 1024 * 1024


class PackageError(ValueError):
    """One closed package or manifest invariant failed."""


@dataclass(frozen=True)
class SnapshotFile:
    """One immutable extension source captured for a package operation."""

    path: str
    raw: bytes


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _extension_root() -> Path:
    return _repo_root() / "chrome_extension"


def _canonical_json(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )


def _is_reparse_stat(value: os.stat_result) -> bool:
    attributes = getattr(value, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse_flag)


def _is_reparse(path: Path) -> bool:
    return _is_reparse_stat(path.stat(follow_symlinks=False))


def _file_identity(value: os.stat_result) -> tuple[int, int]:
    return value.st_dev, value.st_ino


def _file_snapshot_identity(value: os.stat_result) -> tuple[int, int, int, int]:
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns


def _require_regular_unlinked(value: os.stat_result, code: str) -> None:
    if (
        not stat.S_ISREG(value.st_mode)
        or stat.S_ISLNK(value.st_mode)
        or _is_reparse_stat(value)
        or value.st_nlink != 1
    ):
        raise PackageError(code)


def _validate_source_ancestry(path: Path, repository: Path) -> None:
    current = path
    while True:
        value = current.stat(follow_symlinks=False)
        if (
            stat.S_ISLNK(value.st_mode)
            or _is_reparse_stat(value)
            or not stat.S_ISDIR(value.st_mode)
        ):
            raise PackageError("PACKAGE_REPARSE_POINT_PROHIBITED")
        if current == repository:
            return
        if current.parent == current:
            raise PackageError("PACKAGE_SOURCE_OUTSIDE_REPOSITORY")
        current = current.parent


def _read_verified_source(path: Path, root: Path) -> bytes:
    repository = _repo_root().resolve(strict=True)
    if not path.is_relative_to(root):
        raise PackageError("PACKAGE_SOURCE_OUTSIDE_EXTENSION")
    _validate_source_ancestry(path.parent, repository)
    before = path.stat(follow_symlinks=False)
    _require_regular_unlinked(before, "PACKAGE_NONREGULAR_FILE_PROHIBITED")
    resolved_before = path.resolve(strict=True)
    if not resolved_before.is_relative_to(root):
        raise PackageError("PACKAGE_SOURCE_OUTSIDE_EXTENSION")

    flags = os.O_RDONLY
    flags |= getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOINHERIT", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        _require_regular_unlinked(opened, "PACKAGE_NONREGULAR_FILE_PROHIBITED")
        if _file_snapshot_identity(opened) != _file_snapshot_identity(before):
            raise PackageError("PACKAGE_SOURCE_CHANGED_DURING_SNAPSHOT")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, 131_072)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_SOURCE_FILE_BYTES:
                raise PackageError("PACKAGE_SOURCE_FILE_TOO_LARGE")
            chunks.append(chunk)
        opened_after = os.fstat(descriptor)
        if _file_snapshot_identity(opened_after) != _file_snapshot_identity(opened):
            raise PackageError("PACKAGE_SOURCE_CHANGED_DURING_SNAPSHOT")
    finally:
        os.close(descriptor)

    after = path.stat(follow_symlinks=False)
    _require_regular_unlinked(after, "PACKAGE_NONREGULAR_FILE_PROHIBITED")
    if (
        _file_snapshot_identity(after) != _file_snapshot_identity(opened_after)
        or path.resolve(strict=True) != resolved_before
    ):
        raise PackageError("PACKAGE_SOURCE_CHANGED_DURING_SNAPSHOT")
    _validate_source_ancestry(path.parent, repository)
    return b"".join(chunks)


def _source_files() -> tuple[Path, ...]:
    unresolved_root = _extension_root()
    try:
        root_state = unresolved_root.stat(follow_symlinks=False)
    except OSError as error:
        raise PackageError("PACKAGE_ROOT_INVALID") from error
    root_attributes = getattr(root_state, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    if (
        unresolved_root.is_symlink()
        or bool(root_attributes & reparse_flag)
        or not stat.S_ISDIR(root_state.st_mode)
    ):
        raise PackageError("PACKAGE_ROOT_REPARSE_OR_NONDIRECTORY_PROHIBITED")
    root = unresolved_root.resolve(strict=True)
    repository = _repo_root().resolve(strict=True)
    _validate_source_ancestry(root, repository)
    files: list[Path] = []
    for candidate in sorted(root.rglob("*")):
        if candidate.is_dir():
            if candidate.is_symlink() or _is_reparse(candidate):
                raise PackageError("PACKAGE_REPARSE_POINT_PROHIBITED")
            continue
        if candidate.is_symlink() or _is_reparse(candidate) or not candidate.is_file():
            raise PackageError("PACKAGE_NONREGULAR_FILE_PROHIBITED")
        relative = candidate.relative_to(root)
        if candidate.suffix.casefold() not in ALLOWED_SUFFIXES:
            raise PackageError("PACKAGE_FILE_TYPE_PROHIBITED")
        if any(part.startswith(".") or part == "__pycache__" for part in relative.parts):
            raise PackageError("PACKAGE_HIDDEN_FILE_PROHIBITED")
        files.append(candidate)
    if not files or root / "manifest.json" not in files:
        raise PackageError("PACKAGE_MANIFEST_REQUIRED")
    return tuple(files)


def _snapshot_files() -> tuple[SnapshotFile, ...]:
    files = _source_files()
    root = _extension_root()
    return tuple(
        SnapshotFile(path.relative_to(root).as_posix(), _read_verified_source(path, root))
        for path in files
    )


def _snapshot_member(snapshot: tuple[SnapshotFile, ...], path: str) -> SnapshotFile:
    matches = tuple(item for item in snapshot if item.path == path)
    if len(matches) != 1:
        raise PackageError("PACKAGE_SNAPSHOT_MEMBER_INVALID")
    return matches[0]


def _record(source: SnapshotFile) -> dict[str, object]:
    return {
        "path": source.path,
        "sha256": hashlib.sha256(source.raw).hexdigest(),
        "size": len(source.raw),
    }


def _parse_json(source: SnapshotFile, code: str) -> object:
    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise PackageError(code)
            result[key] = value
        return result

    def reject_constant(_value: str) -> object:
        raise PackageError(code)

    try:
        return json.loads(
            source.raw.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError) as error:
        raise PackageError(code) from error


def _manifest_from_snapshot(snapshot: tuple[SnapshotFile, ...]) -> dict[str, object]:
    parsed = _parse_json(_snapshot_member(snapshot, "manifest.json"), "MANIFEST_JSON_INVALID")
    if not isinstance(parsed, dict):
        raise PackageError("MANIFEST_JSON_INVALID")
    return parsed


def build_inventory(
    snapshot: tuple[SnapshotFile, ...] | None = None,
) -> dict[str, object]:
    captured = _snapshot_files() if snapshot is None else snapshot
    files = [
        _record(source)
        for source in captured
        if source.path not in EXCLUDED_FROM_INVENTORY
    ]
    manifest = _manifest_from_snapshot(captured)
    return {
        "author_marker": AUTHOR_MARKER,
        "extension_version": manifest.get("version"),
        "files": files,
        "inventory_excludes": sorted(EXCLUDED_FROM_INVENTORY),
        "schema_version": INVENTORY_SCHEMA_VERSION,
    }


def _validate_manifest(snapshot: tuple[SnapshotFile, ...]) -> dict[str, object]:
    manifest = _manifest_from_snapshot(snapshot)
    source_root = _repo_root() / "src"
    if str(source_root) not in sys.path:
        sys.path.insert(0, str(source_root))
    from synthetic_sales_assist.safety.chrome import (  # noqa: PLC0415
        ChromePermissionViolation,
        validate_chrome_permissions,
    )

    try:
        validate_chrome_permissions(manifest)
    except ChromePermissionViolation as error:
        raise PackageError("MANIFEST_CLOSED_POLICY_INVALID") from error
    if manifest.get("manifest_version") != 3 or manifest.get("version") != "0.1.0":
        raise PackageError("MANIFEST_VERSION_INVALID")
    if manifest.get("permissions") != EXPECTED_PERMISSIONS:
        raise PackageError("MANIFEST_PERMISSION_INVALID")
    if manifest.get("host_permissions") != EXPECTED_HOST_PERMISSIONS:
        raise PackageError("MANIFEST_HOST_PERMISSION_INVALID")
    scripts = manifest.get("content_scripts")
    if not isinstance(scripts, list) or len(scripts) != 1:
        raise PackageError("MANIFEST_CONTENT_SCRIPT_INVALID")
    content = scripts[0]
    if (
        not isinstance(content, dict)
        or content.get("matches") != EXPECTED_CONTENT_MATCHES
        or content.get("world") != "ISOLATED"
        or content.get("run_at") != "document_idle"
    ):
        raise PackageError("MANIFEST_CONTENT_MATCH_INVALID")
    csp = manifest.get("content_security_policy")
    if not isinstance(csp, dict) or csp.get("extension_pages") != EXPECTED_CSP:
        raise PackageError("MANIFEST_CSP_INVALID")
    if "storage" in EXPECTED_PERMISSIONS or "tabs" in EXPECTED_PERMISSIONS:
        raise PackageError("MANIFEST_PERMISSION_INTERNAL_INVALID")
    return manifest


def check_package(
    snapshot: tuple[SnapshotFile, ...] | None = None,
) -> dict[str, object]:
    captured = _snapshot_files() if snapshot is None else snapshot
    manifest = _validate_manifest(captured)
    inventory_source = _snapshot_member(captured, "package_inventory.json")
    checked = _parse_json(inventory_source, "PACKAGE_INVENTORY_JSON_INVALID")
    expected = build_inventory(captured)
    if checked != expected or inventory_source.raw != _canonical_json(expected):
        raise PackageError("PACKAGE_INVENTORY_MISMATCH")
    return manifest


def _zip_bytes(snapshot: tuple[SnapshotFile, ...]) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(
        buffer,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
        strict_timestamps=True,
    ) as archive:
        for source in snapshot:
            info = zipfile.ZipInfo(source.path, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(
                info,
                source.raw,
                compress_type=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            )
    return buffer.getvalue()


def _validate_output_dir(value: str) -> Path:
    if (
        not isinstance(value, str)
        or not value
        or value.startswith(("\\\\", "//", "\\\\?\\", "\\\\.\\"))
        or "://" in value
        or re.match(r"^[A-Za-z]:[\\/]", value) is None
    ):
        raise PackageError("PACKAGE_OUTPUT_LOCAL_ABSOLUTE_PATH_REQUIRED")
    requested = Path(value)
    if not requested.is_absolute():
        raise PackageError("PACKAGE_OUTPUT_LOCAL_ABSOLUTE_PATH_REQUIRED")
    current = requested
    while True:
        if current.exists() and (current.is_symlink() or _is_reparse(current)):
            raise PackageError("PACKAGE_OUTPUT_REPARSE_POINT_PROHIBITED")
        if current.parent == current:
            break
        current = current.parent
    candidate = requested.resolve(strict=False)
    repository = _repo_root().resolve(strict=True)
    if (
        candidate == Path(candidate.anchor)
        or candidate == repository
        or candidate.is_relative_to(repository)
    ):
        raise PackageError("PACKAGE_OUTPUT_INSIDE_REPOSITORY_PROHIBITED")
    return candidate


def _validate_existing_output_dir(path: Path) -> Path:
    checked = _validate_output_dir(str(path))
    value = checked.stat(follow_symlinks=False)
    if (
        not stat.S_ISDIR(value.st_mode)
        or stat.S_ISLNK(value.st_mode)
        or _is_reparse_stat(value)
    ):
        raise PackageError("PACKAGE_OUTPUT_DIRECTORY_INVALID")
    return checked


def _validate_output_target(path: Path) -> None:
    _validate_existing_output_dir(path.parent)
    try:
        value = path.stat(follow_symlinks=False)
    except FileNotFoundError:
        return
    _require_regular_unlinked(value, "PACKAGE_OUTPUT_TARGET_INVALID")


def _atomic_write(path: Path, raw: bytes) -> None:
    _validate_output_target(path)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.tmp-", dir=path.parent
    )
    temporary = Path(temporary_name)
    created = os.fstat(descriptor)
    owned_temporary = True
    descriptor_open = True
    try:
        _require_regular_unlinked(created, "PACKAGE_OUTPUT_TEMPORARY_INVALID")
        with os.fdopen(descriptor, "wb", closefd=True) as output:
            descriptor_open = False
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        on_path = temporary.stat(follow_symlinks=False)
        _require_regular_unlinked(on_path, "PACKAGE_OUTPUT_TEMPORARY_INVALID")
        if (
            _file_identity(on_path) != _file_identity(created)
            or on_path.st_size != len(raw)
        ):
            raise PackageError("PACKAGE_OUTPUT_TEMPORARY_CHANGED")
        _validate_output_target(path)
        os.replace(temporary, path)
        owned_temporary = False
        written = path.stat(follow_symlinks=False)
        _require_regular_unlinked(written, "PACKAGE_OUTPUT_TARGET_INVALID")
        if _file_identity(written) != _file_identity(created) or written.st_size != len(raw):
            raise PackageError("PACKAGE_OUTPUT_REPLACE_INVALID")
    finally:
        if descriptor_open:
            os.close(descriptor)
        if owned_temporary:
            try:
                current = temporary.stat(follow_symlinks=False)
            except FileNotFoundError:
                current = None
            if current is not None and _file_identity(current) == _file_identity(created):
                temporary.unlink()


def _validate_generation(
    path: Path,
    expected: dict[str, bytes],
) -> None:
    directory = _validate_existing_output_dir(path)
    try:
        members = tuple(sorted(directory.iterdir(), key=lambda value: value.name.casefold()))
    except OSError as error:
        raise PackageError("PACKAGE_GENERATION_INVALID") from error
    if tuple(member.name for member in members) != tuple(
        sorted(expected, key=str.casefold)
    ):
        raise PackageError("PACKAGE_GENERATION_INVENTORY_INVALID")
    for member in members:
        try:
            before = member.stat(follow_symlinks=False)
        except OSError as error:
            raise PackageError("PACKAGE_GENERATION_MEMBER_INVALID") from error
        _require_regular_unlinked(before, "PACKAGE_GENERATION_MEMBER_INVALID")
        try:
            raw = member.read_bytes()
            after = member.stat(follow_symlinks=False)
        except OSError as error:
            raise PackageError("PACKAGE_GENERATION_MEMBER_INVALID") from error
        _require_regular_unlinked(after, "PACKAGE_GENERATION_MEMBER_INVALID")
        if (
            _file_identity(before) != _file_identity(after)
            or before.st_size != after.st_size
            or raw != expected[member.name]
        ):
            raise PackageError("PACKAGE_GENERATION_MEMBER_MISMATCH")


def _cleanup_owned_stage(
    path: Path,
    identity: tuple[int, int],
    allowed_names: frozenset[str],
) -> None:
    try:
        state = path.stat(follow_symlinks=False)
        if (
            _file_identity(state) != identity
            or not stat.S_ISDIR(state.st_mode)
            or stat.S_ISLNK(state.st_mode)
            or _is_reparse_stat(state)
        ):
            return
        members = tuple(path.iterdir())
        if any(member.name not in allowed_names for member in members):
            return
        verified: list[Path] = []
        for member in members:
            member_state = member.stat(follow_symlinks=False)
            _require_regular_unlinked(
                member_state, "PACKAGE_OUTPUT_STAGE_MEMBER_INVALID"
            )
            verified.append(member)
        for member in verified:
            member.unlink()
        path.rmdir()
    except (OSError, PackageError):
        return


def package(output_dir: Path) -> tuple[Path, str, Path, Path]:
    snapshot = _snapshot_files()
    manifest = check_package(snapshot)
    output_dir = _validate_output_dir(str(output_dir))
    output_dir.mkdir(parents=True, exist_ok=True)
    output_dir = _validate_existing_output_dir(output_dir)
    package_name = f"synthetic-sales-assist-m6-extension-{manifest['version']}.zip"
    raw = _zip_bytes(snapshot)
    digest = hashlib.sha256(raw).hexdigest()
    external_inventory = {
        "archive": package_name,
        "archive_sha256": digest,
        "archive_size": len(raw),
        "author_marker": AUTHOR_MARKER,
        "extension_version": manifest["version"],
        "files": [_record(source) for source in snapshot],
        "schema_version": PACKAGE_SCHEMA_VERSION,
    }
    inventory_name = f"{package_name}.inventory.json"
    checksum_name = f"{package_name}.sha256"
    expected = {
        package_name: raw,
        inventory_name: _canonical_json(external_inventory),
        checksum_name: f"{digest}  {package_name}\n".encode("ascii"),
    }
    generation_name = (
        f"synthetic-sales-assist-m6-extension-{manifest['version']}-{digest}"
    )
    generation_path = output_dir / generation_name
    stage_path = Path(
        tempfile.mkdtemp(prefix=".ssa-m6-package-stage-", dir=output_dir)
    )
    stage_state = stage_path.stat(follow_symlinks=False)
    if (
        not stat.S_ISDIR(stage_state.st_mode)
        or stat.S_ISLNK(stage_state.st_mode)
        or _is_reparse_stat(stage_state)
    ):
        raise PackageError("PACKAGE_OUTPUT_STAGE_INVALID")
    stage_identity = _file_identity(stage_state)
    published = False
    try:
        for name in (package_name, inventory_name, checksum_name):
            _atomic_write(stage_path / name, expected[name])
        _validate_generation(stage_path, expected)
        _validate_existing_output_dir(output_dir)
        try:
            os.rename(stage_path, generation_path)
            published = True
        except FileExistsError:
            _validate_generation(generation_path, expected)
        if published:
            published_state = generation_path.stat(follow_symlinks=False)
            if _file_identity(published_state) != stage_identity:
                raise PackageError("PACKAGE_GENERATION_PUBLICATION_INVALID")
            _validate_generation(generation_path, expected)
        package_path = generation_path / package_name
        inventory_path = generation_path / inventory_name
        checksum_path = generation_path / checksum_name
    finally:
        if not published:
            _cleanup_owned_stage(
                stage_path,
                stage_identity,
                frozenset(expected),
            )
    return package_path, digest, inventory_path, checksum_path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate or package the localhost-only Milestone 6 extension."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--check", action="store_true", help="Validate without writing output."
    )
    mode.add_argument(
        "--print-inventory",
        action="store_true",
        help="Print the canonical source inventory.",
    )
    mode.add_argument(
        "--output-dir",
        help="Write deterministic package artifacts outside the repository.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.print_inventory:
            sys.stdout.buffer.write(_canonical_json(build_inventory()))
            return 0
        if args.check:
            check_package()
            print("M6_EXTENSION_PACKAGE_CHECK = PASS")
            return 0
        if not args.output_dir:
            raise PackageError("PACKAGE_OUTPUT_DIR_REQUIRED")
        package_path, digest, inventory_path, checksum_path = package(
            _validate_output_dir(args.output_dir)
        )
        print(f"package={package_path}")
        print(f"sha256={digest}")
        print(f"inventory={inventory_path}")
        print(f"checksum={checksum_path}")
        print("M6_EXTENSION_PACKAGE = PASS")
        return 0
    except (OSError, PackageError, UnicodeError, json.JSONDecodeError, zipfile.BadZipFile) as error:
        code = str(error) if isinstance(error, PackageError) else "PACKAGE_IO_FAILED"
        print(f"M6_EXTENSION_PACKAGE = FAIL ({code})", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
