"""Offline release integrity, first-run preparation, extraction, and conservative removal."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import stat
import sys
import uuid
import zipfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


WORKSPACE_FORMAT = "synthetic-campaign-workspace/v1"
WORKSPACE_TABLES = frozenset({
    "workspace_metadata", "cr_campaigns", "cr_campaign_records", "cr_campaign_events",
    "cr_campaign_writer", "cr_campaign_transfers", "cr_reply_schema", "cr_snapshots",
    "cr_reply_sync", "cr_reply_contacts", "cr_local_drafts", "cr_draft_versions",
    "cr_style_profiles", "cr_reply_projection_schema", "cr_history_imports",
    "cr_history_files", "cr_history_variants", "cr_history_provenance",
    "cr_history_prepared", "cr_history_templates",
})


def safe_member(name: str) -> str:
    path = PurePosixPath(name)
    if (
        not name or name != path.as_posix() or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or any(character in name for character in "\\:\x00")
        or any(part.endswith((".", " ")) for part in path.parts)
        or any(re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", part)
               for part in path.parts)
    ):
        raise ValueError("RELEASE_MEMBER_PATH_INVALID")
    return name


def assert_unlinked(path: Path) -> None:
    if str(path).startswith(("\\\\", "//")) or ":" in str(path)[len(path.drive):]:
        raise ValueError("RELEASE_LOCAL_PATH_REQUIRED")
    for candidate in (path, *path.parents):
        if candidate.exists() or candidate.is_symlink():
            metadata = candidate.lstat()
            if candidate.is_symlink() or getattr(metadata, "st_file_attributes", 0) & 0x400:
                raise ValueError("RELEASE_REPARSE_POINT_PROHIBITED")
            if stat.S_ISREG(metadata.st_mode) and metadata.st_nlink != 1:
                raise ValueError("RELEASE_HARD_LINK_PROHIBITED")


def atomic_json(path: Path, value: object) -> None:
    assert_unlinked(path)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write((json.dumps(value, indent=2) + "\n").encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        assert_unlinked(path)
        assert_unlinked(temporary)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            assert_unlinked(temporary)
            temporary.unlink()


def validate_external_directory(path: Path, source: Path) -> Path:
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("ABSOLUTE_RELEASE_DIRECTORY_REQUIRED")
    if str(path).startswith(("\\\\", "//")) or ":" in str(path)[len(path.drive):]:
        raise ValueError("RELEASE_LOCAL_PATH_REQUIRED")
    assert_unlinked(path)
    resolved = path.resolve()
    if resolved == Path(resolved.anchor) or resolved.is_relative_to(source.resolve()):
        raise ValueError("RELEASE_OUTPUT_MUST_BE_EXTERNAL")
    if os.name == "nt":
        import ctypes

        if ctypes.windll.kernel32.GetDriveTypeW(resolved.anchor) == 4:
            raise ValueError("RELEASE_NETWORK_DRIVE_PROHIBITED")
    return resolved


def extract_archive(archive_path: Path, destination: Path) -> None:
    destination = validate_external_directory(destination, Path(__file__).resolve().parents[1])
    if destination.exists():
        raise ValueError("NEW_EXTRACTION_DIRECTORY_REQUIRED")
    assert_unlinked(archive_path)
    with zipfile.ZipFile(archive_path) as archive:
        members = archive.infolist()
        names: set[str] = set()
        total = 0
        for member in members:
            name = safe_member(member.filename)
            mode = member.external_attr >> 16
            total += member.file_size
            if (
                member.is_dir() or stat.S_ISLNK(mode) or name.casefold() in names
                or (stat.S_IFMT(mode) not in {0, stat.S_IFREG})
                or member.file_size > 32 * 1024 * 1024 or total > 256 * 1024 * 1024
            ):
                raise ValueError("RELEASE_ARCHIVE_MEMBER_INVALID")
            names.add(name.casefold())
        destination.mkdir(parents=True)
        for member in members:
            target = destination / member.filename
            assert_unlinked(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(archive.read(member))


def _inventory(root: Path) -> dict[str, str]:
    assert_unlinked(root)
    if (root / ".git").exists():
        raise ValueError("DEVELOPMENT_CHECKOUT_PROHIBITED")
    for name in ("release-build.json", "release-payload.json"):
        assert_unlinked(root / name)
    build = json.loads((root / "release-build.json").read_text(encoding="utf-8"))
    inventory = json.loads((root / "release-payload.json").read_text(encoding="utf-8"))
    if (
        build.get("schema") != "synthetic-sales-assist-release-build/v1"
        or inventory.get("schema") != "synthetic-sales-assist-release-payload/v1"
        or inventory.get("source_commit") != build.get("source_commit")
        or inventory.get("excluded_self") != "release-payload.json"
        or re.fullmatch(r"[0-9a-f]{40}", str(build.get("source_commit"))) is None
        or type(inventory.get("files")) is not dict
    ):
        raise ValueError("RELEASE_METADATA_INVALID")
    files = inventory["files"]
    folded: set[str] = set()
    for name, digest in files.items():
        safe_member(name)
        if name.casefold() in folded or re.fullmatch(r"[0-9a-f]{64}", str(digest)) is None:
            raise ValueError("RELEASE_INVENTORY_INVALID")
        if name == "release-payload.json" or name.split("/")[0].casefold() in {
            ".git", "data", "backups", "runtime", "logs", "profiles",
        }:
            raise ValueError("RELEASE_PROTECTED_MEMBER")
        folded.add(name.casefold())
    return files


def verify_installation(root: Path) -> dict[str, object]:
    assert_unlinked(root)
    root = root.resolve()
    files = _inventory(root)
    for name, expected in files.items():
        target = root / name
        assert_unlinked(target)
        if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != expected:
            raise ValueError("RELEASE_PAYLOAD_MISMATCH")
    return {"status": "PASS", "verified_files": len(files)}


@contextmanager
def _read_database(path: Path):
    for candidate in (path, path.with_name(path.name + "-wal"),
                      path.with_name(path.name + "-shm")):
        assert_unlinked(candidate)
    if not path.is_file():
        raise ValueError("APPLICATION_DATABASE_MISSING")
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5)
    try:
        connection.execute("BEGIN")
        yield connection
    finally:
        connection.rollback()
        connection.close()


def _verify_core(path: Path) -> None:
    from synthetic_sales_assist.persistence.schema import verify_database

    with _read_database(path) as connection:
        connection.row_factory = sqlite3.Row
        verify_database(connection, deep=True)


def _verify_workspace(connection: sqlite3.Connection) -> None:
    """Require the identified complete workspace before opening it for writes."""
    try:
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )}
        if tables != WORKSPACE_TABLES or connection.execute(
            "SELECT singleton,format FROM workspace_metadata"
        ).fetchall() != [(1, WORKSPACE_FORMAT)]:
            raise ValueError("WORKSPACE_FORMAT_INVALID")
        if (connection.execute("SELECT version FROM cr_reply_schema").fetchall() != [(1,)]
                or connection.execute(
                    "SELECT singleton,version FROM cr_reply_projection_schema"
                ).fetchall() != [(1, 1)]):
            raise ValueError("WORKSPACE_SCHEMA_UNSUPPORTED")
        if (connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]
                or connection.execute("PRAGMA foreign_key_check").fetchall()):
            raise ValueError("WORKSPACE_DATABASE_VERIFICATION_FAILED")
    except sqlite3.DatabaseError:
        raise ValueError("WORKSPACE_FORMAT_INVALID") from None


def _preflight_workspace(path: Path, previous: dict | None) -> bool:
    assert_unlinked(path)
    if not path.exists():
        if previous and previous.get("campaign_workspace_format"):
            raise ValueError("WORKSPACE_DATABASE_MISSING")
        return False
    with _read_database(path) as connection:
        _verify_workspace(connection)
    return True


def _logical_digest(connection: sqlite3.Connection) -> str:
    digest = hashlib.sha256()
    for statement in connection.iterdump():
        digest.update(statement.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _backup_workspace(path: Path, destination: Path) -> dict[str, str]:
    """Copy a reserved workspace snapshot, verifying content as well as SQLite health."""
    assert_unlinked(destination)
    # Exclusive creation never replaces an existing database, including an empty one.
    with destination.open("xb"):
        pass
    with _read_database(path) as source:
        _verify_workspace(source)
        expected = _logical_digest(source)
        target = sqlite3.connect(destination, timeout=5)
        try:
            source.backup(target)
            target.execute("PRAGMA journal_mode=DELETE")
        finally:
            target.close()
    with _read_database(destination) as target:
        _verify_workspace(target)
        if _logical_digest(target) != expected:
            raise ValueError("WORKSPACE_BACKUP_CONTENT_MISMATCH")
    with destination.open("r+b") as stream:
        os.fsync(stream.fileno())
    return {"filename": destination.name, "format": WORKSPACE_FORMAT,
            "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
            "logical_sha256": expected}


def _create_application_backup(paths, metadata: dict, previous: dict | None,
                               prefix: str) -> dict[str, object]:
    from synthetic_sales_assist.persistence.backup import (
        create_backup, receipt_path, verify_backup,
    )
    from synthetic_sales_assist.persistence.database import SQLiteDatabase

    workspace_path = paths.data / "campaign_replies.sqlite3"
    workspace_exists = _preflight_workspace(workspace_path, previous)
    _verify_core(paths.database)
    name = prefix + "-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    name += "-" + uuid.uuid4().hex[:12]
    core_path = paths.backups / (name + ".sqlite3")
    companion_dir = paths.backups / "workspace"
    manifests = paths.backups / "app-manifests"
    # Subdirectories keep workspace copies out of the core-only backup retention scanner.
    for folder in (paths.backups, companion_dir, manifests):
        assert_unlinked(folder)
        folder.mkdir(parents=True, exist_ok=True)
    manifest_path = manifests / (name + ".json")
    assert_unlinked(manifest_path)
    reservation = None
    try:
        if workspace_exists:
            reservation = sqlite3.connect(workspace_path, timeout=5, isolation_level=None)
            reservation.execute("BEGIN IMMEDIATE")
            _verify_workspace(reservation)
        # The reservation prevents workspace edits during the independently verified
        # core snapshot and companion copy; this is not a cross-database transaction.
        receipt = create_backup(SQLiteDatabase(paths.database), core_path)
        if verify_backup(core_path) != receipt:
            raise ValueError("UPGRADE_BACKUP_VERIFICATION_FAILED")
        companion = _backup_workspace(
            workspace_path, companion_dir / (name + ".sqlite3"),
        ) if workspace_exists else None
        manifest = {
            "schema": "synthetic-sales-assist-application-backup/v1",
            "status": "BACKUP_VERIFIED", "source_release": previous,
            "source_release_status": "RECORDED" if previous else "NOT_VERIFIED",
            "created_by_release": metadata,
            "core": {"filename": core_path.name, "sha256": receipt.backup_sha256,
                     "receipt_filename": receipt_path(core_path).name,
                     "receipt_sha256": hashlib.sha256(
                         receipt_path(core_path).read_bytes()
                     ).hexdigest(),
                     "source_database_sha256": receipt.source_database_sha256},
            "campaign_workspace": companion,
            "campaign_workspace_status": (
                "BACKUP_VERIFIED" if companion else "ABSENT_LEGACY_CORE_ONLY"
            ),
            "restore_policy": "STOP_APPLICATION_AND_RESTORE_MATCHING_PAIR_WITH_MANIFEST",
        }
        # A successful manifest is published only after both copies have verified. If
        # any step fails, retain existing backup evidence and never advance readiness.
        with manifest_path.open("xb") as stream:
            stream.write((json.dumps(manifest, indent=2) + "\n").encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        return {"status": "BACKUP_VERIFIED", "manifest_path": str(manifest_path),
                "core_backup_sha256": receipt.backup_sha256,
                "campaign_backup_sha256": companion["sha256"] if companion else None,
                "campaign_workspace_status": manifest["campaign_workspace_status"]}
    finally:
        if reservation is not None:
            reservation.rollback()
            reservation.close()


def backup_application(root: Path, data_dir: Path,
                       prefix: str = "demo-backup") -> dict[str, object]:
    if prefix not in {"demo-backup", "pre-reset"}:
        raise ValueError("APPLICATION_BACKUP_PREFIX_INVALID")
    verify_installation(root)
    sys.path.insert(0, str(root / "src"))
    from synthetic_sales_assist.persistence.paths import resolve_data_paths

    paths = resolve_data_paths(data_dir)
    marker = paths.root / "demo-release.json"
    assert_unlinked(marker)
    previous = json.loads(marker.read_text(encoding="utf-8")) if marker.exists() else None
    metadata = json.loads((root / "release-build.json").read_text(encoding="utf-8"))
    return _create_application_backup(paths, metadata, previous, prefix)


def prepare(root: Path, data_dir: Path, allow_upgrade: bool) -> dict[str, object]:
    verify_installation(root)
    sys.path.insert(0, str(root / "src"))
    sys.path.insert(0, str(root / "tools"))
    from prepare_milestone7_demo import prepare_demo
    from synthetic_sales_assist.persistence.paths import resolve_data_paths
    from synthetic_sales_assist.campaign_replies.application import WorkspaceApplication

    metadata = json.loads((root / "release-build.json").read_text(encoding="utf-8"))
    paths = resolve_data_paths(data_dir)
    paths.ensure_directories()
    marker = paths.root / "demo-release.json"
    routes = paths.root / "demo-routes.json"
    assert_unlinked(marker)
    assert_unlinked(routes)
    existing = paths.database.exists()
    if not existing and (marker.exists() or routes.exists()):
        raise ValueError("FRESH_DEMO_METADATA_ALREADY_EXISTS")
    previous = json.loads(marker.read_text(encoding="utf-8")) if marker.exists() else None
    workspace_path = paths.data / "campaign_replies.sqlite3"
    workspace_exists = _preflight_workspace(workspace_path, previous)
    if workspace_exists and not existing:
        raise ValueError("ORPHAN_WORKSPACE_REQUIRES_REVIEW")
    if existing:
        _verify_core(paths.database)
    changed = previous is None or previous.get("source_commit") != metadata["source_commit"]
    backup = None
    if existing and changed:
        if not allow_upgrade:
            raise ValueError("EXISTING_DATA_REQUIRES_EXPLICIT_UPGRADE")
        backup = _create_application_backup(paths, metadata, previous, "before-upgrade")
    if not existing:
        seed = prepare_demo(paths.root)
        atomic_json(routes, seed)
    if not workspace_exists:
        WorkspaceApplication(workspace_path).post({"action": "demo"})
    _verify_core(paths.database)
    _preflight_workspace(workspace_path, previous)
    if changed or not previous.get("campaign_workspace_format"):
        atomic_json(marker, {**metadata, "campaign_workspace_format": WORKSPACE_FORMAT})
    return {"status": "READY", "fresh_seed": not existing,
            "campaign_fresh_seed": not workspace_exists, "campaign_workspace": "READY",
            "upgrade_backup_sha256": backup["core_backup_sha256"] if backup else None,
            "upgrade_backup_manifest": backup["manifest_path"] if backup else None}


def configured_data_root(root: Path, chosen: Path | None = None) -> dict[str, str]:
    _inventory(root)
    metadata = json.loads((root / "release-build.json").read_text(encoding="utf-8"))
    release_id = metadata["release_id"]
    if re.fullmatch(r"demo-[0-9]+\.[0-9]+\.[0-9]+-[0-9a-f]{12}", release_id) is None:
        raise ValueError("RELEASE_ID_INVALID")
    settings_root = Path(os.environ["LOCALAPPDATA"]) / "SyntheticSalesAssist" / "completion"
    install_key = hashlib.sha256(os.path.normcase(str(root.resolve())).encode("utf-8")).hexdigest()
    settings_root = validate_external_directory(settings_root / release_id / install_key[:24], root)
    settings = settings_root / "selected-data-root.json"
    assert_unlinked(settings)
    if chosen is not None:
        chosen = validate_external_directory(chosen, root)
        settings_root.mkdir(parents=True, exist_ok=True)
        atomic_json(settings, {"schema": "synthetic-demo-data-root/v1", "data_dir": str(chosen)})
    elif settings.exists():
        value = json.loads(settings.read_text(encoding="utf-8"))
        if set(value) != {"schema", "data_dir"} or value["schema"] != "synthetic-demo-data-root/v1":
            raise ValueError("DEMO_DATA_ROOT_CONFIGURATION_INVALID")
        chosen = validate_external_directory(Path(value["data_dir"]), root)
    else:
        chosen = settings_root / "demo-data"
    return {"data_dir": str(chosen)}


def reseed(root: Path, data_dir: Path) -> dict[str, object]:
    verify_installation(root)
    sys.path.insert(0, str(root / "src"))
    sys.path.insert(0, str(root / "tools"))
    from prepare_milestone7_demo import prepare_demo
    from synthetic_sales_assist.application.scenarios import ScenarioApplication
    from synthetic_sales_assist.campaign_replies.application import WorkspaceApplication
    from synthetic_sales_assist.persistence.paths import resolve_data_paths

    paths = resolve_data_paths(data_dir)
    marker = paths.root / "demo-release.json"
    assert_unlinked(marker)
    previous = json.loads(marker.read_text(encoding="utf-8")) if marker.exists() else None
    workspace_path = paths.data / "campaign_replies.sqlite3"
    workspace_exists = _preflight_workspace(workspace_path, previous)
    application = ScenarioApplication.open(data_dir)
    if application.list_orders():
        raise ValueError("DEMO_RESEED_REQUIRES_EMPTY_DATABASE")
    routes = data_dir / "demo-routes.json"
    assert_unlinked(routes)
    result = prepare_demo(data_dir)
    if not workspace_exists:
        WorkspaceApplication(workspace_path).post({"action": "demo"})
    _preflight_workspace(workspace_path, previous)
    atomic_json(routes, result)
    return {"status": "DEMO_RESEEDED", "scenarios": len(result["scenarios"]),
            "campaign_workspace": "PRESERVED" if workspace_exists else "SEEDED"}


def remove_installation(root: Path) -> dict[str, object]:
    # Delete only unchanged files named in the package inventory, never a directory tree.
    assert_unlinked(root)
    root = root.resolve()
    files = _inventory(root)
    removed: list[str] = []
    preserved: list[str] = []
    preserved_runtime: list[str] = []
    for name in files:
        assert_unlinked(root / name)
    for name, expected in files.items():
        target = root / name
        assert_unlinked(target)
        if not target.exists():
            continue
        # The remover may itself be executing from this embedded runtime. Retain all
        # inventoried runtime files for operator removal after this process exits.
        if name.split("/")[0].casefold() == "python":
            preserved_runtime.append(name)
            continue
        if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != expected:
            preserved.append(name)
            continue
        # release-build.json is retained until all other candidate paths have been checked.
        if name not in {"release-build.json", "REMOVE.cmd"}:
            target.unlink()
            removed.append(name)
    if not preserved:
        for name in ("release-build.json", "release-payload.json"):
            (root / name).unlink()
            removed.append(name)
    folders = {parent for name in files for parent in (root / name).parents
               if parent != root and parent.is_relative_to(root)}
    for folder in sorted(folders, key=lambda item: len(item.parts), reverse=True):
        assert_unlinked(folder)
        if folder.exists() and folder.is_dir():
            try:
                folder.rmdir()
            except OSError:
                pass
    remaining = sorted(path.name for path in root.iterdir())
    return {"removed_files": len(removed), "preserved_modified": preserved,
            "preserved_runtime": preserved_runtime,
            "retained_launcher": "REMOVE.cmd",
            "remaining_files": remaining, "data_and_backups": "PRESERVED_OUTSIDE_INSTALLATION"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=(
        "verify", "prepare", "remove", "extract", "data-root", "configure", "reseed", "backup",
    ))
    parser.add_argument("--install-root", required=True, type=Path)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--backup-prefix", choices=("demo-backup", "pre-reset"),
                        default="demo-backup")
    parser.add_argument("--allow-schema4-upgrade", action="store_true")
    parser.add_argument("--confirm-remove", action="store_true")
    arguments = parser.parse_args()
    if arguments.action in {"data-root", "configure"}:
        if arguments.action == "configure" and arguments.data_dir is None:
            parser.error("--data-dir required for configure")
        result = configured_data_root(arguments.install_root, arguments.data_dir)
    elif arguments.action == "backup":
        if arguments.data_dir is None:
            parser.error("--data-dir required for backup")
        result = backup_application(arguments.install_root, arguments.data_dir,
                                    arguments.backup_prefix)
    elif arguments.action == "reseed":
        if arguments.data_dir is None:
            parser.error("--data-dir required for reseed")
        result = reseed(arguments.install_root, arguments.data_dir)
    elif arguments.action == "prepare":
        if arguments.data_dir is None:
            parser.error("--data-dir is required for prepare")
        result = prepare(
            arguments.install_root, arguments.data_dir, arguments.allow_schema4_upgrade,
        )
    elif arguments.action == "remove":
        if not arguments.confirm_remove:
            parser.error("--confirm-remove is required")
        result = remove_installation(arguments.install_root)
    elif arguments.action == "extract":
        if arguments.archive is None:
            parser.error("--archive is required")
        extract_archive(arguments.archive, arguments.install_root)
        result = {"status": "EXTRACTED"}
    else:
        result = verify_installation(arguments.install_root)
    print(json.dumps(result, sort_keys=True))
