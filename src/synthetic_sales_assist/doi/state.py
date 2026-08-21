"""Copy-on-write in-memory composition for pure Milestone 3 DOI reducers.

Source/run serialization is owned exclusively by :mod:`synthetic_sales_assist.doi.source`.
This coordinator composes that authority with lifecycle streams without reimplementing any
run-control command or business guard.
"""

from __future__ import annotations

from collections.abc import Callable
from threading import RLock
from types import MappingProxyType
from typing import TypeVar

from synthetic_sales_assist.doi.lifecycle import (
    LifecycleConflictError,
    LifecycleSchemaError,
    TransitionCommand,
    TransitionResult,
    TransitionStream,
    reduce_fixture_transition,
    reduce_transition,
    transition_definition,
)
from synthetic_sales_assist.doi.source import InMemoryDOIRunControl
from synthetic_sales_assist.domain.identities import EvidenceId
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp


_ResultT = TypeVar("_ResultT")
FaultInjector = Callable[[_ResultT], None]


# Only unambiguous aggregate/entity creation rows may establish a lifecycle stream.
# Attention creation is owned by AttentionStream and source-import creation is owned by
# InMemoryDOIRunControl, so neither may be bootstrapped through this coordinator.
_ABSENT_STREAM_CREATION_FROM_STATES = MappingProxyType(
    {
        "TR-001": "NONEXISTENT",
        "TR-007": "NONEXISTENT",
        "TR-042": "NONEXISTENT",
        "TR-044": "NONEXISTENT",
        "TR-045": "NONEXISTENT",
        "TR-045A": "NONEXISTENT",
        "TR-054": (
            "exact link NONEXISTENT; separate search absent/NOT_FOUND/AMBIGUOUS"
        ),
        "TR-055": (
            "exact link NONEXISTENT; separate search absent/NOT_FOUND/AMBIGUOUS"
        ),
        "TR-082": "relationship NONEXISTENT",
        "TR-084": "Action Context NONEXISTENT",
    }
)


def absent_stream_creation_transition_ids() -> tuple[str, ...]:
    """Return the closed transition IDs allowed to create a coordinator stream."""

    return tuple(sorted(_ABSENT_STREAM_CREATION_FROM_STATES))


class InMemoryDoiState:
    """Compose the authoritative source controller and atomic lifecycle streams.

    Lifecycle events and their replay material share one owner-scoped stream. Candidate
    streams are reduced before publication, so injected faults and rejected guards leave the
    retained state byte-for-byte unchanged. This class is test-only, not durable storage.
    """

    def __init__(self, *, source_run_control: InMemoryDOIRunControl | None = None) -> None:
        if source_run_control is not None and type(
            source_run_control
        ) is not InMemoryDOIRunControl:
            raise LifecycleSchemaError("SOURCE_RUN_CONTROL_INVALID")
        self.source_run_control = source_run_control or InMemoryDOIRunControl()
        self._streams: dict[EvidenceId, TransitionStream] = {}
        self._lock = RLock()

    def execute(
        self,
        command: TransitionCommand,
        *,
        occurred_at: CanonicalTimestamp,
        fault_injector: FaultInjector[TransitionResult] | None = None,
    ) -> TransitionResult:
        """Reduce and atomically publish one lifecycle command after all checks pass."""

        return self._execute(
            command,
            occurred_at=occurred_at,
            fault_injector=fault_injector,
            fixture_mode=False,
        )

    def execute_fixture(
        self,
        command: TransitionCommand,
        *,
        occurred_at: CanonicalTimestamp,
        fault_injector: FaultInjector[TransitionResult] | None = None,
    ) -> TransitionResult:
        """Exercise coordinator mechanics with structural registry fixture evidence."""

        return self._execute(
            command,
            occurred_at=occurred_at,
            fault_injector=fault_injector,
            fixture_mode=True,
        )

    def _execute(
        self,
        command: TransitionCommand,
        *,
        occurred_at: CanonicalTimestamp,
        fault_injector: FaultInjector[TransitionResult] | None,
        fixture_mode: bool,
    ) -> TransitionResult:
        """Publish one already-reduced candidate under the coordinator lock."""

        if type(command) is not TransitionCommand:
            raise LifecycleSchemaError("STATE_COMMAND_INVALID")
        if fault_injector is not None and not callable(fault_injector):
            raise LifecycleSchemaError("STATE_FAULT_INJECTOR_INVALID")
        with self._lock:
            current = self._streams.get(command.stream_id)
            if current is None:
                definition = transition_definition(command.transition)
                expected_from = _ABSENT_STREAM_CREATION_FROM_STATES.get(
                    command.transition.transition_id
                )
                if expected_from is None or definition.from_state != expected_from:
                    raise LifecycleConflictError(
                        "STATE_STREAM_CREATION_TRANSITION_INVALID"
                    )
                current = TransitionStream.initial(
                    stream_id=command.stream_id,
                    state=definition.from_state,
                )
            reducer = reduce_fixture_transition if fixture_mode else reduce_transition
            candidate = reducer(current, command, occurred_at=occurred_at)
            if fault_injector is not None:
                fault_injector(candidate)
            if not candidate.replayed:
                updated = dict(self._streams)
                updated[command.stream_id] = candidate.stream
                self._streams = updated
            return candidate

    def stream(self, stream_id: EvidenceId) -> TransitionStream | None:
        if type(stream_id) is not EvidenceId:
            raise LifecycleSchemaError("STATE_STREAM_ID_INVALID")
        with self._lock:
            return self._streams.get(stream_id)

    def delete_owner_stream(
        self,
        stream_id: EvidenceId,
        *,
        expected_head_sha256: str,
    ) -> None:
        """Delete an owner stream and replay bytes, retaining no identity tombstone."""

        if type(stream_id) is not EvidenceId or type(expected_head_sha256) is not str:
            raise LifecycleSchemaError("STATE_DELETE_INPUT_INVALID")
        with self._lock:
            current = self._streams.get(stream_id)
            if current is None:
                return
            if current.projection.head_sha256 != expected_head_sha256:
                raise LifecycleConflictError("STATE_DELETE_HEAD_CONFLICT")
            updated = dict(self._streams)
            del updated[stream_id]
            self._streams = updated

    @property
    def stream_count(self) -> int:
        with self._lock:
            return len(self._streams)

    @property
    def retained_event_count(self) -> int:
        with self._lock:
            return sum(len(stream.events) for stream in self._streams.values())


__all__ = ["InMemoryDoiState", "absent_stream_creation_transition_ids"]
