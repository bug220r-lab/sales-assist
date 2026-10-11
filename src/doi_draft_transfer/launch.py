"""Explicit, isolated draft-review runtime; daily DOI policy is not its authority."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path

from synthetic_sales_assist.persistence.paths import validate_local_path
from synthetic_sales_assist.portal.lifecycle import (
    RuntimeReceipt, SingleInstanceLease, new_local_token, process_start_time,
)
from synthetic_sales_assist.portal.server import PortalHTTPServer, PortalServerConfig

from .contract import MAILBOX_ID, USER_ID, TransferError
from .helpscout import HelpScoutDraftClient
from .store import DraftTransferStore, FILENAME

CONFIG_NAME = "draft-only-launch.json"
RECEIPT_NAME = "draft-service.json"
SCHEMA = "ssa-draft-only-launch/v1"
CONFIG_KEYS = {
    "schema", "enabled", "data_dir", "port", "mailbox_id", "user_id", "allow_draft_create",
}


class DraftLaunchError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def private_path(value):
    """Local fixed storage only; reject sync roots, repositories and linked ancestors."""
    if not isinstance(value, (str, Path)):
        raise DraftLaunchError("DRAFT_PRIVATE_PATH_INVALID")
    raw = str(value)
    path = Path(raw)
    if (
        not path.is_absolute()
        or raw.startswith(("\\\\", "//"))
        or re.search(r"(^|[\\/])\.\.?([\\/]|$)", raw)
        or any(ord(c) < 32 or c == '"' for c in raw)
        or os.name == "nt" and (not re.match(r"^[A-Za-z]:[\\/]", raw) or ":" in raw[2:])
    ):
        raise DraftLaunchError("DRAFT_PRIVATE_PATH_INVALID")
    sync = re.compile(r"OneDrive(?: - .+)?|Dropbox|Google Drive|iCloudDrive", re.I)
    if any(sync.fullmatch(part) for part in path.parts):
        raise DraftLaunchError("DRAFT_SYNCHRONIZED_PATH_PROHIBITED")
    folded = tuple(part.casefold() for part in path.parts)
    for name in ("OneDrive", "OneDriveCommercial", "OneDriveConsumer"):
        known = os.environ.get(name)
        if known:
            root = Path(known)
            parts = tuple(part.casefold() for part in root.parts)
            if not root.is_absolute() or folded[:len(parts)] == parts:
                raise DraftLaunchError("DRAFT_SYNCHRONIZED_PATH_PROHIBITED")
    if os.name == "nt":
        import ctypes

        drive = ctypes.windll.kernel32.GetDriveTypeW
        drive.argtypes, drive.restype = [ctypes.c_wchar_p], ctypes.c_uint
        if drive(path.anchor) != 3:
            raise DraftLaunchError("DRAFT_FIXED_LOCAL_DISK_REQUIRED")
    for candidate in (*reversed(path.parents), path):
        try:
            info = candidate.lstat()
        except FileNotFoundError:
            continue
        if (
            stat.S_ISLNK(info.st_mode)
            or getattr(info, "st_file_attributes", 0) & 0x400
            or stat.S_ISREG(info.st_mode) and info.st_nlink != 1
        ):
            raise DraftLaunchError("DRAFT_LINKED_PATH_PROHIBITED")
        if stat.S_ISDIR(info.st_mode) and (candidate / ".git").exists():
            raise DraftLaunchError("DRAFT_REPOSITORY_PATH_PROHIBITED")
    return validate_local_path(path)


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DraftLaunchError("DRAFT_CONFIGURATION_INVALID")
        result[key] = value
    return result


def check_layout(root):
    """Never open or migrate a normal app/DOI review root or another journal."""
    allowed = {
        root: {CONFIG_NAME, "data", "runtime"},
        root / "data": {FILENAME, FILENAME + "-journal", FILENAME + "-wal", FILENAME + "-shm"},
        root / "runtime": {RECEIPT_NAME, RECEIPT_NAME + ".lock"},
    }
    for folder, names in allowed.items():
        private_path(folder)
        if folder.exists():
            if not folder.is_dir():
                raise DraftLaunchError("DRAFT_DEDICATED_ROOT_REQUIRED")
            for entry in folder.iterdir():
                if entry.name not in names:
                    raise DraftLaunchError("DRAFT_DEDICATED_ROOT_REQUIRED")
                private_path(entry)
                if entry.name not in {"data", "runtime"} and not entry.is_file():
                    raise DraftLaunchError("DRAFT_DEDICATED_ROOT_REQUIRED")


def read_config(config_file):
    try:
        path = private_path(config_file)
        if path.name != CONFIG_NAME:
            raise DraftLaunchError("DRAFT_CONFIGURATION_PATH_INVALID")
        with path.open("rb") as stream:
            raw = stream.read(8193)
        if len(raw) > 8192:
            raise DraftLaunchError("DRAFT_CONFIGURATION_INVALID")
        value = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_unique)
        if (
            type(value) is not dict or set(value) != CONFIG_KEYS
            or value["schema"] != SCHEMA
            or type(value["enabled"]) is not bool
            or type(value["allow_draft_create"]) is not bool
            or type(value["port"]) is not int or not 0 <= value["port"] <= 65535
            or type(value["mailbox_id"]) is not int or value["mailbox_id"] != MAILBOX_ID
            or type(value["user_id"]) is not int or value["user_id"] != USER_ID
        ):
            raise DraftLaunchError("DRAFT_CONFIGURATION_INVALID")
        if not value["enabled"]:
            raise DraftLaunchError("DRAFT_MODE_DISABLED")
        root = private_path(value["data_dir"])
        if path.parent != root:
            raise DraftLaunchError("DRAFT_CONFIGURATION_ROOT_MISMATCH")
        check_layout(root)
        return value, hashlib.sha256(raw).hexdigest()
    except DraftLaunchError:
        raise
    except (OSError, ValueError, TypeError, RecursionError):
        raise DraftLaunchError("DRAFT_CONFIGURATION_INVALID") from None


class DraftOnlyRuntime:
    def __init__(self, config_file):
        self.config_file = config_file
        self.server = None
        self.lease = None

    def start(self):
        if self.lease is not None:
            raise DraftLaunchError("DRAFT_RUNTIME_ALREADY_STARTED")
        config, fingerprint = read_config(self.config_file)
        root = Path(config["data_dir"])
        receipt_path = root / "runtime" / RECEIPT_NAME
        lease = SingleInstanceLease(receipt_path)
        identity, csrf, shutdown = (new_local_token() for _ in range(3))
        try:
            lease.acquire(identity)
            self.lease = lease
            if read_config(self.config_file)[1] != fingerprint:
                raise DraftLaunchError("DRAFT_CONFIGURATION_CHANGED_DURING_START")
            (root / "data").mkdir(exist_ok=True)
            store = DraftTransferStore(root / "data" / FILENAME)
            store.checked_path()
            client = None
            if config["allow_draft_create"]:
                client = HelpScoutDraftClient.from_environment()
                if client is None:
                    raise DraftLaunchError("DRAFT_TRANSFER_SEPARATE_ACTIVATION_REQUIRED")
            self.server = PortalHTTPServer(
                None, PortalServerConfig("127.0.0.1", config["port"]),
                csrf_token=csrf, shutdown_token=shutdown, draft_transfer_only=True,
                draft_transfer_store=store, draft_transfer_client=client,
            )
            receipt = RuntimeReceipt(
                schema_version="synthetic-sales-assist-runtime-receipt/v1",
                pid=os.getpid(), process_start_time=process_start_time(),
                process_identity_token=identity, csrf_token=csrf, host="127.0.0.1",
                port=self.server.server_port, shutdown_token=shutdown,
                database_path=str(store.path), database_schema_version=1,
                app_version="draft-only-v1", build_version="draft-only/v1:" + fingerprint,
                origin=self.server.origin,
            )
            lease.publish(receipt)
            return receipt
        except Exception:
            self.close()
            raise

    def serve_forever(self):
        if self.server is None:
            raise DraftLaunchError("DRAFT_RUNTIME_NOT_STARTED")
        try:
            self.server.serve_forever(poll_interval=0.1)
        finally:
            self.close()

    def close(self):
        if self.server is not None:
            self.server.server_close()
            client = self.server.draft_transfer.client
            if isinstance(client, HelpScoutDraftClient):
                client.close()
            self.server = None
        if self.lease is not None:
            self.lease.release()
            self.lease = None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    runtime = DraftOnlyRuntime(args.config)
    try:
        if args.check:
            config, _ = read_config(args.config)
            print(json.dumps({"mode": SCHEMA, "allow_draft_create": config["allow_draft_create"]}))
            return 0
        receipt = runtime.start()
        print(f"Draft review ready at {receipt.origin}/doi-draft-transfer", flush=True)
        runtime.serve_forever()
        return 0
    except KeyboardInterrupt:
        return 0
    except (DraftLaunchError, TransferError) as exc:
        print("DRAFT_START_FAILED:" + exc.code, file=sys.stderr)
        return 1
    except Exception:
        print("DRAFT_START_FAILED:LOCAL_RUNTIME_UNAVAILABLE", file=sys.stderr)
        return 1
    finally:
        runtime.close()
