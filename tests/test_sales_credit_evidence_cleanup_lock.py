"""Original byte-lock compatibility using only synthetic paths and dummy files."""

from __future__ import annotations

import io
import os
import stat
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from sales_credit_evidence import cleanup_lock as lock
from sales_credit_evidence.transport import ReadError

CONNECTION = (
    r"C:\Users\Synthetic\Documents\HelpScout\ECS_Campaign_Replies_2026-09-11"
    r"\local-review\helpscout-auth.dpapi"
)
LOCK = (
    r"C:\Users\Synthetic\Documents\Codex\2026-10-10\task-3"
    r"\helpscout_one_outbound_candidate\operation-v1.lock"
)


def assert_safe(error: ReadError, code: str) -> None:
    assert error.code == code
    assert code in lock.CLEANUP_LOCK_ERROR_CODES
    assert error.__context__ is None
    assert error.__cause__ is None
    assert "Synthetic" not in str(error)
    assert "Synthetic" not in repr(error)


def test_factory_and_close_without_acquire_have_no_io(monkeypatch):
    forbidden = Mock(side_effect=AssertionError("unexpected I/O"))
    monkeypatch.setattr(lock, "_inspect_lock", forbidden)
    monkeypatch.setattr(lock, "_open_existing_lock", forbidden)
    monkeypatch.setattr(lock, "_lock_fd", forbidden)
    lease = lock.new_cleanup_lease(CONNECTION, LOCK)
    assert repr(lease) == "<CleanupLease redacted>"
    lease.close()
    lease.close()
    forbidden.assert_not_called()
    with pytest.raises(ReadError) as caught:
        lease.acquire()
    assert_safe(caught.value, "cleanup_lock_closed")


@pytest.mark.parametrize(
    ("connection", "cleanup"),
    [
        (CONNECTION.replace("ECS_Campaign_Replies_2026-09-11", "other"), LOCK),
        (CONNECTION.replace("Synthetic", "Another"), LOCK),
        (CONNECTION, LOCK.replace("Synthetic", "Another")),
        (CONNECTION, LOCK.replace("operation-v1.lock", "operation-v2.lock")),
        (CONNECTION, LOCK.replace("helpscout_one_outbound_candidate", "another")),
        (CONNECTION, LOCK.replace("2026-10-10", "2026-10-11")),
        (CONNECTION, LOCK + ":stream"),
        (CONNECTION, LOCK + "."),
        (CONNECTION, LOCK + " "),
        (CONNECTION.replace("Documents", r"Elsewhere\Documents"), LOCK),
        (CONNECTION.replace("Documents", r"..\Documents"), LOCK),
        (CONNECTION.replace("Documents", r".\Documents"), LOCK),
        (CONNECTION.replace("Users", "Accounts"), LOCK),
        (CONNECTION.replace("Synthetic", "CON"), LOCK.replace("Synthetic", "CON")),
        (CONNECTION.replace("C:", r"\\server"), LOCK),
        (CONNECTION, LOCK.replace("C:", "D:")),
        (None, LOCK),
        (CONNECTION, None),
    ],
)
def test_wrong_scope_rejected_before_io(monkeypatch, connection, cleanup):
    forbidden = Mock(side_effect=AssertionError("unexpected I/O"))
    monkeypatch.setattr(lock, "_inspect_lock", forbidden)
    monkeypatch.setattr(lock, "_open_existing_lock", forbidden)
    with pytest.raises(ReadError) as caught:
        lock.new_cleanup_lease(connection, cleanup)
    assert_safe(caught.value, "cleanup_lock_scope_invalid")
    forbidden.assert_not_called()


def test_case_and_slash_variants_refer_to_same_bound_pair():
    lease = lock.new_cleanup_lease(CONNECTION.lower().replace("\\", "/"), LOCK.upper())
    lease.close()


class DummyHandle(io.BytesIO):
    def fileno(self):
        return 99


@pytest.fixture
def fake_io(monkeypatch):
    info = SimpleNamespace(
        st_mode=stat.S_IFREG | 0o600,
        st_size=1,
        st_nlink=1,
        st_ino=123,
        st_dev=456,
        st_mtime_ns=789,
        st_file_attributes=0,
    )
    handle = DummyHandle(b"0")
    handle.seek(1)
    inspect = Mock(return_value=info)
    open_file = Mock(return_value=handle)
    operations = []

    def locking(descriptor, *, release):
        assert descriptor == 99
        assert handle.tell() == 0
        operations.append(release)

    monkeypatch.setattr(lock, "_is_windows", lambda: True)
    monkeypatch.setattr(lock, "_inspect_lock", inspect)
    monkeypatch.setattr(lock, "_open_existing_lock", open_file)
    monkeypatch.setattr(lock.os, "fstat", lambda descriptor: info)
    monkeypatch.setattr(lock, "_lock_fd", locking)
    return SimpleNamespace(
        info=info, handle=handle, inspect=inspect, open_file=open_file, operations=operations
    )


def test_one_acquisition_and_release_seek_byte_zero(fake_io):
    lease = lock.new_cleanup_lease(CONNECTION, LOCK)
    lease.acquire()
    assert fake_io.operations == [False]
    assert fake_io.inspect.call_count == 2
    assert fake_io.open_file.call_count == 1
    with pytest.raises(ReadError) as caught:
        lease.acquire()
    assert_safe(caught.value, "cleanup_lock_already_attempted")
    fake_io.handle.seek(1)
    lease.close()
    assert fake_io.operations == [False, True]
    assert fake_io.handle.closed
    lease.close()
    assert fake_io.operations == [False, True]


@pytest.mark.parametrize("kind", ["empty", "directory", "hardlink", "reparse", "no_identity"])
def test_invalid_file_rejected_before_open(fake_io, kind):
    updates = {
        "empty": {"st_size": 0},
        "directory": {"st_mode": stat.S_IFDIR | 0o700},
        "hardlink": {"st_nlink": 2},
        "reparse": {"st_file_attributes": stat.FILE_ATTRIBUTE_REPARSE_POINT},
        "no_identity": {"st_ino": 0},
    }
    for key, value in updates[kind].items():
        setattr(fake_io.info, key, value)
    lease = lock.new_cleanup_lease(CONNECTION, LOCK)
    with pytest.raises(ReadError) as caught:
        lease.acquire()
    assert_safe(caught.value, "cleanup_lock_invalid")
    fake_io.open_file.assert_not_called()
    assert fake_io.operations == []


def test_missing_file_not_created_or_retried(fake_io):
    fake_io.inspect.side_effect = FileNotFoundError(CONNECTION)
    lease = lock.new_cleanup_lease(CONNECTION, LOCK)
    with pytest.raises(ReadError) as caught:
        lease.acquire()
    assert_safe(caught.value, "cleanup_lock_missing")
    with pytest.raises(ReadError) as caught:
        lease.acquire()
    assert_safe(caught.value, "cleanup_lock_already_attempted")
    fake_io.inspect.assert_called_once()
    fake_io.open_file.assert_not_called()


def test_contention_closes_handle_and_does_not_unlock_or_retry(fake_io, monkeypatch):
    native = Mock(side_effect=OSError("private " + CONNECTION))
    monkeypatch.setattr(lock, "_lock_fd", native)
    lease = lock.new_cleanup_lease(CONNECTION, LOCK)
    with pytest.raises(ReadError) as caught:
        lease.acquire()
    assert_safe(caught.value, "cleanup_lock_unavailable")
    assert fake_io.handle.closed
    native.assert_called_once_with(99, release=False)
    lease.close()
    native.assert_called_once()


@pytest.mark.parametrize("phase", ["before_lock", "after_lock", "ancestor_after_lock"])
def test_identity_and_ancestor_changes_release_and_close(fake_io, monkeypatch, phase):
    changed = SimpleNamespace(**vars(fake_io.info))
    changed.st_ino += 1
    if phase == "before_lock":
        monkeypatch.setattr(lock.os, "fstat", lambda descriptor: changed)
    elif phase == "after_lock":
        fake_io.inspect.side_effect = [fake_io.info, changed]
    else:
        fake_io.inspect.side_effect = [fake_io.info, ValueError("ancestor reparse")]
    lease = lock.new_cleanup_lease(CONNECTION, LOCK)
    with pytest.raises(ReadError) as caught:
        lease.acquire()
    assert_safe(caught.value, "cleanup_lock_invalid")
    assert fake_io.handle.closed
    assert fake_io.operations == ([] if phase == "before_lock" else [False, True])


def test_unlock_failure_still_closes_handle(fake_io, monkeypatch):
    lease = lock.new_cleanup_lease(CONNECTION, LOCK)
    lease.acquire()
    monkeypatch.setattr(lock, "_lock_fd", Mock(side_effect=OSError(CONNECTION)))
    with pytest.raises(ReadError) as caught:
        lease.close()
    assert_safe(caught.value, "cleanup_lock_release_failed")
    assert fake_io.handle.closed
    lease.close()


def test_non_windows_fails_without_io(fake_io, monkeypatch):
    monkeypatch.setattr(lock, "_is_windows", lambda: False)
    lease = lock.new_cleanup_lease(CONNECTION, LOCK)
    with pytest.raises(ReadError) as caught:
        lease.acquire()
    assert_safe(caught.value, "cleanup_lock_windows_required")
    fake_io.inspect.assert_not_called()
    fake_io.open_file.assert_not_called()


def test_native_wrapper_uses_original_nonblocking_one_byte_modes(monkeypatch):
    import msvcrt

    native = Mock()
    monkeypatch.setattr(msvcrt, "locking", native)
    lock._lock_fd(19, release=False)
    lock._lock_fd(19, release=True)
    assert native.call_args_list[0].args == (19, msvcrt.LK_NBLCK, 1)
    assert native.call_args_list[1].args == (19, msvcrt.LK_UNLCK, 1)


@pytest.mark.skipif(os.name != "nt", reason="original locking protocol is Windows-only")
@pytest.mark.parametrize("original_first", [True, False])
def test_original_and_adapter_exclude_each_other_on_dummy_file(
    tmp_path, monkeypatch, original_first
):
    import msvcrt

    dummy = tmp_path / "synthetic-operation.lock"
    dummy.write_bytes(b"0")
    monkeypatch.setattr(lock, "_inspect_lock", lambda path: dummy.lstat())
    monkeypatch.setattr(lock, "_open_existing_lock", lambda path: dummy.open("r+b", buffering=0))
    lease = lock.new_cleanup_lease(CONNECTION, LOCK)
    with dummy.open("a+b") as original:
        if original_first:
            original.seek(0)
            msvcrt.locking(original.fileno(), msvcrt.LK_NBLCK, 1)
            try:
                with pytest.raises(ReadError) as caught:
                    lease.acquire()
                assert_safe(caught.value, "cleanup_lock_unavailable")
            finally:
                original.seek(0)
                msvcrt.locking(original.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            lease.acquire()
            try:
                original.seek(0)
                with pytest.raises(OSError):
                    msvcrt.locking(original.fileno(), msvcrt.LK_NBLCK, 1)
            finally:
                lease.close()
    lease.close()
    assert dummy.read_bytes() == b"0"


def test_real_open_requires_existing_file_and_never_seeds(tmp_path):
    missing = tmp_path / "synthetic-missing.lock"
    with pytest.raises(FileNotFoundError):
        lock._open_existing_lock(missing)
    assert not missing.exists()
    existing = tmp_path / "synthetic-existing.lock"
    existing.write_bytes(b"0")
    with lock._open_existing_lock(existing) as handle:
        assert handle.read() == b"0"
    assert existing.read_bytes() == b"0"


def test_inspection_uses_existing_local_path_guards_only(monkeypatch):
    from doi_draft_transfer import local_auth

    sentinel = object()
    inspect = Mock(return_value=sentinel)
    monkeypatch.setattr(local_auth, "_local_regular_path", inspect)
    synthetic = Path("synthetic-only.lock")
    assert lock._inspect_lock(synthetic) is sentinel
    inspect.assert_called_once_with(synthetic)
