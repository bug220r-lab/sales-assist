"""Assemble a pinned Windows Python distribution from two existing offline inputs.

Nothing here downloads, executes, installs, or extracts an input onto the filesystem.
Both whole-file hashes are checked before either archive is parsed. The returned file
map is suitable for the release builder's deterministic ZIP writer.
"""

from __future__ import annotations

import ast
import gzip
import hashlib
import io
import json
import re
import stat
import tarfile
import zipfile
from email.parser import BytesParser
from pathlib import Path, PurePosixPath


LOCK_PATH = Path(__file__).with_name("windows_runtime_lock.json")
MAX_INPUT_BYTES = 64 * 1024 * 1024
MAX_TAR_BYTES = 160 * 1024 * 1024
MAX_MEMBER_BYTES = 32 * 1024 * 1024
MAX_TOTAL_BYTES = 128 * 1024 * 1024
MAX_MEMBERS = 10000
PATH_CONFIGURATION = b"Lib\nDLLs\nLib/site-packages\n../src\n"
REQUIRED_NATIVE_FILES = frozenset({
    "python/python.exe", "python/python312.dll", "python/DLLs/_sqlite3.pyd",
    "python/DLLs/sqlite3.dll", "python/vcruntime140.dll", "python/vcruntime140_1.dll",
})
REQUIRED_PYTHON_FILES = REQUIRED_NATIVE_FILES | frozenset({
    "python/Lib/encodings/__init__.py", "python/LICENSE.txt",
})


def _load_lock() -> dict[str, object]:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    if (
        not isinstance(lock, dict)
        or lock.get("schema") != "synthetic-sales-assist-windows-runtime-lock/v1"
        or not isinstance(lock.get("python"), dict)
        or not isinstance(lock.get("timezone"), dict)
        or lock["python"].get("version") != "3.12.14"
        or lock["python"].get("architecture") != "windows-x86_64"
        or lock["timezone"].get("version") != "2026.3"
        or lock["timezone"].get("iana_version") != "2026c"
    ):
        raise ValueError("BUNDLED_RUNTIME_LOCK_INVALID")
    return lock


def _read_pinned(path: Path, expected: dict[str, object]) -> bytes:
    value = str(path)
    if value.startswith(("\\\\", "//")) or ":" in value[len(path.drive):]:
        raise ValueError("BUNDLED_RUNTIME_LOCAL_INPUT_REQUIRED")
    for candidate in (path, *path.parents):
        if candidate.is_symlink():
            raise ValueError("BUNDLED_RUNTIME_INPUT_LINK_PROHIBITED")
        metadata = candidate.lstat()
        if getattr(metadata, "st_file_attributes", 0) & 0x400:
            raise ValueError("BUNDLED_RUNTIME_INPUT_LINK_PROHIBITED")
    metadata = path.stat()
    expected_size = expected.get("size")
    expected_hash = expected.get("sha256")
    if (
        not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1
        or type(expected_size) is not int or not 0 < expected_size <= MAX_INPUT_BYTES
        or not isinstance(expected_hash, str)
        or re.fullmatch(r"[0-9a-f]{64}", expected_hash) is None
        or metadata.st_size != expected_size
    ):
        raise ValueError("BUNDLED_RUNTIME_INPUT_SIZE_OR_TYPE_INVALID")
    with path.open("rb") as stream:
        raw = stream.read(expected_size + 1)
    if len(raw) != expected_size or hashlib.sha256(raw).hexdigest() != expected_hash:
        raise ValueError("BUNDLED_RUNTIME_INPUT_HASH_MISMATCH")
    return raw


def _safe_name(name: str, *, directory: bool = False) -> str:
    if directory and name.endswith("/"):
        name = name[:-1]
    path = PurePosixPath(name)
    if (
        not name or len(name) > 1024 or path.as_posix() != name or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or any(ord(character) < 32 or character in '\\:<>"|?*' for character in name)
        or any(len(part) > 255 or part.endswith((".", " ")) for part in path.parts)
        or any(re.fullmatch(
            r"(?i)(CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|COM[1-9¹²³]|LPT[1-9¹²³]) *(?:\..*)?", part,
        ) for part in path.parts)
    ):
        raise ValueError("BUNDLED_RUNTIME_MEMBER_PATH_INVALID")
    return name


class _Inventory:
    """Enforce Windows path identity, including implicit parent directories."""

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.paths: dict[str, tuple[str, bool]] = {}
        self.members: set[str] = set()
        self.count = 0
        self.total = 0

    def member(self, name: str, size: int, *, directory: bool = False) -> str:
        name = _safe_name(name, directory=directory)
        self.count += 1
        self.total += size
        if (
            self.count > MAX_MEMBERS or size < 0 or size > MAX_MEMBER_BYTES
            or self.total > MAX_TOTAL_BYTES or (directory and size != 0)
        ):
            raise ValueError("BUNDLED_RUNTIME_ARCHIVE_LIMIT_EXCEEDED")
        key = name.casefold()
        if key in self.members:
            raise ValueError("BUNDLED_RUNTIME_MEMBER_COLLISION")
        self.members.add(key)
        parts = name.split("/")
        for count in range(1, len(parts) + 1):
            prefix = "/".join(parts[:count])
            prefix_key = prefix.casefold()
            is_directory = count < len(parts) or directory
            prior = self.paths.get(prefix_key)
            if prior is not None and prior != (prefix, is_directory):
                raise ValueError("BUNDLED_RUNTIME_MEMBER_COLLISION")
            self.paths[prefix_key] = (prefix, is_directory)
        return name

    def store(self, name: str, raw: bytes, expected_size: int) -> None:
        if len(raw) != expected_size:
            raise ValueError("BUNDLED_RUNTIME_MEMBER_SIZE_MISMATCH")
        self.files[name] = raw


def _python_files(raw: bytes, inventory: _Inventory) -> None:
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as compressed:
        tar_raw = compressed.read(MAX_TAR_BYTES + 1)
    if len(tar_raw) > MAX_TAR_BYTES:
        raise ValueError("BUNDLED_RUNTIME_ARCHIVE_LIMIT_EXCEEDED")
    with tarfile.open(fileobj=io.BytesIO(tar_raw), mode="r:") as archive:
        for member in archive:
            if member.type not in {tarfile.REGTYPE, tarfile.AREGTYPE, tarfile.DIRTYPE} \
                    or member.issparse():
                raise ValueError("BUNDLED_RUNTIME_ARCHIVE_LINK_OR_TYPE_PROHIBITED")
            name = inventory.member(member.name, member.size, directory=member.isdir())
            if not name.startswith("python/") and not (name == "python" and member.isdir()):
                raise ValueError("BUNDLED_RUNTIME_PYTHON_PREFIX_REQUIRED")
            if member.isdir():
                continue
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError("BUNDLED_RUNTIME_ARCHIVE_MEMBER_INVALID")
            with stream:
                inventory.store(name, stream.read(member.size + 1), member.size)


def _timezone_files(raw: bytes, inventory: _Inventory, version: str) -> None:
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        members = archive.infolist()
        if len(members) + inventory.count > MAX_MEMBERS:
            raise ValueError("BUNDLED_RUNTIME_ARCHIVE_LIMIT_EXCEEDED")
        for member in members:
            mode = stat.S_IFMT(member.external_attr >> 16)
            directory = member.is_dir()
            if member.flag_bits & 1 or mode not in {0, stat.S_IFREG, stat.S_IFDIR} \
                    or (mode == stat.S_IFDIR and not directory) \
                    or (mode == stat.S_IFREG and directory):
                raise ValueError("BUNDLED_RUNTIME_ARCHIVE_LINK_OR_TYPE_PROHIBITED")
            local_name = _safe_name(member.filename, directory=directory)
            if local_name.split("/")[0] not in {"tzdata", f"tzdata-{version}.dist-info"}:
                raise ValueError("BUNDLED_RUNTIME_TIMEZONE_PREFIX_REQUIRED")
            name = inventory.member("python/Lib/site-packages/" + local_name,
                                    member.file_size, directory=directory)
            if not directory:
                inventory.store(name, archive.read(member), member.file_size)


def _validate_components(files: dict[str, bytes], timezone: dict[str, object]) -> None:
    if not REQUIRED_PYTHON_FILES.issubset(files) or any(
        not files[name] for name in REQUIRED_PYTHON_FILES
    ):
        raise ValueError("BUNDLED_RUNTIME_PYTHON_COMPONENT_MISSING")
    for name in REQUIRED_NATIVE_FILES:
        raw = files[name]
        offset = int.from_bytes(raw[60:64], "little")
        if (
            len(raw) < 64 or raw[:2] != b"MZ" or not 64 <= offset <= len(raw) - 26
            or raw[offset:offset + 6] != b"PE\x00\x00\x64\x86"
            or raw[offset + 24:offset + 26] != b"\x0b\x02"
        ):
            raise ValueError("BUNDLED_RUNTIME_WINDOWS_X64_COMPONENT_REQUIRED")
    prefix = "python/Lib/site-packages/"
    distribution = prefix + "tzdata-2026.3.dist-info/"
    required = {
        prefix + "tzdata/__init__.py", prefix + "tzdata/zones",
        prefix + "tzdata/zoneinfo/UTC", prefix + "tzdata/zoneinfo/America/New_York",
        distribution + "METADATA", distribution + "WHEEL", distribution + "RECORD",
        distribution + "licenses/LICENSE", distribution + "licenses/licenses/LICENSE_APACHE",
    }
    if not required.issubset(files) or any(not files[name] for name in required):
        raise ValueError("BUNDLED_RUNTIME_TIMEZONE_COMPONENT_MISSING")
    metadata = BytesParser().parsebytes(files[distribution + "METADATA"])
    if metadata.get_all("Name") != ["tzdata"] \
            or metadata.get_all("Version") != [timezone["version"]]:
        raise ValueError("BUNDLED_RUNTIME_TIMEZONE_VERSION_MISMATCH")
    wheel = BytesParser().parsebytes(files[distribution + "WHEEL"])
    if wheel.get_all("Root-Is-Purelib") != ["true"] \
            or "py3-none-any" not in wheel.get_all("Tag", []):
        raise ValueError("BUNDLED_RUNTIME_TIMEZONE_WHEEL_INVALID")
    module = ast.parse(files[prefix + "tzdata/__init__.py"])
    versions = {}
    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in {"__version__", "IANA_VERSION"}:
                    if target.id in versions or not isinstance(node.value, ast.Constant):
                        raise ValueError("BUNDLED_RUNTIME_TIMEZONE_VERSION_MISMATCH")
                    versions[target.id] = node.value.value
    if versions != {"__version__": timezone["version"], "IANA_VERSION": timezone["iana_version"]}:
        raise ValueError("BUNDLED_RUNTIME_TIMEZONE_VERSION_MISMATCH")


def bundled_runtime(
    python_archive: Path, timezone_wheel: Path,
) -> tuple[dict[str, bytes], dict[str, object]]:
    """Return package members and its release-build ``bundled_runtime`` metadata value.

    Input bytes must match the checked-in lock. The manifest inventories every
    returned ``python/`` file, including licenses, vendor bytecode, and isolation
    configuration. Application invocations must additionally use Python's ``-B``.
    """
    lock = _load_lock()
    python = lock["python"]
    timezone = lock["timezone"]
    python_raw = _read_pinned(python_archive, python)
    timezone_raw = _read_pinned(timezone_wheel, timezone)
    inventory = _Inventory()
    _python_files(python_raw, inventory)
    _timezone_files(timezone_raw, inventory, str(timezone["version"]))
    _validate_components(inventory.files, timezone)
    configuration = inventory.member("python/python312._pth", len(PATH_CONFIGURATION))
    inventory.store(configuration, PATH_CONFIGURATION, len(PATH_CONFIGURATION))
    manifest = {
        "schema": "synthetic-sales-assist-bundled-python/v1",
        "python_version": python["version"],
        "architecture": python["architecture"],
        "executable": "python/python.exe",
        "timezone_version": timezone["version"],
        "sources": {"python": python, "timezone": timezone},
        "files": {name: hashlib.sha256(raw).hexdigest()
                  for name, raw in sorted(inventory.files.items())},
    }
    manifest_bytes = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode("utf-8")
    inventory.files["python-runtime.json"] = manifest_bytes
    metadata = {
        "manifest": "python-runtime.json",
        "sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "executable": "python/python.exe",
        "python_version": python["version"],
        "timezone_version": timezone["version"],
    }
    return inventory.files, metadata
