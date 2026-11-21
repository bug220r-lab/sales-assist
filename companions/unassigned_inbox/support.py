"""Local-only configuration and durable files for the optional reader."""
from __future__ import annotations

from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import uuid

from .reader import positive_id, utc_now


REPO_ROOT = Path(__file__).resolve().parents[2]


def _outside_repo(path):
    resolved = Path(path).resolve()
    if resolved == REPO_ROOT or REPO_ROOT in resolved.parents:
        raise ValueError("Configuration, credentials and runtime must be outside the repository")
    return resolved


def read_json(path, *, max_bytes=512_000_000):
    path = Path(path)
    if path.stat().st_size > max_bytes:
        raise ValueError("Local JSON exceeds the size limit")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("Local JSON must be an object")
    return value


def write_json(path, value):
    """Replace one file after a flushed temporary file, before starting reads."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temp.open("x", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def configuration(path):
    if not path:
        raise ValueError("An external --config path is required")
    source = Path(path)
    if not source.is_absolute():
        raise ValueError("Use an absolute external --config path")
    source = _outside_repo(source)
    data = read_json(source, max_bytes=1_000_000)
    if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise ValueError("Unsupported configuration schema")
    for key in ("auth_path", "runtime_dir"):
        raw = data.get(key)
        if not isinstance(raw, str) or not raw or not Path(raw).is_absolute():
            raise ValueError(f"{key} must be an absolute external path")
        data[key] = _outside_repo(raw)
    if data["auth_path"] == data["runtime_dir"] or data["auth_path"] in data["runtime_dir"].parents:
        raise ValueError("Credentials and runtime must use separate paths")
    if not isinstance(data.get("expected_user_name"), str) or not data["expected_user_name"].strip():
        raise ValueError("An expected user name is required")
    data["user_id_hint"] = positive_id(data.get("user_id_hint"))
    boxes = data.get("mailboxes")
    if not isinstance(boxes, dict) or not boxes:
        raise ValueError("At least one explicit mailbox is required")
    for selector, box in boxes.items():
        if not isinstance(selector, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", selector):
            raise ValueError("Invalid mailbox selector")
        if not isinstance(box, dict):
            raise ValueError("Mailbox configuration is invalid")
        box["id"] = positive_id(box.get("id"))
        for key in ("name", "email"):
            if not isinstance(box.get(key), str) or not box[key].strip() or any(c in box[key] for c in "\r\n"):
                raise ValueError("Mailbox name and email are required")
        if "@" not in box["email"]:
            raise ValueError("Mailbox email is invalid")
    return data


def resolve_scope(reader, cfg, selector):
    box = cfg["mailboxes"].get(selector)
    if box is None:
        raise ValueError("Mailbox selector is not configured")
    me = reader.get_identity()
    user = reader.get_user(cfg["user_id_hint"])
    def name(value):
        return (str(value.get("firstName", value.get("first", ""))) + " " +
                str(value.get("lastName", value.get("last", "")))).strip().casefold()
    expected = cfg["expected_user_name"].strip().casefold()
    if (user.get("id") != cfg["user_id_hint"] or name(user) != expected or
            user.get("type", "user") not in {"user", None} or user.get("status", "active") != "active" or
            not isinstance(user.get("email"), str) or "@" not in user["email"]):
        raise ValueError("Configured user identity did not match the live Help Scout user")
    if (me.get("id") != user["id"] or name(me) != expected or
            str(me.get("email", "")).casefold() != user["email"].casefold()):
        raise ValueError("Authenticated identity differs from the configured user")
    live = reader.get_mailbox(box["id"])
    if (live.get("id") != box["id"] or live.get("name") != box["name"] or
            str(live.get("email", "")).casefold() != box["email"].casefold()):
        raise ValueError("Configured mailbox does not match the live Help Scout mailbox")
    return {"user_id": user["id"], "user_name": cfg["expected_user_name"],
            "user_email": user["email"], "mailbox_id": live["id"],
            "mailbox_name": live["name"], "mailbox_email": live["email"],
            "mailbox_selector": selector, "verified_at_utc": utc_now()}


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        if tag in {"p", "div", "br", "li"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)
        if tag in {"p", "div", "li"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def plain_text(body):
    parser = _Text()
    parser.feed(str(body or ""))
    return re.sub(r"[ \t]+", " ", "".join(parser.parts)).strip()


class ReadLock:
    """OS-held lock for one external run directory; the file is not a status flag."""

    def __init__(self, path):
        self.path = Path(path)
        self.handle = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+b")
        self.handle.seek(0, os.SEEK_END)
        if self.handle.tell() == 0:
            self.handle.write(b"0")
            self.handle.flush()
        self.handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError):
            self.handle.close()
            self.handle = None
            raise RuntimeError("This local read run is already in progress") from None
        return self

    def __exit__(self, *_):
        if self.handle is not None:
            try:
                self.handle.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            finally:
                self.handle.close()
                self.handle = None
