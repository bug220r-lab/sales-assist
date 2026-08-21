"""Local-only application-data path policy for durable synthetic state."""

from __future__ import annotations

import ntpath
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from synthetic_sales_assist.persistence.migrations import PROJECT_ROOT


APPLICATION_DIRECTORY_NAME: Final = "SyntheticSalesAssist"
DATABASE_FILENAME: Final = "synthetic_sales_assist.sqlite3"
_URL_SCHEME = re.compile(r"\A[A-Za-z][A-Za-z0-9+.-]*://")
_WINDOWS_DEVICE_PREFIXES = ("\\\\?\\", "\\\\.\\", "//?/", "//./")


class PathPolicyError(ValueError):
    """A runtime path is not an explicitly local, nonsynchronized location."""


def _existing_ancestor_is_reparse_point(path: Path) -> bool:
    candidate = path
    while True:
        if candidate.exists():
            try:
                attributes = getattr(candidate.lstat(), "st_file_attributes", 0)
            except OSError:
                return True
            if candidate.is_symlink() or attributes & 0x400:
                return True
        parent = candidate.parent
        if parent == candidate:
            return False
        candidate = parent


def _windows_drive_is_remote(path: Path) -> bool:
    if os.name != "nt":
        return False
    try:
        import ctypes

        drive = path.drive
        if not drive:
            return True
        drive_root = drive + "\\"
        return int(ctypes.windll.kernel32.GetDriveTypeW(drive_root)) == 4
    except (AttributeError, OSError, TypeError, ValueError):
        return True


def validate_local_path(
    value: Path | str,
    *,
    repository_root: Path | str = PROJECT_ROOT,
) -> Path:
    """Resolve one absolute local path and reject repository/network escape hatches."""

    if not isinstance(value, (Path, str)):
        raise PathPolicyError("LOCAL_PATH_TYPE_INVALID")
    raw = os.fspath(value)
    if not raw or "\x00" in raw or _URL_SCHEME.match(raw):
        raise PathPolicyError("LOCAL_PATH_INVALID")
    normalized_prefix = raw.replace("/", "\\")
    if normalized_prefix.startswith("\\\\") or normalized_prefix.startswith(
        _WINDOWS_DEVICE_PREFIXES
    ):
        raise PathPolicyError("LOCAL_PATH_NETWORK_OR_DEVICE")
    _drive, drive_relative = ntpath.splitdrive(normalized_prefix)
    if ":" in drive_relative:
        raise PathPolicyError("LOCAL_PATH_ALTERNATE_DATA_STREAM")
    candidate = Path(raw)
    if not candidate.is_absolute() or ".." in candidate.parts:
        raise PathPolicyError("LOCAL_PATH_ABSOLUTE_REQUIRED")
    if _existing_ancestor_is_reparse_point(candidate):
        raise PathPolicyError("LOCAL_PATH_SYMLINK_PROHIBITED")
    try:
        resolved = candidate.resolve(strict=False)
        repository = Path(repository_root).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise PathPolicyError("LOCAL_PATH_RESOLUTION_FAILED") from exc
    if resolved == repository or resolved.is_relative_to(repository):
        raise PathPolicyError("LOCAL_PATH_REPOSITORY_PROHIBITED")
    if _windows_drive_is_remote(resolved):
        raise PathPolicyError("LOCAL_PATH_NETWORK_OR_DEVICE")
    return resolved


@dataclass(frozen=True, slots=True)
class DataPaths:
    """Closed runtime directory layout rooted outside the source checkout."""

    root: Path
    data: Path
    logs: Path
    backups: Path
    runtime: Path
    exports: Path
    database: Path

    def ensure_directories(self) -> None:
        for path in (
            self.root,
            self.data,
            self.logs,
            self.backups,
            self.runtime,
            self.exports,
        ):
            path.mkdir(parents=True, exist_ok=True)


def resolve_data_paths(
    data_dir: Path | str | None = None,
    *,
    repository_root: Path | str = PROJECT_ROOT,
    environ: Mapping[str, str] | None = None,
) -> DataPaths:
    """Return the deterministic local application layout without creating it."""

    environment = os.environ if environ is None else environ
    if data_dir is None:
        local_app_data = environment.get("LOCALAPPDATA")
        if not local_app_data:
            raise PathPolicyError("LOCALAPPDATA_UNAVAILABLE")
        candidate: Path | str = Path(local_app_data) / APPLICATION_DIRECTORY_NAME
    else:
        candidate = data_dir
    root = validate_local_path(candidate, repository_root=repository_root)
    data = root / "data"
    return DataPaths(
        root=root,
        data=data,
        logs=root / "logs",
        backups=root / "backups",
        runtime=root / "runtime",
        exports=root / "exports",
        database=data / DATABASE_FILENAME,
    )


__all__ = [
    "APPLICATION_DIRECTORY_NAME",
    "DATABASE_FILENAME",
    "DataPaths",
    "PathPolicyError",
    "resolve_data_paths",
    "validate_local_path",
]
