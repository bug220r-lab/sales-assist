"""Internal immutable closed-string token base for shared domain enumerations."""

from __future__ import annotations

from enum import StrEnum
from types import MappingProxyType
from typing import Any


class ImmutableStrEnum(StrEnum):
    """A closed string enum whose public state cannot mutate after initialization.

    ``Enum`` normally exposes each member's writable implementation dictionary.  A
    frozen domain record that retained such a member could therefore serialize
    differently after construction.  The public dictionary is a read-only view,
    and ``value`` is derived from the immutable ``str`` payload rather than the
    writable Enum bookkeeping slot.  The latter is deliberate defense in depth
    against callers that bypass normal attribute access with ``object`` helpers.
    """

    @property
    def value(self) -> str:
        return str.__str__(self)

    def __getattribute__(self, name: str) -> Any:
        value = super().__getattribute__(name)
        if name == "__dict__":
            return MappingProxyType(value)
        return value

    def __setattr__(self, name: str, value: object) -> None:
        enum_initialization = name in {"__objclass__", "_sort_order_"} and not hasattr(
            self, name
        )
        if hasattr(self, "_name_") and not enum_initialization:
            raise AttributeError("immutable enum member")
        super().__setattr__(name, value)

    def __delattr__(self, name: str) -> None:
        raise AttributeError("immutable enum member")

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<closed>)"


__all__ = ["ImmutableStrEnum"]
