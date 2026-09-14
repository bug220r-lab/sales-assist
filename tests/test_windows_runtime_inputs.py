"""Pinned offline runtime assembly; tiny fixtures never execute a vendor runtime."""

from __future__ import annotations

import copy
import hashlib
import io
import json
import stat
import struct
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from tools import bundled_python


def synthetic_pe_header() -> bytes:
    """Nonexecutable fixture containing only a DOS header and AMD64 PE32+ identity."""
    raw = bytearray(90)
    raw[:2] = b"MZ"
    raw[60:64] = (64).to_bytes(4, "little")
    raw[64:70] = b"PE\x00\x00\x64\x86"
    raw[88:90] = b"\x0b\x02"
    return bytes(raw)


def python_members() -> list[tuple[str, bytes, bytes]]:
    members = [(name, synthetic_pe_header() if name in bundled_python.REQUIRED_NATIVE_FILES
                else b"synthetic-component", tarfile.REGTYPE)
               for name in sorted(bundled_python.REQUIRED_PYTHON_FILES)]
    members.extend([
        ("python/Lib/site-packages/vendor/LICENSE", b"synthetic license", tarfile.REGTYPE),
        ("python/Lib/vendor/__pycache__/module.cpython-312.pyc", b"bytecode", tarfile.REGTYPE),
    ])
    return members


def timezone_members() -> list[tuple[str, bytes, int]]:
    distribution = "tzdata-2026.3.dist-info/"
    files = {
        "tzdata/__init__.py": b'__version__ = "2026.3"\nIANA_VERSION = "2026c"\n',
        "tzdata/zones": b"America/New_York\nUTC\n",
        "tzdata/zoneinfo/UTC": b"synthetic TZif",
        "tzdata/zoneinfo/America/New_York": b"synthetic TZif",
        distribution + "METADATA": b"Name: tzdata\nVersion: 2026.3\n\n",
        distribution + "WHEEL": b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        distribution + "RECORD": b"synthetic-record\n",
        distribution + "licenses/LICENSE": b"synthetic timezone license",
        distribution + "licenses/licenses/LICENSE_APACHE": b"synthetic apache license",
    }
    return [(name, raw, stat.S_IFREG | 0o644) for name, raw in files.items()]


def tar_bytes(members: list[tuple[str, bytes, bytes]]) -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        for name, raw, kind in members:
            member = tarfile.TarInfo(name)
            member.type = kind
            member.size = len(raw) if kind == tarfile.REGTYPE else 0
            if kind in {tarfile.SYMTYPE, tarfile.LNKTYPE}:
                member.linkname = "python/python.exe"
            archive.addfile(member, io.BytesIO(raw) if kind == tarfile.REGTYPE else None)
    return output.getvalue()


def wheel_bytes(members: list[tuple[str, bytes, int]]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, raw, mode in members:
            member = zipfile.ZipInfo(name)
            member.create_system = 3
            member.external_attr = mode << 16
            archive.writestr(member, raw)
    return output.getvalue()


class BundledRuntimeInputTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="ssa-runtime-inputs-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.lock = bundled_python._load_lock()

    def inputs(
        self, python: list[tuple[str, bytes, bytes]] | None = None,
        timezone: list[tuple[str, bytes, int]] | None = None,
        *, wheel_raw: bytes | None = None,
    ) -> tuple[Path, Path]:
        runtime = self.root / "synthetic-python.tar.gz"
        wheel = self.root / "synthetic-tzdata.whl"
        runtime.write_bytes(tar_bytes(python if python is not None else python_members()))
        wheel.write_bytes(wheel_raw if wheel_raw is not None else wheel_bytes(
            timezone if timezone is not None else timezone_members(),
        ))
        self.lock = copy.deepcopy(self.lock)
        for key, path in (("python", runtime), ("timezone", wheel)):
            raw = path.read_bytes()
            self.lock[key]["size"] = len(raw)
            self.lock[key]["sha256"] = hashlib.sha256(raw).hexdigest()
        return runtime, wheel

    def bundle(self, paths: tuple[Path, Path]) -> tuple[dict[str, bytes], dict[str, object]]:
        with patch.object(bundled_python, "_load_lock", return_value=self.lock):
            return bundled_python.bundled_runtime(*paths)

    def test_preserves_vendor_bytes_and_emits_complete_deterministic_manifest(self) -> None:
        paths = self.inputs()
        before = [path.read_bytes() for path in paths]
        files, metadata = self.bundle(paths)
        self.assertEqual((files, metadata), self.bundle(paths))
        self.assertEqual(before, [path.read_bytes() for path in paths])
        for name, raw, _ in python_members():
            self.assertEqual(files[name], raw)
        for name, raw, _ in timezone_members():
            self.assertEqual(files["python/Lib/site-packages/" + name], raw)
        self.assertEqual(files["python/python312._pth"],
                         b"Lib\nDLLs\nLib/site-packages\n../src\n")
        manifest_raw = files.pop("python-runtime.json")
        manifest = json.loads(manifest_raw)
        self.assertEqual(manifest["schema"], "synthetic-sales-assist-bundled-python/v1")
        self.assertEqual(manifest["architecture"], "windows-x86_64")
        self.assertEqual(manifest["sources"], {
            "python": self.lock["python"], "timezone": self.lock["timezone"],
        })
        self.assertEqual(manifest["files"], {
            name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()
        })
        self.assertEqual(metadata, {
            "manifest": "python-runtime.json",
            "sha256": hashlib.sha256(manifest_raw).hexdigest(),
            "executable": "python/python.exe", "python_version": "3.12.14",
            "timezone_version": "2026.3",
        })

    def test_both_hashes_are_verified_before_archive_parsing(self) -> None:
        for index in (0, 1):
            with self.subTest(input=index):
                paths = self.inputs()
                raw = paths[index].read_bytes()
                paths[index].write_bytes(bytes([raw[0] ^ 1]) + raw[1:])
                with patch.object(tarfile, "open", side_effect=AssertionError("parsed tar")), \
                        patch.object(zipfile, "ZipFile", side_effect=AssertionError("parsed zip")):
                    with self.assertRaisesRegex(ValueError, "INPUT_HASH_MISMATCH"):
                        self.bundle(paths)

    def test_input_length_and_global_input_bound_are_checked(self) -> None:
        paths = self.inputs()
        paths[0].write_bytes(paths[0].read_bytes() + b"extra")
        with self.assertRaisesRegex(ValueError, "INPUT_SIZE_OR_TYPE_INVALID"):
            self.bundle(paths)
        paths = self.inputs()
        with patch.object(bundled_python, "MAX_INPUT_BYTES", 1):
            with self.assertRaisesRegex(ValueError, "INPUT_SIZE_OR_TYPE_INVALID"):
                self.bundle(paths)

    def test_traversal_device_ads_and_windows_alias_names_are_rejected(self) -> None:
        for name in ("python/../escape", "/python/absolute", "python/C:/drive",
                     "python/a:b", "python/a\\b", "python/a//b", "python/./a",
                     "python/NUL.txt", "python/COM1.log", "python/CONIN$", "python/COM¹",
                     "python/space ", "python/period.", "python/a?b", "python/a\x01b"):
            with self.subTest(name=name):
                paths = self.inputs(python_members() + [(name, b"invalid", tarfile.REGTYPE)])
                with self.assertRaisesRegex(ValueError, "MEMBER_PATH_INVALID"):
                    self.bundle(paths)
        paths = self.inputs(timezone=timezone_members() + [
            ("tzdata/../escape", b"invalid", stat.S_IFREG | 0o644),
        ])
        with self.assertRaisesRegex(ValueError, "MEMBER_PATH_INVALID"):
            self.bundle(paths)

    def test_archive_links_and_special_devices_are_rejected(self) -> None:
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.CHRTYPE,
                     tarfile.BLKTYPE, tarfile.FIFOTYPE):
            with self.subTest(kind=kind):
                paths = self.inputs(python_members() + [("python/link", b"", kind)])
                with self.assertRaisesRegex(ValueError, "LINK_OR_TYPE_PROHIBITED"):
                    self.bundle(paths)
        for mode in (stat.S_IFLNK, stat.S_IFCHR, stat.S_IFIFO):
            with self.subTest(wheel_mode=mode):
                paths = self.inputs(timezone=timezone_members() + [
                    ("tzdata/special", b"synthetic-target", mode | 0o644),
                ])
                with self.assertRaisesRegex(ValueError, "LINK_OR_TYPE_PROHIBITED"):
                    self.bundle(paths)

    def test_case_collisions_and_file_directory_collisions_are_rejected(self) -> None:
        for additions in (
            [("python/PYTHON.exe", b"duplicate", tarfile.REGTYPE)],
            [("python/lib/other", b"case parent", tarfile.REGTYPE)],
            [("python/python.exe/child", b"file parent", tarfile.REGTYPE)],
            [("python/Lib", b"directory replaced", tarfile.REGTYPE)],
            [("python/python312._pth", b"unreviewed paths", tarfile.REGTYPE)],
        ):
            with self.subTest(additions=additions):
                paths = self.inputs(python_members() + additions)
                with self.assertRaisesRegex(ValueError, "MEMBER_COLLISION"):
                    self.bundle(paths)
        paths = self.inputs(timezone=timezone_members() + [
            ("tzdata/ZONEINFO/extra", b"case parent", stat.S_IFREG | 0o644),
        ])
        with self.assertRaisesRegex(ValueError, "MEMBER_COLLISION"):
            self.bundle(paths)

    def test_archive_count_size_and_expansion_bounds_are_enforced(self) -> None:
        paths = self.inputs()
        for constant, maximum in (("MAX_MEMBER_BYTES", 1), ("MAX_TOTAL_BYTES", 1),
                                  ("MAX_MEMBERS", 1), ("MAX_TAR_BYTES", 1)):
            with self.subTest(bound=constant), patch.object(bundled_python, constant, maximum):
                with self.assertRaisesRegex(ValueError, "ARCHIVE_LIMIT_EXCEEDED"):
                    self.bundle(paths)

    def test_encrypted_wheel_is_rejected_without_reading_member_data(self) -> None:
        raw = bytearray(wheel_bytes(timezone_members()))
        for signature, offset in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
            location = raw.find(signature)
            flags = struct.unpack_from("<H", raw, location + offset)[0]
            struct.pack_into("<H", raw, location + offset, flags | 1)
        paths = self.inputs(wheel_raw=bytes(raw))
        with self.assertRaisesRegex(ValueError, "LINK_OR_TYPE_PROHIBITED"):
            self.bundle(paths)

    def test_missing_python_and_timezone_components_are_rejected(self) -> None:
        for name in ("python/python.exe", "python/python312.dll", "python/DLLs/_sqlite3.pyd",
                     "python/DLLs/sqlite3.dll", "python/LICENSE.txt"):
            with self.subTest(component=name):
                paths = self.inputs([entry for entry in python_members() if entry[0] != name])
                with self.assertRaisesRegex(ValueError, "PYTHON_COMPONENT_MISSING"):
                    self.bundle(paths)
        for name in ("tzdata/zoneinfo/UTC", "tzdata-2026.3.dist-info/licenses/LICENSE"):
            with self.subTest(component=name):
                paths = self.inputs(timezone=[entry for entry in timezone_members()
                                              if entry[0] != name])
                with self.assertRaisesRegex(ValueError, "TIMEZONE_COMPONENT_MISSING"):
                    self.bundle(paths)

    def test_wrong_timezone_metadata_is_rejected(self) -> None:
        cases = (
            ("tzdata-2026.3.dist-info/METADATA", b"Name: tzdata\nVersion: 2026.2\n",
             "TIMEZONE_VERSION_MISMATCH"),
            ("tzdata-2026.3.dist-info/METADATA", b"Name: wrong\nVersion: 2026.3\n",
             "TIMEZONE_VERSION_MISMATCH"),
            ("tzdata-2026.3.dist-info/WHEEL", b"Root-Is-Purelib: false\nTag: py3-none-any\n",
             "TIMEZONE_WHEEL_INVALID"),
            ("tzdata/__init__.py", b'__version__ = "2026.2"\nIANA_VERSION = "2026c"\n',
             "TIMEZONE_VERSION_MISMATCH"),
            ("tzdata/__init__.py", b'__version__ = "2026.3"\nIANA_VERSION = "2026b"\n',
             "TIMEZONE_VERSION_MISMATCH"),
        )
        for name, replacement, error in cases:
            with self.subTest(component=name, replacement=replacement):
                members = [(key, replacement if key == name else raw, mode)
                           for key, raw, mode in timezone_members()]
                paths = self.inputs(timezone=members)
                with self.assertRaisesRegex(ValueError, error):
                    self.bundle(paths)

    def test_required_native_components_must_identify_as_windows_x64(self) -> None:
        wrong_architecture = bytearray(synthetic_pe_header())
        wrong_architecture[68:70] = b"\x4c\x01"
        wrong_optional_header = bytearray(synthetic_pe_header())
        wrong_optional_header[88:90] = b"\x0b\x01"
        for raw in (b"truncated", bytes(wrong_architecture), bytes(wrong_optional_header)):
            with self.subTest(header=raw):
                members = [(name, raw if name == "python/python.exe" else data, kind)
                           for name, data, kind in python_members()]
                paths = self.inputs(members)
                with self.assertRaisesRegex(ValueError, "WINDOWS_X64_COMPONENT_REQUIRED"):
                    self.bundle(paths)

    def test_unrelated_payload_roots_are_rejected(self) -> None:
        paths = self.inputs(python_members() + [("outside/file", b"invalid", tarfile.REGTYPE)])
        with self.assertRaisesRegex(ValueError, "PYTHON_PREFIX_REQUIRED"):
            self.bundle(paths)
        paths = self.inputs(timezone=timezone_members() + [
            ("unrelated-package/file", b"invalid", stat.S_IFREG | 0o644),
        ])
        with self.assertRaisesRegex(ValueError, "TIMEZONE_PREFIX_REQUIRED"):
            self.bundle(paths)


if __name__ == "__main__":
    unittest.main()
