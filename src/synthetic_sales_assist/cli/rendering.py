"""Stable CLI envelopes and intentionally small human rendering."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Final, TextIO


CLI_SCHEMA_VERSION: Final = "synthetic-sales-assist-cli/v1"


@dataclass(frozen=True, slots=True)
class CLIEnvelope:
    command: str
    ok: bool
    result: dict[str, object] | list[object] | None
    errors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "command": self.command,
            "errors": list(self.errors),
            "ok": self.ok,
            "result": self.result,
            "schema_version": CLI_SCHEMA_VERSION,
        }


def render_json(envelope: CLIEnvelope, stream: TextIO) -> None:
    stream.write(
        json.dumps(
            envelope.to_dict(),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    )


def _human_value(value: object) -> str:
    if value is None:
        return "not available"
    if type(value) is bool:
        return "yes" if value else "no"
    if isinstance(value, (list, tuple)):
        return ", ".join(_human_value(item) for item in value) if value else "none"
    if isinstance(value, dict):
        return ", ".join(
            f"{key}={_human_value(item)}" for key, item in sorted(value.items())
        )
    return str(value)


def render_human(envelope: CLIEnvelope, stream: TextIO) -> None:
    if not envelope.ok:
        stream.write(f"{envelope.command}: FAILED ({', '.join(envelope.errors)})\n")
        return
    stream.write(f"{envelope.command}: OK\n")
    result = envelope.result
    if isinstance(result, dict):
        for key, value in sorted(result.items()):
            stream.write(f"{key.replace('_', ' ')}: {_human_value(value)}\n")
    elif isinstance(result, list):
        for item in result:
            stream.write(f"- {_human_value(item)}\n")


__all__ = ["CLI_SCHEMA_VERSION", "CLIEnvelope", "render_human", "render_json"]
