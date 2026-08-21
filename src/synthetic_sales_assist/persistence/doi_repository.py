"""Durable, lossless SQLite repository for the Milestone 3 DOI domain.

The repository deliberately accepts validated domain records rather than dictionaries.  A
closed JSON envelope preserves the Python domain graph needed to return those same types,
while every hash-bearing record also retains and verifies its authoritative domain, digest,
and canonical bytes.  Repository methods never commit; the application service owns the
transaction boundary.
"""

from __future__ import annotations

import base64
import dataclasses
import hashlib
import importlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from types import ModuleType
from typing import Final, TypeVar, cast

from synthetic_sales_assist.doi.identities import LineSnapshotId
from synthetic_sales_assist.doi.case_attention import (
    CaseOwnerDecision,
    DOICaseSourceAdmissionProofV1,
    OwnedCaseSourceBinding,
    validate_case_owner_decision,
)
from synthetic_sales_assist.doi.extraction import (
    DOIExtractionAttempt,
    DOIExtractionResult,
    ExtractionStatus,
)
from synthetic_sales_assist.doi.interventions import DOIIntervention
from synthetic_sales_assist.doi.interventions import (
    DOIResultingOrderLink,
    DOIResultingOrderLinkSearch,
    DOIResultingOrderLinkSearchHistory,
    ResultingLinkSearchEvent,
)
from synthetic_sales_assist.doi.knowledge import (
    DOIAlternateObservation,
    DOIAlternateRelationship,
    DOIAlternateRelationshipRevision,
    DOIExactSKUObservation,
)
from synthetic_sales_assist.doi.models import (
    CaseLifecycleState,
    DOIEvaluation,
    DOILineItemSnapshot,
    DOIOpportunity,
    DOIOrderCase,
    DOIOrderSnapshot,
    LineContinuityProof,
)
from synthetic_sales_assist.doi.retention import (
    DoiRetentionProjection,
    KPIContributionEvent,
    RetainedKPIContribution,
)
from synthetic_sales_assist.doi.source import (
    DOIRun,
    DOIRunEvent,
    DOIRunWorkDisposition,
    DOIRunWorkItem,
    DOISourceBatch,
    DOISourceImportAttempt,
    DOISourceImportAttemptEvent,
    RunStatus,
    SourceImportResult,
    SourceImportResultKind,
)
from synthetic_sales_assist.domain.canonical import (
    HashBinding,
    canonical_json_bytes,
    domain_hash,
    parse_canonical_json_bytes,
)
from synthetic_sales_assist.domain.identities import EvidenceId
from synthetic_sales_assist.domain.observed import (
    KnownObservedValue,
    NotApplicableObservedValue,
    UnknownObservedValue,
)
from synthetic_sales_assist.domain.registries import (
    ReasonRef,
    TransitionRef,
    load_doi_registries,
)
from synthetic_sales_assist.domain.records import WholeOrderCompletenessProof
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp
from synthetic_sales_assist.persistence.faults import FaultInjector, FaultPoint


class DOIPersistenceError(RuntimeError):
    """Base DOI persistence failure with no source payload reflection."""


class DOIPersistenceConflict(DOIPersistenceError):
    """A retained natural key was presented with different immutable material."""


class DOIPersistenceIntegrityError(DOIPersistenceError):
    """Stored DOI material is malformed or inconsistent with its hash/projection."""


@dataclass(frozen=True, slots=True)
class PersistenceResult:
    replayed: bool


@dataclass(frozen=True, slots=True)
class ProjectionVerification:
    run_projection_count: int
    case_projection_count: int
    owner_stream_count: int
    intervention_projection_count: int
    errors: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass(frozen=True, slots=True)
class PurgeResult:
    deleted: bool
    finalized_contribution_count: int
    deleted_run_count: int


@dataclass(frozen=True, slots=True)
class DOIOwnerEventRecord:
    stream_family: str
    event_id: str
    projection_state: str
    occurred_at: CanonicalTimestamp
    transition_id: str | None


@dataclass(frozen=True, slots=True)
class DOIInterventionHistoryRecord:
    intervention: DOIIntervention
    created_at: CanonicalTimestamp


@dataclass(frozen=True, slots=True)
class _EncodedRecord:
    payload: bytes
    binding: HashBinding


_CLOSED_MODULE_NAMES: Final = (
    "synthetic_sales_assist.domain.canonical",
    "synthetic_sales_assist.domain.identities",
    "synthetic_sales_assist.domain.numeric",
    "synthetic_sales_assist.domain.observed",
    "synthetic_sales_assist.domain.records",
    "synthetic_sales_assist.domain.registries",
    "synthetic_sales_assist.domain.timestamps",
    "synthetic_sales_assist.doi.identities",
    "synthetic_sales_assist.doi.models",
    "synthetic_sales_assist.doi.source",
    "synthetic_sales_assist.doi.extraction",
    "synthetic_sales_assist.doi.knowledge",
    "synthetic_sales_assist.doi.case_attention",
    "synthetic_sales_assist.doi.interventions",
    "synthetic_sales_assist.doi.lifecycle",
    "synthetic_sales_assist.doi.retention",
)
_MAX_PAYLOAD_BYTES: Final = 16 * 1024 * 1024


def _closed_types() -> dict[str, type[object]]:
    result: dict[str, type[object]] = {}
    for module_name in _CLOSED_MODULE_NAMES:
        module: ModuleType = importlib.import_module(module_name)
        for value in vars(module).values():
            if not isinstance(value, type):
                continue
            if not (
                dataclasses.is_dataclass(value)
                or issubclass(value, Enum)
            ):
                continue
            if value.__module__ not in _CLOSED_MODULE_NAMES:
                continue
            tag = f"{value.__module__}:{value.__qualname__}"
            result[tag] = value
    return result


_CLOSED_TYPES: Final = _closed_types()


def _tag(value_type: type[object]) -> str:
    tag = f"{value_type.__module__}:{value_type.__qualname__}"
    if _CLOSED_TYPES.get(tag) is not value_type:
        raise DOIPersistenceIntegrityError("DOI_PAYLOAD_TYPE_NOT_CLOSED")
    return tag


def _pack(value: object) -> object:
    if value is None or type(value) in {bool, int, str}:
        return value
    if type(value) is bytes:
        return {"$bytes": base64.b64encode(cast(bytes, value)).decode("ascii")}
    if type(value) is Decimal:
        return {"$decimal": str(value)}
    if type(value) is date:
        return {"$date": cast(date, value).isoformat()}
    if type(value) is tuple:
        return {"$tuple": [_pack(item) for item in cast(tuple[object, ...], value)]}
    if type(value) is frozenset:
        packed = [_pack(item) for item in cast(frozenset[object], value)]
        packed.sort(key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")))
        return {"$frozenset": packed}
    if isinstance(value, Enum):
        return {"$enum": _tag(type(value)), "value": value.value}
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        value_type = type(value)
        if value_type is CanonicalTimestamp:
            return {"$timestamp": cast(CanonicalTimestamp, value).value}
        if value_type is ReasonRef:
            reason = cast(ReasonRef, value)
            return {
                "$reason": reason.code,
                "label": reason.label,
                "registry_version": reason.registry_version,
            }
        if value_type is TransitionRef:
            transition = cast(TransitionRef, value)
            return {
                "$transition": transition.transition_id,
                "registry_version": transition.registry_version,
            }
        if value_type is KnownObservedValue:
            return {"$known": _pack(cast(KnownObservedValue[object], value).value)}
        if value_type is UnknownObservedValue:
            unknown = cast(UnknownObservedValue, value)
            return {"$unknown": unknown.reason_code, "raw_hint": unknown.raw_hint}
        if value_type is NotApplicableObservedValue:
            return {"$not_applicable": True}
        dataclass_type = cast(type[object], value_type)
        params = getattr(dataclass_type, "__dataclass_params__")
        include_all = not params.init
        fields = {
            field.name: _pack(getattr(value, field.name))
            for field in dataclasses.fields(value)
            if include_all or field.init
        }
        return {"$dataclass": _tag(dataclass_type), "fields": fields}
    raise DOIPersistenceIntegrityError("DOI_PAYLOAD_VALUE_NOT_CLOSED")


def _require_exact_members(value: dict[str, object], expected: set[str]) -> None:
    if set(value) != expected:
        raise DOIPersistenceIntegrityError("DOI_PAYLOAD_MEMBERS_INVALID")


def _unpack(value: object) -> object:
    if value is None or type(value) in {bool, int, str}:
        return value
    if type(value) is not dict:
        raise DOIPersistenceIntegrityError("DOI_PAYLOAD_NODE_INVALID")
    node = cast(dict[str, object], value)
    if "$bytes" in node:
        _require_exact_members(node, {"$bytes"})
        try:
            return base64.b64decode(cast(str, node["$bytes"]), validate=True)
        except Exception as exc:
            raise DOIPersistenceIntegrityError("DOI_PAYLOAD_BYTES_INVALID") from exc
    if "$decimal" in node:
        _require_exact_members(node, {"$decimal"})
        try:
            return Decimal(cast(str, node["$decimal"]))
        except Exception as exc:
            raise DOIPersistenceIntegrityError("DOI_PAYLOAD_DECIMAL_INVALID") from exc
    if "$date" in node:
        _require_exact_members(node, {"$date"})
        try:
            parsed = date.fromisoformat(cast(str, node["$date"]))
        except Exception as exc:
            raise DOIPersistenceIntegrityError("DOI_PAYLOAD_DATE_INVALID") from exc
        if parsed.isoformat() != node["$date"]:
            raise DOIPersistenceIntegrityError("DOI_PAYLOAD_DATE_INVALID")
        return parsed
    if "$tuple" in node:
        _require_exact_members(node, {"$tuple"})
        if type(node["$tuple"]) is not list:
            raise DOIPersistenceIntegrityError("DOI_PAYLOAD_TUPLE_INVALID")
        return tuple(_unpack(item) for item in cast(list[object], node["$tuple"]))
    if "$frozenset" in node:
        _require_exact_members(node, {"$frozenset"})
        if type(node["$frozenset"]) is not list:
            raise DOIPersistenceIntegrityError("DOI_PAYLOAD_SET_INVALID")
        return frozenset(_unpack(item) for item in cast(list[object], node["$frozenset"]))
    if "$enum" in node:
        _require_exact_members(node, {"$enum", "value"})
        enum_type = _CLOSED_TYPES.get(cast(str, node["$enum"]))
        if enum_type is None or not issubclass(enum_type, Enum):
            raise DOIPersistenceIntegrityError("DOI_PAYLOAD_ENUM_INVALID")
        try:
            return enum_type(node["value"])
        except Exception as exc:
            raise DOIPersistenceIntegrityError("DOI_PAYLOAD_ENUM_INVALID") from exc
    if "$timestamp" in node:
        _require_exact_members(node, {"$timestamp"})
        try:
            return CanonicalTimestamp.from_sqlite_text(node["$timestamp"])
        except Exception as exc:
            raise DOIPersistenceIntegrityError("DOI_PAYLOAD_TIMESTAMP_INVALID") from exc
    if "$reason" in node:
        _require_exact_members(node, {"$reason", "label", "registry_version"})
        try:
            reason = load_doi_registries().reason_ref(cast(str, node["$reason"]))
        except Exception as exc:
            raise DOIPersistenceIntegrityError("DOI_PAYLOAD_REASON_INVALID") from exc
        if reason.label != node["label"] or reason.registry_version != node["registry_version"]:
            raise DOIPersistenceIntegrityError("DOI_PAYLOAD_REASON_DRIFT")
        return reason
    if "$transition" in node:
        _require_exact_members(node, {"$transition", "registry_version"})
        try:
            transition = load_doi_registries().transition_ref(
                cast(str, node["$transition"])
            )
        except Exception as exc:
            raise DOIPersistenceIntegrityError("DOI_PAYLOAD_TRANSITION_INVALID") from exc
        if transition.registry_version != node["registry_version"]:
            raise DOIPersistenceIntegrityError("DOI_PAYLOAD_TRANSITION_DRIFT")
        return transition
    if "$known" in node:
        _require_exact_members(node, {"$known"})
        from synthetic_sales_assist.doi.models import known_fact

        return known_fact(_unpack(node["$known"]))
    if "$unknown" in node:
        _require_exact_members(node, {"$unknown", "raw_hint"})
        from synthetic_sales_assist.doi.models import unknown_fact

        return unknown_fact(
            cast(str, node["$unknown"]),
            raw_hint=cast(str | None, node["raw_hint"]),
        )
    if "$not_applicable" in node:
        _require_exact_members(node, {"$not_applicable"})
        if node["$not_applicable"] is not True:
            raise DOIPersistenceIntegrityError("DOI_PAYLOAD_NOT_APPLICABLE_INVALID")
        from synthetic_sales_assist.doi.models import not_applicable_fact

        return not_applicable_fact()
    if "$dataclass" in node:
        _require_exact_members(node, {"$dataclass", "fields"})
        cls = _CLOSED_TYPES.get(cast(str, node["$dataclass"]))
        if cls is None or not dataclasses.is_dataclass(cls) or type(node["fields"]) is not dict:
            raise DOIPersistenceIntegrityError("DOI_PAYLOAD_DATACLASS_INVALID")
        raw_fields = cast(dict[str, object], node["fields"])
        declared = dataclasses.fields(cls)
        params = getattr(cls, "__dataclass_params__")
        expected = {field.name for field in declared if not params.init or field.init}
        if set(raw_fields) != expected:
            raise DOIPersistenceIntegrityError("DOI_PAYLOAD_DATACLASS_FIELDS_INVALID")
        fields = {name: _unpack(item) for name, item in raw_fields.items()}
        try:
            if params.init:
                return cls(**fields)
            instance = object.__new__(cls)
            for name, field_value in fields.items():
                object.__setattr__(instance, name, field_value)
            post_init = getattr(instance, "__post_init__", None)
            if callable(post_init):
                post_init()
            return instance
        except DOIPersistenceIntegrityError:
            raise
        except Exception as exc:
            raise DOIPersistenceIntegrityError("DOI_PAYLOAD_DATACLASS_REJECTED") from exc
    raise DOIPersistenceIntegrityError("DOI_PAYLOAD_TAG_INVALID")


def encode_payload(record: object) -> bytes:
    """Encode one record with a closed type inventory and deterministic JSON bytes."""

    try:
        payload = json.dumps(
            _pack(record),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except DOIPersistenceError:
        raise
    except Exception as exc:
        raise DOIPersistenceIntegrityError("DOI_PAYLOAD_ENCODING_FAILED") from exc
    if len(payload) > _MAX_PAYLOAD_BYTES:
        raise DOIPersistenceIntegrityError("DOI_PAYLOAD_TOO_LARGE")
    return payload


_RecordT = TypeVar("_RecordT")


def decode_payload(payload: object, expected_type: type[_RecordT]) -> _RecordT:
    """Decode a closed envelope and require its exact expected domain type."""

    if type(payload) is not bytes or len(cast(bytes, payload)) > _MAX_PAYLOAD_BYTES:
        raise DOIPersistenceIntegrityError("DOI_PAYLOAD_STORAGE_INVALID")
    try:
        decoded_json = json.loads(cast(bytes, payload).decode("utf-8", errors="strict"))
    except Exception as exc:
        raise DOIPersistenceIntegrityError("DOI_PAYLOAD_JSON_INVALID") from exc
    value = _unpack(decoded_json)
    if type(value) is not expected_type:
        raise DOIPersistenceIntegrityError("DOI_PAYLOAD_RESULT_TYPE_INVALID")
    return cast(_RecordT, value)


def _encoded(record: object) -> _EncodedRecord:
    binding_method = getattr(record, "hash_binding", None)
    if not callable(binding_method):
        raise DOIPersistenceIntegrityError("DOI_RECORD_HASH_BINDING_REQUIRED")
    binding = binding_method()
    if type(binding) is not HashBinding:
        raise DOIPersistenceIntegrityError("DOI_RECORD_HASH_BINDING_INVALID")
    return _EncodedRecord(encode_payload(record), binding)


def _text_id(value: object) -> str:
    json_method = getattr(value, "to_json_value", None)
    if callable(json_method):
        result = json_method()
        if type(result) is str:
            return result
    raw = getattr(value, "value", None)
    if type(raw) is str:
        return raw
    nested = getattr(raw, "value", None)
    if type(nested) is str:
        return nested
    raise DOIPersistenceIntegrityError("DOI_IDENTITY_STORAGE_INVALID")


def _stored_bytes(value: object) -> bytes:
    if isinstance(value, memoryview):
        return bytes(value)
    if type(value) is bytes:
        return cast(bytes, value)
    raise DOIPersistenceIntegrityError("DOI_BLOB_STORAGE_INVALID")


def _verify_binding(row: sqlite3.Row | tuple[object, ...], offset: int, record: object) -> None:
    binding = getattr(record, "hash_binding")()
    domain = str(row[offset])
    digest = str(row[offset + 1])
    canonical = _stored_bytes(row[offset + 2])
    if (
        type(binding) is not HashBinding
        or binding.domain != domain
        or binding.sha256 != digest
        or binding.canonical_bytes != canonical
    ):
        raise DOIPersistenceIntegrityError("DOI_RETAINED_HASH_MISMATCH")


class DOIRepository:
    """Connection-oriented DOI repository; callers supply one active SQLite UoW."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        if not isinstance(connection, sqlite3.Connection) or not connection.in_transaction:
            raise DOIPersistenceError("DOI_ACTIVE_TRANSACTION_REQUIRED")
        self.connection = connection

    def persist_run(
        self,
        run: DOIRun,
        event: DOIRunEvent,
        *,
        fault_injector: FaultInjector | None = None,
    ) -> PersistenceResult:
        if type(run) is not DOIRun or type(event) is not DOIRunEvent or event.run_id != run.run_id:
            raise DOIPersistenceError("DOI_RUN_RECORD_INVALID")
        injector = FaultInjector() if fault_injector is None else fault_injector
        run_material = _encoded(run)
        event_material = _encoded(event)
        run_id = run.run_id.value
        current = self.connection.execute(
            "SELECT record_domain, record_sha256, record_canonical_bytes, "
            "record_payload, projection_version, material_version, "
            "material_event_sha256, status, head_sha256, source_batch_id, "
            "completed_at, purge_eligible_at, source_attempt_count, work_item_count, "
            "disposition_subject_count, successful_evaluation_count, "
            "order_exception_count, blocked_order_count, portal_read_count "
            "FROM doi_run_projections WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        event_row = self.connection.execute(
            "SELECT record_domain, record_sha256, record_canonical_bytes, record_payload "
            "FROM doi_run_events WHERE run_id = ? AND sequence_no = ?",
            (run_id, event.sequence.value),
        ).fetchone()
        if event_row is not None:
            retained_event = decode_payload(_stored_bytes(event_row[3]), DOIRunEvent)
            _verify_binding(event_row, 0, retained_event)
            if (
                event_material.binding != retained_event.hash_binding()
                or event_material.payload != _stored_bytes(event_row[3])
            ):
                raise DOIPersistenceConflict("DOI_RUN_EVENT_CONFLICT")
            if current is None:
                raise DOIPersistenceIntegrityError("DOI_RUN_PROJECTION_MISSING")
            retained = decode_payload(_stored_bytes(current[3]), DOIRun)
            _verify_binding(current, 0, retained)
            material_head = self.connection.execute(
                "SELECT material_version, cause_sha256, record_sha256 "
                "FROM doi_run_material_events WHERE run_id=? "
                "ORDER BY material_version DESC LIMIT 1",
                (run_id,),
            ).fetchone()
            if (
                retained.hash_binding() != run_material.binding
                or _stored_bytes(current[3]) != run_material.payload
                or int(current[4]) != event.sequence.value
                or str(current[8]) != event_material.binding.sha256
                or str(current[7]) != run.status.value
                or current[9]
                != (
                    None
                    if run.source_batch_id is None
                    else run.source_batch_id.to_json_value()
                )
                or current[10]
                != (None if run.completed_at is None else run.completed_at.value)
                or current[11]
                != (
                    None
                    if run.purge_eligible_at is None
                    else run.purge_eligible_at.value
                )
                or tuple(int(current[index]) for index in range(12, 19))
                != (
                    run.counts.source_attempt_count.value,
                    run.counts.work_item_count.value,
                    run.counts.disposition_subject_count.value,
                    run.counts.successful_evaluation_count.value,
                    run.counts.order_exception_count.value,
                    run.counts.blocked_order_count.value,
                    run.counts.portal_read_count.value,
                )
                or material_head is None
                or tuple(material_head)
                != (int(current[5]), str(current[6]), str(current[1]))
            ):
                raise DOIPersistenceConflict("DOI_RUN_PROJECTION_CONFLICT")
            return PersistenceResult(True)

        if current is None:
            if event.sequence.value != 1 or event.status is not RunStatus.IN_PROGRESS:
                raise DOIPersistenceConflict("DOI_RUN_START_SEQUENCE_CONFLICT")
            self.connection.execute(
                "INSERT INTO doi_runs"
                "(run_id, invocation_id, run_type, recheck_order_id, started_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    run_id,
                    _text_id(run.invocation_id),
                    run.run_type.value,
                    None if run.recheck_order_id is None else run.recheck_order_id.value,
                    run.started_at.value,
                ),
            )
            injector.hit(FaultPoint.AFTER_FIRST_INSERT)
            prior_version = 0
            predecessor = None
        else:
            retained = decode_payload(_stored_bytes(current[3]), DOIRun)
            _verify_binding(current, 0, retained)
            prior_version = int(current[4])
            retained_material_event = self.connection.execute(
                "SELECT 1 FROM doi_run_events WHERE run_id=? AND record_sha256=? "
                "UNION ALL SELECT 1 FROM doi_source_import_attempt_events e "
                "JOIN doi_source_import_attempts a ON a.attempt_id=e.attempt_id "
                "WHERE a.run_id=? AND e.record_sha256=? LIMIT 1",
                (run_id, str(current[6]), run_id, str(current[6])),
            ).fetchone()
            if int(current[5]) < prior_version or retained_material_event is None:
                raise DOIPersistenceIntegrityError(
                    "DOI_RUN_PROJECTION_PRIOR_STATE_MISMATCH"
                )
            if event.sequence.value != prior_version + 1:
                raise DOIPersistenceConflict("DOI_RUN_EXPECTED_VERSION_CONFLICT")
            predecessor_row = self.connection.execute(
                "SELECT record_sha256 FROM doi_run_events WHERE run_id = ? AND sequence_no = ?",
                (run_id, prior_version),
            ).fetchone()
            if predecessor_row is None:
                raise DOIPersistenceIntegrityError("DOI_RUN_EVENT_HISTORY_GAP")
            predecessor = str(predecessor_row[0])
        injector.hit(FaultPoint.BEFORE_EVENT_APPEND)
        self.connection.execute(
            "INSERT INTO doi_run_events"
            "(run_id, sequence_no, event_kind, occurred_at, predecessor_sha256, "
            "record_domain, record_sha256, record_canonical_bytes, record_payload) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                event.sequence.value,
                event.event_kind.value,
                event.occurred_at.value,
                predecessor,
                event_material.binding.domain,
                event_material.binding.sha256,
                event_material.binding.canonical_bytes,
                event_material.payload,
            ),
        )
        injector.hit(FaultPoint.AFTER_EVENT_BEFORE_PROJECTION)
        projection_values = (
            run.status.value,
            event.sequence.value,
            event_material.binding.sha256,
            1 if current is None else int(current[5]) + 1,
            event_material.binding.sha256,
            None if run.source_batch_id is None else _text_id(run.source_batch_id),
            None if run.completed_at is None else run.completed_at.value,
            None if run.purge_eligible_at is None else run.purge_eligible_at.value,
            run.counts.source_attempt_count.value,
            run.counts.work_item_count.value,
            run.counts.disposition_subject_count.value,
            run.counts.successful_evaluation_count.value,
            run.counts.order_exception_count.value,
            run.counts.blocked_order_count.value,
            run.counts.portal_read_count.value,
            run_material.binding.domain,
            run_material.binding.sha256,
            run_material.binding.canonical_bytes,
            run_material.payload,
        )
        if current is None:
            self.connection.execute(
                "INSERT INTO doi_run_projections"
                "(run_id, status, projection_version, head_sha256, material_version, "
                "material_event_sha256, source_batch_id, "
                "completed_at, purge_eligible_at, source_attempt_count, work_item_count, "
                "disposition_subject_count, successful_evaluation_count, "
                "order_exception_count, blocked_order_count, portal_read_count, "
                "record_domain, record_sha256, record_canonical_bytes, record_payload) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, *projection_values),
            )
        else:
            cursor = self.connection.execute(
                "UPDATE doi_run_projections SET status=?, projection_version=?, "
                "head_sha256=?, material_version=?, material_event_sha256=?, "
                "source_batch_id=?, completed_at=?, purge_eligible_at=?, "
                "source_attempt_count=?, work_item_count=?, disposition_subject_count=?, "
                "successful_evaluation_count=?, order_exception_count=?, "
                "blocked_order_count=?, portal_read_count=?, record_domain=?, "
                "record_sha256=?, record_canonical_bytes=?, record_payload=? "
                "WHERE run_id=? AND projection_version=? AND material_version=? "
                "AND material_event_sha256=? AND record_sha256=?",
                (
                    *projection_values,
                    run_id,
                    prior_version,
                    int(current[5]),
                    str(current[6]),
                    str(current[1]),
                ),
            )
            if cursor.rowcount != 1:
                raise DOIPersistenceConflict("DOI_RUN_PROJECTION_RACE")
        self.connection.execute(
            "INSERT INTO doi_run_material_events"
            "(run_id, material_version, cause_sha256, record_sha256) "
            "VALUES (?, ?, ?, ?)",
            (
                run_id,
                projection_values[3],
                event_material.binding.sha256,
                run_material.binding.sha256,
            ),
        )
        readback = self.connection.execute(
            "SELECT projection_version, material_version, material_event_sha256, "
            "record_sha256 FROM doi_run_projections WHERE run_id=?",
            (run_id,),
        ).fetchone()
        if readback is None or tuple(readback) != (
            event.sequence.value,
            projection_values[3],
            event_material.binding.sha256,
            run_material.binding.sha256,
        ):
            raise DOIPersistenceIntegrityError("DOI_RUN_PROJECTION_READBACK_MISMATCH")
        injector.hit(FaultPoint.AFTER_PROJECTION_BEFORE_RECEIPT)
        if run.status is not RunStatus.IN_PROGRESS:
            self.connection.execute(
                "UPDATE doi_rejected_source_records SET "
                "retention_state='RETAINED_UNTIL', purge_eligible_at=? "
                "WHERE run_id=? AND retention_state='PENDING_RUN_TERMINAL'",
                (run.purge_eligible_at.value, run_id),
            )
        return PersistenceResult(False)

    def get_run(self, run_id: str) -> DOIRun | None:
        row = self.connection.execute(
            "SELECT record_domain, record_sha256, record_canonical_bytes, record_payload "
            "FROM doi_run_projections WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        run = decode_payload(_stored_bytes(row[3]), DOIRun)
        _verify_binding(row, 0, run)
        return run

    def run_history(self, run_id: str) -> tuple[DOIRunEvent, ...]:
        rows = self.connection.execute(
            "SELECT record_domain, record_sha256, record_canonical_bytes, record_payload "
            "FROM doi_run_events WHERE run_id = ? ORDER BY sequence_no",
            (run_id,),
        ).fetchall()
        result: list[DOIRunEvent] = []
        for row in rows:
            event = decode_payload(_stored_bytes(row[3]), DOIRunEvent)
            _verify_binding(row, 0, event)
            result.append(event)
        return tuple(result)

    def persist_source_attempt(
        self,
        attempt: DOISourceImportAttempt,
        event: DOISourceImportAttemptEvent,
    ) -> PersistenceResult:
        """Append one source-attempt event and update its current projection exactly once."""

        if (
            type(attempt) is not DOISourceImportAttempt
            or type(event) is not DOISourceImportAttemptEvent
            or event.attempt_id != attempt.attempt_id
        ):
            raise DOIPersistenceError("DOI_SOURCE_ATTEMPT_INVALID")
        run_id = attempt.run_id.value
        attempt_id = _text_id(attempt.attempt_id)
        if self.connection.execute(
            "SELECT 1 FROM doi_runs WHERE run_id=?", (run_id,)
        ).fetchone() is None:
            raise DOIPersistenceError("DOI_SOURCE_ATTEMPT_RUN_MISSING")
        material = _encoded(attempt)
        event_material = _encoded(event)
        retained_event = self.connection.execute(
            "SELECT event_kind, occurred_at, predecessor_sha256, record_domain, "
            "record_sha256, record_canonical_bytes, record_payload "
            "FROM doi_source_import_attempt_events "
            "WHERE attempt_id=? AND sequence_no=?",
            (attempt_id, event.sequence.value),
        ).fetchone()
        if retained_event is not None:
            decoded = decode_payload(
                _stored_bytes(retained_event[6]),
                DOISourceImportAttemptEvent,
            )
            _verify_binding(retained_event, 3, decoded)
            retained_attempt = self.connection.execute(
                "SELECT run_id, ordinal, source_identity_id, state, started_at, "
                "completed_at, source_batch_id, portal_read_count, projection_version, "
                "head_sha256, record_domain, record_sha256, record_canonical_bytes, "
                "record_payload "
                "FROM doi_source_import_attempts WHERE attempt_id=?",
                (attempt_id,),
            ).fetchone()
            if retained_attempt is None:
                raise DOIPersistenceIntegrityError("DOI_SOURCE_ATTEMPT_MISSING")
            current_attempt = decode_payload(
                _stored_bytes(retained_attempt[13]),
                DOISourceImportAttempt,
            )
            _verify_binding(retained_attempt, 10, current_attempt)
            latest = self.connection.execute(
                "SELECT sequence_no, record_sha256 "
                "FROM doi_source_import_attempt_events WHERE attempt_id=? "
                "ORDER BY sequence_no DESC LIMIT 1",
                (attempt_id,),
            ).fetchone()
            if latest is None:
                raise DOIPersistenceIntegrityError(
                    "DOI_SOURCE_ATTEMPT_EVENT_HISTORY_GAP"
                )
            latest_sequence = int(latest[0])
            normalized_attempt = (
                current_attempt.run_id.value,
                current_attempt.ordinal.value,
                _text_id(current_attempt.source_identity_id),
                current_attempt.state.value,
                current_attempt.started_at.value,
                None
                if current_attempt.completed_at is None
                else current_attempt.completed_at.value,
                None
                if current_attempt.source_batch_id is None
                else current_attempt.source_batch_id.to_json_value(),
                current_attempt.portal_read_count.value,
            )
            projection_changed = (
                event.sequence.value == latest_sequence
                and (
                    current_attempt.hash_binding() != material.binding
                    or _stored_bytes(retained_attempt[13]) != material.payload
                    or int(retained_attempt[8]) != latest_sequence
                    or str(retained_attempt[9])
                    != event_material.binding.sha256
                )
            )
            if (
                decoded.hash_binding() != event_material.binding
                or tuple(retained_attempt[:8]) != normalized_attempt
                or int(retained_attempt[8]) != latest_sequence
                or str(retained_attempt[9]) != str(latest[1])
                or str(retained_event[0]) != event.event_kind.value
                or str(retained_event[1]) != event.occurred_at.value
                or projection_changed
            ):
                raise DOIPersistenceConflict("DOI_SOURCE_ATTEMPT_EVENT_CONFLICT")
            return PersistenceResult(True)
        current = self.connection.execute(
            "SELECT ordinal, state, projection_version, head_sha256, record_sha256 "
            "FROM doi_source_import_attempts WHERE attempt_id=?",
            (attempt_id,),
        ).fetchone()
        ordinal_owner = self.connection.execute(
            "SELECT attempt_id FROM doi_source_import_attempts "
            "WHERE run_id=? AND ordinal=?",
            (run_id, attempt.ordinal.value),
        ).fetchone()
        if ordinal_owner is not None and str(ordinal_owner[0]) != attempt_id:
            raise DOIPersistenceConflict("DOI_SOURCE_ATTEMPT_ORDINAL_CONFLICT")
        predecessor_row = self.connection.execute(
            "SELECT record_sha256 FROM doi_source_import_attempt_events "
            "WHERE attempt_id=? ORDER BY sequence_no DESC LIMIT 1",
            (attempt_id,),
        ).fetchone()
        predecessor = None if predecessor_row is None else str(predecessor_row[0])
        values = (
            run_id,
            attempt.ordinal.value,
            _text_id(attempt.source_identity_id),
            attempt.state.value,
            attempt.started_at.value,
            None if attempt.completed_at is None else attempt.completed_at.value,
            None
            if attempt.source_batch_id is None
            else _text_id(attempt.source_batch_id),
            attempt.portal_read_count.value,
            material.binding.domain,
            material.binding.sha256,
            material.binding.canonical_bytes,
            material.payload,
            event.sequence.value,
            event_material.binding.sha256,
        )
        if current is None:
            if event.sequence.value != 1 or predecessor is not None:
                raise DOIPersistenceConflict("DOI_SOURCE_ATTEMPT_SEQUENCE_CONFLICT")
            self.connection.execute(
                "INSERT INTO doi_source_import_attempts"
                "(attempt_id, run_id, ordinal, source_identity_id, state, started_at, "
                "completed_at, source_batch_id, portal_read_count, record_domain, "
                "record_sha256, record_canonical_bytes, record_payload, "
                "projection_version, head_sha256) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (attempt_id, *values),
            )
        elif int(current[0]) != attempt.ordinal.value:
            raise DOIPersistenceConflict("DOI_SOURCE_ATTEMPT_ORDINAL_CONFLICT")
        else:
            if (
                event.sequence.value != int(current[2]) + 1
                or predecessor != str(current[3])
            ):
                raise DOIPersistenceConflict("DOI_SOURCE_ATTEMPT_SEQUENCE_CONFLICT")
            cursor = self.connection.execute(
                "UPDATE doi_source_import_attempts SET state=?, completed_at=?, "
                "source_batch_id=?, portal_read_count=?, record_domain=?, record_sha256=?, "
                "record_canonical_bytes=?, record_payload=?, projection_version=?, "
                "head_sha256=? WHERE attempt_id=? AND state=? AND "
                "projection_version=? AND head_sha256=? AND record_sha256=?",
                (
                    attempt.state.value,
                    None if attempt.completed_at is None else attempt.completed_at.value,
                    None
                    if attempt.source_batch_id is None
                    else _text_id(attempt.source_batch_id),
                    attempt.portal_read_count.value,
                    material.binding.domain,
                    material.binding.sha256,
                    material.binding.canonical_bytes,
                    material.payload,
                    event.sequence.value,
                    event_material.binding.sha256,
                    attempt_id,
                    str(current[1]),
                    int(current[2]),
                    str(current[3]),
                    str(current[4]),
                ),
            )
            if cursor.rowcount != 1:
                raise DOIPersistenceConflict("DOI_SOURCE_ATTEMPT_PROJECTION_RACE")
        self.connection.execute(
            "INSERT INTO doi_source_import_attempt_events"
            "(attempt_id, sequence_no, event_kind, occurred_at, predecessor_sha256, "
            "record_domain, record_sha256, record_canonical_bytes, record_payload) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                attempt_id,
                event.sequence.value,
                event.event_kind.value,
                event.occurred_at.value,
                predecessor,
                event_material.binding.domain,
                event_material.binding.sha256,
                event_material.binding.canonical_bytes,
                event_material.payload,
            ),
        )
        readback = self.connection.execute(
            "SELECT state, projection_version, head_sha256, record_sha256 "
            "FROM doi_source_import_attempts WHERE attempt_id=?",
            (attempt_id,),
        ).fetchone()
        if readback is None or tuple(readback) != (
            attempt.state.value,
            event.sequence.value,
            event_material.binding.sha256,
            material.binding.sha256,
        ):
            raise DOIPersistenceIntegrityError(
                "DOI_SOURCE_ATTEMPT_READBACK_MISMATCH"
            )
        return PersistenceResult(False)

    def _persist_source_batch(self, batch: DOISourceBatch) -> PersistenceResult:
        if type(batch) is not DOISourceBatch:
            raise DOIPersistenceError("DOI_SOURCE_BATCH_INVALID")
        material = _encoded(batch)
        batch_id = batch.batch_id.to_json_value()
        retained = self.connection.execute(
            "SELECT identity_domain, identity_sha256, identity_canonical_bytes, "
            "record_domain, record_sha256, record_canonical_bytes, record_payload "
            "FROM doi_source_batches WHERE batch_id=? OR identity_sha256=?",
            (batch_id, batch.identity.sha256),
        ).fetchone()
        if retained is not None:
            exact = (
                str(retained[0]) == batch.identity.domain
                and str(retained[1]) == batch.identity.sha256
                and _stored_bytes(retained[2]) == batch.identity.canonical_bytes
                and str(retained[3]) == material.binding.domain
                and str(retained[4]) == material.binding.sha256
                and _stored_bytes(retained[5]) == material.binding.canonical_bytes
                and _stored_bytes(retained[6]) == material.payload
            )
            if not exact:
                raise DOIPersistenceConflict("DOI_SOURCE_BATCH_CONFLICT")
            return PersistenceResult(True)
        self.connection.execute(
            "INSERT INTO doi_source_batches"
            "(batch_id, source_identity_id, identity_domain, identity_sha256, "
            "identity_canonical_bytes, record_domain, record_sha256, "
            "record_canonical_bytes, record_payload, mapping_version, finite_extent, "
            "status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                batch_id,
                batch.source_identity_id.to_json_value(),
                batch.identity.domain,
                batch.identity.sha256,
                batch.identity.canonical_bytes,
                material.binding.domain,
                material.binding.sha256,
                material.binding.canonical_bytes,
                material.payload,
                batch.mapping_version,
                batch.finite_extent.value,
                batch.status.value,
            ),
        )
        return PersistenceResult(False)

    def refresh_in_progress_run(
        self,
        run: DOIRun,
        *,
        cause_event: DOISourceImportAttemptEvent,
        allow_cause_advance: bool,
    ) -> None:
        if (
            type(run) is not DOIRun
            or run.status is not RunStatus.IN_PROGRESS
            or type(cause_event) is not DOISourceImportAttemptEvent
            or type(allow_cause_advance) is not bool
            or cause_event.attempt_id.to_json_value()
            not in {
                row[0]
                for row in self.connection.execute(
                    "SELECT attempt_id FROM doi_source_import_attempts WHERE run_id=?",
                    (run.run_id.value,),
                ).fetchall()
            }
        ):
            raise DOIPersistenceError("DOI_RUN_REFRESH_INVALID")
        current = self.connection.execute(
            "SELECT status, material_version, material_event_sha256, record_sha256 "
            "FROM doi_run_projections WHERE run_id=?",
            (run.run_id.value,),
        ).fetchone()
        if current is None or str(current[0]) != RunStatus.IN_PROGRESS.value:
            raise DOIPersistenceConflict("DOI_RUN_REFRESH_STATE_CONFLICT")
        attempt_count = int(
            self.connection.execute(
                "SELECT COUNT(*) FROM doi_source_import_attempts WHERE run_id=?",
                (run.run_id.value,),
            ).fetchone()[0]
        )
        work_count = int(
            self.connection.execute(
                "SELECT COUNT(*) FROM doi_run_work_items WHERE run_id=?",
                (run.run_id.value,),
            ).fetchone()[0]
        )
        if (
            run.counts.source_attempt_count.value != attempt_count
            or run.counts.work_item_count.value != work_count
        ):
            raise DOIPersistenceConflict("DOI_RUN_REFRESH_COUNT_CONFLICT")
        material = _encoded(run)
        cause_sha256 = cause_event.hash_binding().sha256
        retained_cause = self.connection.execute(
            "SELECT 1 FROM doi_run_events WHERE run_id=? AND record_sha256=? "
            "UNION ALL SELECT 1 FROM doi_source_import_attempt_events e "
            "JOIN doi_source_import_attempts a ON a.attempt_id=e.attempt_id "
            "WHERE a.run_id=? AND e.record_sha256=? LIMIT 1",
            (
                run.run_id.value,
                str(current[2]),
                run.run_id.value,
                str(current[2]),
            ),
        ).fetchone()
        if retained_cause is None:
            raise DOIPersistenceIntegrityError("DOI_RUN_REFRESH_CAUSE_MISMATCH")
        if str(current[3]) == material.binding.sha256:
            if str(current[2]) == cause_sha256:
                return
            if not allow_cause_advance:
                raise DOIPersistenceIntegrityError(
                    "DOI_RUN_REFRESH_REPLAY_MISMATCH"
                )
            cursor = self.connection.execute(
                "UPDATE doi_run_projections SET material_version=?, "
                "material_event_sha256=? WHERE run_id=? AND status=? "
                "AND material_version=? AND material_event_sha256=? "
                "AND record_sha256=?",
                (
                    int(current[1]) + 1,
                    cause_sha256,
                    run.run_id.value,
                    RunStatus.IN_PROGRESS.value,
                    int(current[1]),
                    str(current[2]),
                    str(current[3]),
                ),
            )
            if cursor.rowcount != 1:
                raise DOIPersistenceConflict("DOI_RUN_REFRESH_RACE")
            self.connection.execute(
                "INSERT INTO doi_run_material_events"
                "(run_id, material_version, cause_sha256, record_sha256) "
                "VALUES (?, ?, ?, ?)",
                (
                    run.run_id.value,
                    int(current[1]) + 1,
                    cause_sha256,
                    material.binding.sha256,
                ),
            )
            readback = self.connection.execute(
                "SELECT material_version, material_event_sha256, record_sha256 "
                "FROM doi_run_projections WHERE run_id=?",
                (run.run_id.value,),
            ).fetchone()
            if readback is None or tuple(readback) != (
                int(current[1]) + 1,
                cause_sha256,
                material.binding.sha256,
            ):
                raise DOIPersistenceIntegrityError(
                    "DOI_RUN_REFRESH_READBACK_MISMATCH"
                )
            return
        if not allow_cause_advance:
            raise DOIPersistenceIntegrityError("DOI_RUN_REFRESH_REPLAY_MISMATCH")
        cursor = self.connection.execute(
            "UPDATE doi_run_projections SET source_batch_id=?, source_attempt_count=?, "
            "work_item_count=?, disposition_subject_count=?, "
            "successful_evaluation_count=?, order_exception_count=?, "
            "blocked_order_count=?, portal_read_count=?, record_domain=?, "
            "record_sha256=?, record_canonical_bytes=?, record_payload=?, "
            "material_version=?, material_event_sha256=? WHERE run_id=? "
            "AND status=? AND material_version=? AND material_event_sha256=? "
            "AND record_sha256=?",
            (
                None
                if run.source_batch_id is None
                else run.source_batch_id.to_json_value(),
                run.counts.source_attempt_count.value,
                run.counts.work_item_count.value,
                run.counts.disposition_subject_count.value,
                run.counts.successful_evaluation_count.value,
                run.counts.order_exception_count.value,
                run.counts.blocked_order_count.value,
                run.counts.portal_read_count.value,
                material.binding.domain,
                material.binding.sha256,
                material.binding.canonical_bytes,
                material.payload,
                int(current[1]) + 1,
                cause_sha256,
                run.run_id.value,
                RunStatus.IN_PROGRESS.value,
                int(current[1]),
                str(current[2]),
                str(current[3]),
            ),
        )
        if cursor.rowcount != 1:
            raise DOIPersistenceConflict("DOI_RUN_REFRESH_RACE")
        self.connection.execute(
            "INSERT INTO doi_run_material_events"
            "(run_id, material_version, cause_sha256, record_sha256) "
            "VALUES (?, ?, ?, ?)",
            (
                run.run_id.value,
                int(current[1]) + 1,
                cause_sha256,
                material.binding.sha256,
            ),
        )
        readback = self.connection.execute(
            "SELECT material_version, material_event_sha256, record_sha256 "
            "FROM doi_run_projections WHERE run_id=?",
            (run.run_id.value,),
        ).fetchone()
        if readback is None or tuple(readback) != (
            int(current[1]) + 1,
            cause_sha256,
            material.binding.sha256,
        ):
            raise DOIPersistenceIntegrityError("DOI_RUN_REFRESH_READBACK_MISMATCH")

    def persist_source_import(
        self,
        *,
        attempt: DOISourceImportAttempt,
        event: DOISourceImportAttemptEvent,
        result: SourceImportResult,
        run: DOIRun,
        work_items: tuple[DOIRunWorkItem, ...],
    ) -> PersistenceResult:
        """Persist one complete source-import result and its normalized owner graph."""

        if (
            type(result) is not SourceImportResult
            or type(run) is not DOIRun
            or type(work_items) is not tuple
            or any(type(item) is not DOIRunWorkItem for item in work_items)
            or attempt.run_id != run.run_id
        ):
            raise DOIPersistenceError("DOI_SOURCE_IMPORT_GRAPH_INVALID")
        succeeded = result.kind is SourceImportResultKind.SUCCEEDED
        if succeeded != (result.batch is not None):
            raise DOIPersistenceError("DOI_SOURCE_IMPORT_RESULT_INVALID")
        batch = result.batch
        if batch is not None:
            if (
                attempt.source_batch_id != batch.batch_id
                or run.source_batch_id != batch.batch_id
                or attempt.source_identity_id != batch.source_identity_id
            ):
                raise DOIPersistenceError("DOI_SOURCE_IMPORT_BATCH_BINDING_INVALID")
            self._persist_source_batch(batch)
        attempt_result = self.persist_source_attempt(attempt, event)
        if attempt_result.replayed:
            self.refresh_in_progress_run(
                run,
                cause_event=event,
                allow_cause_advance=False,
            )
            return attempt_result
        if batch is not None:
            batch_id = batch.batch_id.to_json_value()
            self.connection.execute(
                "INSERT INTO doi_attempt_batch_references(attempt_id, batch_id) "
                "VALUES (?, ?)",
                (attempt.attempt_id.to_json_value(), batch_id),
            )
            for staged in batch.staged_orders:
                material = _encoded(staged)
                self.connection.execute(
                    "INSERT INTO doi_staged_orders"
                    "(attempt_id, order_id, batch_id, record_domain, record_sha256, "
                    "record_canonical_bytes, record_payload) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        attempt.attempt_id.to_json_value(),
                        staged.order_id.value,
                        batch_id,
                        material.binding.domain,
                        material.binding.sha256,
                        material.binding.canonical_bytes,
                        material.payload,
                    ),
                )
                for ordinal, source_ref in enumerate(staged.source_ref_ids, start=1):
                    self.connection.execute(
                        "INSERT INTO doi_staged_order_source_refs"
                        "(attempt_id, order_id, source_ref_id, ordinal) "
                        "VALUES (?, ?, ?, ?)",
                        (
                            attempt.attempt_id.to_json_value(),
                            staged.order_id.value,
                            source_ref.to_json_value(),
                            ordinal,
                        ),
                    )
            for rejected in batch.rejected_records:
                material = _encoded(rejected)
                rejection_id = (
                    "SYN-EVIDENCE-DOI-M4-REJECTION-"
                    + material.binding.sha256[:24].upper()
                )
                self.connection.execute(
                    "INSERT INTO doi_rejected_source_records"
                    "(rejection_id, attempt_id, run_id, batch_id, order_id, "
                    "retention_state, purge_eligible_at, record_domain, record_sha256, "
                    "record_canonical_bytes, record_payload) "
                    "VALUES (?, ?, ?, ?, ?, 'PENDING_RUN_TERMINAL', NULL, ?, ?, ?, ?)",
                    (
                        rejection_id,
                        attempt.attempt_id.to_json_value(),
                        run.run_id.value,
                        batch_id,
                        rejected.order_id.value,
                        material.binding.domain,
                        material.binding.sha256,
                        material.binding.canonical_bytes,
                        material.payload,
                    ),
                )
        for item in work_items:
            if item.run_id != run.run_id:
                raise DOIPersistenceError("DOI_RUN_WORK_ITEM_OWNER_INVALID")
            self.persist_run_work_item(item)
        if attempt.completed_at is None:
            raise DOIPersistenceError("DOI_SOURCE_IMPORT_TERMINAL_TIME_MISSING")
        month_key = attempt.completed_at.value[:7]
        self.connection.execute(
            "INSERT INTO doi_source_import_aggregates"
            "(month_key, outcome_class, attempt_count) VALUES (?, ?, 1) "
            "ON CONFLICT(month_key, outcome_class) DO UPDATE SET "
            "attempt_count=attempt_count+1",
            (month_key, attempt.state.value),
        )
        self.refresh_in_progress_run(
            run,
            cause_event=event,
            allow_cause_advance=True,
        )
        return PersistenceResult(False)

    def persist_run_work_item(
        self,
        item: DOIRunWorkItem,
    ) -> PersistenceResult:
        if type(item) is not DOIRunWorkItem:
            raise DOIPersistenceError("DOI_RUN_WORK_ITEM_INVALID")
        material = _encoded(item)
        item_id = item.work_item_id.to_json_value()
        retained = self.connection.execute(
            "SELECT run_id, order_id, origin, source_batch_id, record_domain, "
            "record_sha256, record_canonical_bytes, record_payload "
            "FROM doi_run_work_items WHERE run_id=? AND work_item_id=?",
            (item.run_id.value, item_id),
        ).fetchone()
        expected = (
            item.run_id.value,
            item.order_id.value,
            item.origin.value,
            None
            if item.source_batch_id is None
            else item.source_batch_id.to_json_value(),
            material.binding.domain,
            material.binding.sha256,
            material.binding.canonical_bytes,
            material.payload,
        )
        if retained is not None:
            if tuple(retained) != expected:
                raise DOIPersistenceConflict("DOI_RUN_WORK_ITEM_CONFLICT")
            return PersistenceResult(True)
        if self.connection.execute(
            "SELECT 1 FROM doi_runs WHERE run_id=?",
            (item.run_id.value,),
        ).fetchone() is None:
            raise DOIPersistenceError("DOI_RUN_WORK_ITEM_RUN_MISSING")
        self.connection.execute(
            "INSERT INTO doi_run_work_items"
            "(work_item_id, run_id, order_id, origin, source_batch_id, "
            "record_domain, record_sha256, record_canonical_bytes, record_payload) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (item_id, *expected),
        )
        return PersistenceResult(False)

    def persist_run_work_disposition(
        self,
        disposition: DOIRunWorkDisposition,
    ) -> PersistenceResult:
        """Retain exactly one terminal disposition for an accepted work item."""

        if type(disposition) is not DOIRunWorkDisposition:
            raise DOIPersistenceError("DOI_RUN_WORK_DISPOSITION_INVALID")
        work_item_id = disposition.work_item_id.to_json_value()
        run_id = disposition.run_id.value
        run = self.get_run(run_id)
        if run is None or run.status is not RunStatus.IN_PROGRESS:
            raise DOIPersistenceConflict("DOI_RUN_WORK_DISPOSITION_STATE_CONFLICT")
        work_row = self.connection.execute(
            "SELECT run_id, record_domain, record_sha256, record_canonical_bytes, "
            "record_payload FROM doi_run_work_items "
            "WHERE run_id=? AND work_item_id=?",
            (run_id, work_item_id),
        ).fetchone()
        if work_row is None or str(work_row[0]) != run_id:
            raise DOIPersistenceConflict("DOI_RUN_WORK_DISPOSITION_ITEM_MISSING")
        work_item = decode_payload(_stored_bytes(work_row[4]), DOIRunWorkItem)
        _verify_binding(work_row, 1, work_item)
        if work_item.hash_binding().sha256 != disposition.work_item_sha256:
            raise DOIPersistenceConflict("DOI_RUN_WORK_DISPOSITION_ITEM_CONFLICT")
        material = _encoded(disposition)
        retained = self.connection.execute(
            "SELECT record_domain, record_sha256, record_canonical_bytes, "
            "record_payload FROM doi_run_work_dispositions "
            "WHERE run_id=? AND work_item_id=?",
            (run_id, work_item_id),
        ).fetchone()
        if retained is not None:
            current = decode_payload(
                _stored_bytes(retained[3]),
                DOIRunWorkDisposition,
            )
            _verify_binding(retained, 0, current)
            if (
                current.hash_binding() != material.binding
                or _stored_bytes(retained[3]) != material.payload
            ):
                raise DOIPersistenceConflict("DOI_RUN_WORK_DISPOSITION_CONFLICT")
            return PersistenceResult(True)
        self.connection.execute(
            "INSERT INTO doi_run_work_dispositions"
            "(work_item_id, run_id, disposition_kind, occurred_at, record_domain, "
            "record_sha256, record_canonical_bytes, record_payload) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                work_item_id,
                run_id,
                disposition.kind.value,
                disposition.occurred_at.value,
                material.binding.domain,
                material.binding.sha256,
                material.binding.canonical_bytes,
                material.payload,
            ),
        )
        return PersistenceResult(False)

    def finalize_run_processing(
        self,
        run: DOIRun,
        event: DOIRunEvent,
        *,
        fault_injector: FaultInjector | None = None,
    ) -> PersistenceResult:
        """Terminalize a run only when normalized work/disposition counts conserve."""

        if (
            type(run) is not DOIRun
            or type(event) is not DOIRunEvent
            or event.run_id != run.run_id
            or run.status is RunStatus.IN_PROGRESS
        ):
            raise DOIPersistenceError("DOI_RUN_FINALIZATION_INVALID")
        run_id = run.run_id.value
        attempt_count = int(
            self.connection.execute(
                "SELECT COUNT(*) FROM doi_source_import_attempts WHERE run_id=?",
                (run_id,),
            ).fetchone()[0]
        )
        work_count = int(
            self.connection.execute(
                "SELECT COUNT(*) FROM doi_run_work_items WHERE run_id=?",
                (run_id,),
            ).fetchone()[0]
        )
        rows = self.connection.execute(
            "SELECT record_domain, record_sha256, record_canonical_bytes, "
            "record_payload FROM doi_run_work_dispositions WHERE run_id=? "
            "ORDER BY work_item_id",
            (run_id,),
        ).fetchall()
        dispositions: list[DOIRunWorkDisposition] = []
        for row in rows:
            disposition = decode_payload(
                _stored_bytes(row[3]),
                DOIRunWorkDisposition,
            )
            _verify_binding(row, 0, disposition)
            dispositions.append(disposition)
        kinds = [item.kind.value for item in dispositions]
        expected = (
            attempt_count,
            work_count,
            len(dispositions),
            kinds.count("SUCCESSFUL_EVALUATION"),
            kinds.count("ORDER_EXCEPTION"),
            kinds.count("BLOCKED_ORDER"),
            sum(item.portal_read_performed for item in dispositions),
        )
        actual = (
            run.counts.source_attempt_count.value,
            run.counts.work_item_count.value,
            run.counts.disposition_subject_count.value,
            run.counts.successful_evaluation_count.value,
            run.counts.order_exception_count.value,
            run.counts.blocked_order_count.value,
            run.counts.portal_read_count.value,
        )
        if expected != actual or len(dispositions) != work_count:
            raise DOIPersistenceConflict("DOI_RUN_FINALIZATION_COUNT_CONFLICT")
        return self.persist_run(run, event, fault_injector=fault_injector)

    def persist_run_control_receipt(
        self,
        *,
        receipt_id: str,
        run_id: str,
        occurrence_key: str,
        operation: str,
        material: HashBinding,
        result: object,
        committed_at: CanonicalTimestamp,
    ) -> PersistenceResult:
        """Retain one retry/finalization winner at its closed race boundary."""

        operations = {
            "RETRY",
            "NO_RETRY_FINALIZATION",
            "EXTRACTION_RESERVED",
            "PRE_EXTRACTION_RULES_UNAVAILABLE",
        }
        if (
            type(receipt_id) is not str
            or not receipt_id
            or type(run_id) is not str
            or not run_id
            or type(occurrence_key) is not str
            or not occurrence_key
            or operation not in operations
            or type(material) is not HashBinding
            or type(committed_at) is not CanonicalTimestamp
        ):
            raise DOIPersistenceError("DOI_RUN_CONTROL_RECEIPT_INVALID")
        result_material = _encoded(result)
        result_payload = result_material.payload
        retained = self.connection.execute(
            "SELECT receipt_id, run_id, occurrence_key, operation, "
            "material_domain, material_sha256, material_canonical_bytes, "
            "result_payload, committed_at FROM doi_run_control_receipts "
            "WHERE receipt_id=? OR (run_id=? AND occurrence_key=?)",
            (receipt_id, run_id, occurrence_key),
        ).fetchone()
        if retained is not None:
            exact = (
                str(retained[0]) == receipt_id
                and str(retained[1]) == run_id
                and str(retained[2]) == occurrence_key
                and str(retained[3]) == operation
                and str(retained[4]) == material.domain
                and str(retained[5]) == material.sha256
                and _stored_bytes(retained[6]) == material.canonical_bytes
                and _stored_bytes(retained[7]) == result_payload
                and str(retained[8]) == committed_at.value
            )
            if not exact:
                raise DOIPersistenceConflict("DOI_RUN_CONTROL_OCCURRENCE_CONFLICT")
            return PersistenceResult(True)

        projection = self.connection.execute(
            "SELECT status FROM doi_run_projections WHERE run_id=?",
            (run_id,),
        ).fetchone()
        if projection is None:
            raise DOIPersistenceError("DOI_RUN_CONTROL_RUN_MISSING")
        status = str(projection[0])
        if operation == "EXTRACTION_RESERVED" and status != RunStatus.IN_PROGRESS.value:
            raise DOIPersistenceConflict("DOI_EXTRACTION_RESERVATION_RUN_STATE")
        if operation == "PRE_EXTRACTION_RULES_UNAVAILABLE":
            if status != RunStatus.FAILED.value:
                raise DOIPersistenceConflict("DOI_PRE_EXTRACTION_RUN_STATE")
        if operation in {"RETRY", "NO_RETRY_FINALIZATION"}:
            predecessor = self.connection.execute(
                "SELECT ordinal, state FROM doi_source_import_attempts "
                "WHERE attempt_id=? AND run_id=?",
                (occurrence_key, run_id),
            ).fetchone()
            if predecessor is None or str(predecessor[1]) not in {"FAILED", "ABORTED"}:
                raise DOIPersistenceConflict("DOI_RETRY_PREDECESSOR_STATE")
            maximum = int(
                self.connection.execute(
                    "SELECT MAX(ordinal) FROM doi_source_import_attempts WHERE run_id=?",
                    (run_id,),
                ).fetchone()[0]
            )
            predecessor_ordinal = int(predecessor[0])
            expected_maximum = (
                predecessor_ordinal + 1 if operation == "RETRY" else predecessor_ordinal
            )
            if maximum != expected_maximum:
                raise DOIPersistenceConflict("DOI_RETRY_GREATEST_ATTEMPT_CONFLICT")
        self.connection.execute(
            "INSERT INTO doi_run_control_receipts"
            "(receipt_id, run_id, occurrence_key, operation, material_domain, "
            "material_sha256, material_canonical_bytes, result_payload, committed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                receipt_id,
                run_id,
                occurrence_key,
                operation,
                material.domain,
                material.sha256,
                material.canonical_bytes,
                result_payload,
                committed_at.value,
            ),
        )
        return PersistenceResult(False)

    def append_relationship_revision(
        self,
        relationship: DOIAlternateRelationship,
    ) -> PersistenceResult:
        """Append the current immutable product revision and advance its projection."""

        if type(relationship) is not DOIAlternateRelationship:
            raise DOIPersistenceError("DOI_RELATIONSHIP_INVALID")
        revision = relationship.current_revision
        material = _encoded(revision)
        relationship_id = relationship.relationship_id.value
        projection = self.connection.execute(
            "SELECT relationship_type, ordered_sku, candidate_sku, current_revision, "
            "current_state, head_sha256 FROM doi_product_relationships "
            "WHERE relationship_id=?",
            (relationship_id,),
        ).fetchone()
        retained = self.connection.execute(
            "SELECT record_domain, record_sha256, record_canonical_bytes, record_payload "
            "FROM doi_product_relationship_revisions WHERE revision_id=?",
            (revision.revision_id.value,),
        ).fetchone()
        if retained is not None:
            decoded = decode_payload(
                _stored_bytes(retained[3]),
                DOIAlternateRelationshipRevision,
            )
            _verify_binding(retained, 0, decoded)
            if (
                decoded.hash_binding() != material.binding
                or projection is None
                or tuple(projection)
                != (
                    relationship.relationship_type.value,
                    relationship.ordered_sku.value,
                    relationship.candidate_sku.value,
                    revision.revision_number.value,
                    revision.state.value,
                    material.binding.sha256,
                )
            ):
                raise DOIPersistenceConflict("DOI_RELATIONSHIP_REVISION_CONFLICT")
            return PersistenceResult(True)
        expected_prior = revision.revision_number.value - 1
        if projection is None:
            if expected_prior != 0:
                raise DOIPersistenceConflict("DOI_RELATIONSHIP_REVISION_GAP")
            self.connection.execute(
                "INSERT INTO doi_product_relationships"
                "(relationship_id, relationship_type, ordered_sku, candidate_sku, "
                "current_revision, current_state, head_sha256) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    relationship_id,
                    relationship.relationship_type.value,
                    relationship.ordered_sku.value,
                    relationship.candidate_sku.value,
                    revision.revision_number.value,
                    revision.state.value,
                    material.binding.sha256,
                ),
            )
        else:
            if (
                str(projection[0]) != relationship.relationship_type.value
                or str(projection[1]) != relationship.ordered_sku.value
                or str(projection[2]) != relationship.candidate_sku.value
                or int(projection[3]) != expected_prior
                or str(projection[5])
                != revision.predecessor_binding.sha256
            ):
                raise DOIPersistenceConflict("DOI_RELATIONSHIP_PROJECTION_CONFLICT")
        self.connection.execute(
            "INSERT INTO doi_product_relationship_revisions"
            "(relationship_id, revision_no, revision_id, predecessor_sha256, "
            "record_domain, record_sha256, record_canonical_bytes, record_payload) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                relationship_id,
                revision.revision_number.value,
                revision.revision_id.value,
                None
                if revision.predecessor_binding is None
                else revision.predecessor_binding.sha256,
                material.binding.domain,
                material.binding.sha256,
                material.binding.canonical_bytes,
                material.payload,
            ),
        )
        if projection is not None:
            cursor = self.connection.execute(
                "UPDATE doi_product_relationships SET current_revision=?, "
                "current_state=?, head_sha256=? WHERE relationship_id=? "
                "AND current_revision=? AND current_state=? AND head_sha256=?",
                (
                    revision.revision_number.value,
                    revision.state.value,
                    material.binding.sha256,
                    relationship_id,
                    expected_prior,
                    str(projection[4]),
                    str(projection[5]),
                ),
            )
            if cursor.rowcount != 1:
                raise DOIPersistenceConflict("DOI_RELATIONSHIP_RACE")
        readback = self.connection.execute(
            "SELECT current_revision, current_state, head_sha256 "
            "FROM doi_product_relationships "
            "WHERE relationship_id=?",
            (relationship_id,),
        ).fetchone()
        if readback is None or tuple(readback) != (
            revision.revision_number.value,
            revision.state.value,
            material.binding.sha256,
        ):
            raise DOIPersistenceIntegrityError(
                "DOI_RELATIONSHIP_PROJECTION_READBACK_MISMATCH"
            )
        return PersistenceResult(False)

    def append_product_observation(
        self,
        observation: DOIAlternateObservation | DOIExactSKUObservation,
        *,
        relationship_id: EvidenceId | None = None,
        case_id: EvidenceId | None = None,
    ) -> PersistenceResult:
        if type(observation) not in {DOIAlternateObservation, DOIExactSKUObservation}:
            raise DOIPersistenceError("DOI_PRODUCT_OBSERVATION_INVALID")
        material = _encoded(observation)
        observation_id = observation.observation_id.value
        retained = self.connection.execute(
            "SELECT relationship_id, case_id, action_context_id, observed_at, "
            "record_domain, record_sha256, record_canonical_bytes, record_payload "
            "FROM doi_product_observations WHERE observation_id=?",
            (observation_id,),
        ).fetchone()
        if retained is not None:
            if (
                retained[0]
                != (None if relationship_id is None else relationship_id.value)
                or retained[1] != (None if case_id is None else case_id.value)
                or str(retained[2]) != observation.action_context_id.value
                or str(retained[3]) != observation.observed_at.value
                or str(retained[4]) != material.binding.domain
                or str(retained[5]) != material.binding.sha256
                or _stored_bytes(retained[6]) != material.binding.canonical_bytes
                or _stored_bytes(retained[7]) != material.payload
            ):
                raise DOIPersistenceConflict("DOI_PRODUCT_OBSERVATION_CONFLICT")
            return PersistenceResult(True)
        self.connection.execute(
            "INSERT INTO doi_product_observations"
            "(observation_id, relationship_id, case_id, action_context_id, observed_at, "
            "record_domain, record_sha256, record_canonical_bytes, record_payload) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                observation_id,
                None if relationship_id is None else relationship_id.value,
                None if case_id is None else case_id.value,
                observation.action_context_id.value,
                observation.observed_at.value,
                material.binding.domain,
                material.binding.sha256,
                material.binding.canonical_bytes,
                material.payload,
            ),
        )
        return PersistenceResult(False)

    def persist_intervention(
        self,
        *,
        case_id: EvidenceId,
        intervention: DOIIntervention,
        created_at: CanonicalTimestamp,
    ) -> PersistenceResult:
        """Persist verified action/value histories before exposing an intervention."""

        if (
            type(case_id) is not EvidenceId
            or type(intervention) is not DOIIntervention
            or type(created_at) is not CanonicalTimestamp
        ):
            raise DOIPersistenceError("DOI_INTERVENTION_INVALID")
        case_key = case_id.value
        opportunity = self.connection.execute(
            "SELECT case_id FROM doi_opportunities WHERE opportunity_id=?",
            (intervention.opportunity_id.value,),
        ).fetchone()
        if opportunity is None or str(opportunity[0]) != case_key:
            raise DOIPersistenceError("DOI_INTERVENTION_OPPORTUNITY_MISSING")
        material = _encoded(intervention)
        projection_events = (
            *intervention.action_events,
            *intervention.value_events,
        )
        projection_version = max(1, len(projection_events))
        projection_head = (
            material.binding.sha256
            if not projection_events
            else projection_events[-1].hash_binding().sha256
        )
        artifact_pk, artifact_replayed = self._artifact(
            case_key,
            "INTERVENTION",
            f"{intervention.intervention_id.value}:{material.binding.sha256[:24]}",
            intervention,
            created_at,
        )
        retained = self.connection.execute(
            "SELECT opportunity_id, intervention_type, status, record_artifact_pk, "
            "projection_version, head_sha256, case_id, action_occurred_at "
            "FROM doi_interventions WHERE intervention_id=?",
            (intervention.intervention_id.value,),
        ).fetchone()
        if retained is not None and (
            str(retained[0]) != intervention.opportunity_id.value
            or str(retained[1]) != intervention.intervention_type.value
            or str(retained[6]) != case_key
            or retained[7]
            != (
                None
                if intervention.action_occurred_at is None
                else intervention.action_occurred_at.value
            )
        ):
            raise DOIPersistenceConflict("DOI_INTERVENTION_NATURAL_KEY_CONFLICT")
        natural_owner = self.connection.execute(
            "SELECT intervention_id FROM doi_interventions "
            "WHERE opportunity_id=? AND intervention_type=?",
            (
                intervention.opportunity_id.value,
                intervention.intervention_type.value,
            ),
        ).fetchone()
        if (
            natural_owner is not None
            and str(natural_owner[0]) != intervention.intervention_id.value
        ):
            raise DOIPersistenceConflict("DOI_INTERVENTION_NATURAL_KEY_CONFLICT")
        inserted = retained is None
        if inserted:
            self.connection.execute(
                "INSERT INTO doi_interventions"
                "(intervention_id, case_id, opportunity_id, intervention_type, status, "
                "action_occurred_at, projection_version, head_sha256, "
                "record_artifact_pk) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    intervention.intervention_id.value,
                    case_key,
                    intervention.opportunity_id.value,
                    intervention.intervention_type.value,
                    intervention.status.value,
                    None
                    if intervention.action_occurred_at is None
                    else intervention.action_occurred_at.value,
                    projection_version,
                    projection_head,
                    artifact_pk,
                ),
            )
        for action in intervention.action_events:
            action_material = _encoded(action)
            prior = self.connection.execute(
                "SELECT record_sha256, record_canonical_bytes FROM "
                "doi_action_verification_events WHERE event_id=?",
                (action.event_id.value,),
            ).fetchone()
            if prior is not None:
                if (
                    str(prior[0]) != action_material.binding.sha256
                    or _stored_bytes(prior[1])
                    != action_material.binding.canonical_bytes
                ):
                    raise DOIPersistenceConflict("DOI_ACTION_OCCURRENCE_CONFLICT")
                continue
            self.connection.execute(
                "INSERT INTO doi_action_verification_events"
                "(event_id, intervention_id, occurrence_id, record_domain, "
                "record_sha256, record_canonical_bytes, record_payload) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    action.event_id.value,
                    intervention.intervention_id.value,
                    action.key.occurrence_id.value,
                    action_material.binding.domain,
                    action_material.binding.sha256,
                    action_material.binding.canonical_bytes,
                    action_material.payload,
                ),
            )
        for sequence, event in enumerate(intervention.value_events, start=1):
            event_material = _encoded(event)
            prior = self.connection.execute(
                "SELECT record_sha256, record_canonical_bytes FROM doi_value_events "
                "WHERE event_id=?",
                (event.event_id.value,),
            ).fetchone()
            if prior is not None:
                if (
                    str(prior[0]) != event_material.binding.sha256
                    or _stored_bytes(prior[1]) != event_material.binding.canonical_bytes
                ):
                    raise DOIPersistenceConflict("DOI_VALUE_OCCURRENCE_CONFLICT")
                continue
            self.connection.execute(
                "INSERT INTO doi_value_events"
                "(intervention_id, event_id, sequence_no, occurrence_id, event_type, "
                "predecessor_sha256, amount_minor_units, currency_code, "
                "currency_registry_version, currency_scale, record_domain, record_sha256, "
                "record_canonical_bytes, record_payload) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    intervention.intervention_id.value,
                    event.event_id.value,
                    sequence,
                    event.key.occurrence_id.value,
                    event.event_type.value,
                    None
                    if event.predecessor_event_binding is None
                    else event.predecessor_event_binding.sha256,
                    event.amount.minor_units,
                    event.amount.currency_code,
                    event.amount.registry_version,
                    event.amount.scale,
                    event_material.binding.domain,
                    event_material.binding.sha256,
                    event_material.binding.canonical_bytes,
                    event_material.payload,
                ),
            )
        if retained is not None and int(retained[3]) != artifact_pk:
            if int(retained[4]) >= projection_version:
                raise DOIPersistenceConflict("DOI_INTERVENTION_PROJECTION_CONFLICT")
            cursor = self.connection.execute(
                "UPDATE doi_interventions SET status=?, action_occurred_at=?, "
                "projection_version=?, head_sha256=?, record_artifact_pk=? "
                "WHERE intervention_id=? AND projection_version=? AND head_sha256=? "
                "AND record_artifact_pk=? AND status=? AND action_occurred_at IS ?",
                (
                    intervention.status.value,
                    None
                    if intervention.action_occurred_at is None
                    else intervention.action_occurred_at.value,
                    projection_version,
                    projection_head,
                    artifact_pk,
                    intervention.intervention_id.value,
                    int(retained[4]),
                    str(retained[5]),
                    int(retained[3]),
                    str(retained[2]),
                    retained[7],
                ),
            )
            if cursor.rowcount != 1:
                raise DOIPersistenceConflict("DOI_INTERVENTION_PROJECTION_RACE")
        readback = self.connection.execute(
            "SELECT case_id, opportunity_id, intervention_type, status, "
            "action_occurred_at, projection_version, head_sha256, record_artifact_pk "
            "FROM doi_interventions WHERE intervention_id=?",
            (intervention.intervention_id.value,),
        ).fetchone()
        if readback is None or tuple(readback) != (
            case_key,
            intervention.opportunity_id.value,
            intervention.intervention_type.value,
            intervention.status.value,
            None
            if intervention.action_occurred_at is None
            else intervention.action_occurred_at.value,
            projection_version,
            projection_head,
            artifact_pk,
        ):
            raise DOIPersistenceIntegrityError(
                "DOI_INTERVENTION_PROJECTION_READBACK_MISMATCH"
            )
        return PersistenceResult(not inserted and artifact_replayed)

    def persist_resulting_search(
        self,
        *,
        case_id: EvidenceId,
        history: DOIResultingOrderLinkSearchHistory,
        created_at: CanonicalTimestamp,
    ) -> PersistenceResult:
        """Append a complete validated search history to its normalized stream."""

        if (
            type(case_id) is not EvidenceId
            or type(history) is not DOIResultingOrderLinkSearchHistory
            or type(created_at) is not CanonicalTimestamp
            or history.projection is None
            or not history.events
        ):
            raise DOIPersistenceError("DOI_RESULTING_SEARCH_INVALID")
        case = self.connection.execute(
            "SELECT order_id FROM doi_cases WHERE case_id=?",
            (case_id.value,),
        ).fetchone()
        if case is None or str(case[0]) != history.parent_order_id.to_json_value():
            raise DOIPersistenceError("DOI_RESULTING_SEARCH_CASE_MISSING")
        projection = history.projection
        payload = encode_payload(projection)
        self._artifact(
            case_id.value,
            "RESULTING_SEARCH",
            f"{history.search_id.value}:{projection.hash_binding().sha256[:24]}",
            projection,
            created_at,
        )
        retained = self.connection.execute(
            "SELECT revision, head_sha256, projection_payload, case_id, "
            "parent_order_id, intervention_type, state "
            "FROM doi_resulting_order_searches WHERE search_id=?",
            (history.search_id.value,),
        ).fetchone()
        if retained is not None and (
            str(retained[3]) != case_id.value
            or str(retained[4]) != history.parent_order_id.to_json_value()
            or str(retained[5]) != history.intervention_type.value
            or str(retained[6])
            != history.events[int(retained[0]) - 1].evidence.state.value
            or
            int(retained[0]) > projection.revision
            or (
                int(retained[0]) == projection.revision
                and (
                    str(retained[1]) != projection.head_event_binding.sha256
                    or _stored_bytes(retained[2]) != payload
                )
            )
        ):
            raise DOIPersistenceConflict("DOI_RESULTING_SEARCH_CONFLICT")
        inserted = retained is None
        if inserted:
            self.connection.execute(
                "INSERT INTO doi_resulting_order_searches"
                "(search_id, case_id, parent_order_id, intervention_type, state, "
                "revision, head_sha256, projection_payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    history.search_id.value,
                    case_id.value,
                    history.parent_order_id.to_json_value(),
                    history.intervention_type.value,
                    projection.state.value,
                    projection.revision,
                    projection.head_event_binding.sha256,
                    payload,
                ),
            )
        for event in history.events:
            material = _encoded(event)
            row = self.connection.execute(
                "SELECT record_sha256, record_canonical_bytes FROM "
                "doi_resulting_order_search_events WHERE event_id=?",
                (event.event_id.value,),
            ).fetchone()
            if row is not None:
                if (
                    str(row[0]) != material.binding.sha256
                    or _stored_bytes(row[1]) != material.binding.canonical_bytes
                ):
                    raise DOIPersistenceConflict(
                        "DOI_RESULTING_SEARCH_OCCURRENCE_CONFLICT"
                    )
                continue
            self.connection.execute(
                "INSERT INTO doi_resulting_order_search_events"
                "(search_id, sequence_no, event_id, predecessor_sha256, record_domain, "
                "record_sha256, record_canonical_bytes, record_payload) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    history.search_id.value,
                    event.sequence,
                    event.event_id.value,
                    None
                    if event.predecessor_binding is None
                    else event.predecessor_binding.sha256,
                    material.binding.domain,
                    material.binding.sha256,
                    material.binding.canonical_bytes,
                    material.payload,
                ),
            )
        if inserted:
            replayed = False
        elif int(retained[0]) == projection.revision:
            replayed = True
        else:
            prior_revision = int(retained[0])
            if (
                prior_revision >= len(history.events)
                or history.events[prior_revision - 1].hash_binding().sha256
                != str(retained[1])
            ):
                raise DOIPersistenceConflict("DOI_RESULTING_SEARCH_HISTORY_CONFLICT")
            cursor = self.connection.execute(
                "UPDATE doi_resulting_order_searches SET state=?, revision=?, "
                "head_sha256=?, projection_payload=? WHERE search_id=? "
                "AND revision=? AND head_sha256=? AND projection_payload=?",
                (
                    projection.state.value,
                    projection.revision,
                    projection.head_event_binding.sha256,
                    payload,
                    history.search_id.value,
                    prior_revision,
                    str(retained[1]),
                    _stored_bytes(retained[2]),
                ),
            )
            if cursor.rowcount != 1:
                raise DOIPersistenceConflict("DOI_RESULTING_SEARCH_PROJECTION_RACE")
            replayed = False
        readback = self.connection.execute(
            "SELECT case_id, parent_order_id, intervention_type, state, "
            "revision, head_sha256, projection_payload "
            "FROM doi_resulting_order_searches WHERE search_id=?",
            (history.search_id.value,),
        ).fetchone()
        if readback is None or tuple(readback) != (
            case_id.value,
            history.parent_order_id.to_json_value(),
            history.intervention_type.value,
            projection.state.value,
            projection.revision,
            projection.head_event_binding.sha256,
            payload,
        ):
            raise DOIPersistenceIntegrityError(
                "DOI_RESULTING_SEARCH_READBACK_MISMATCH"
            )
        return PersistenceResult(replayed)

    def persist_resulting_link(
        self,
        *,
        case_id: EvidenceId,
        link: DOIResultingOrderLink,
        created_at: CanonicalTimestamp,
    ) -> PersistenceResult:
        """Append immutable link revisions and advance their typed projection."""

        if (
            type(case_id) is not EvidenceId
            or type(link) is not DOIResultingOrderLink
            or type(created_at) is not CanonicalTimestamp
        ):
            raise DOIPersistenceError("DOI_RESULTING_LINK_INVALID")
        intervention = self.connection.execute(
            "SELECT case_id, intervention_type FROM doi_interventions "
            "WHERE intervention_id=?",
            (link.intervention_id.value,),
        ).fetchone()
        if (
            intervention is None
            or str(intervention[0]) != case_id.value
            or str(intervention[1]) != link.intervention_type.value
        ):
            raise DOIPersistenceError("DOI_RESULTING_LINK_INTERVENTION_MISSING")
        case = self.connection.execute(
            "SELECT order_id FROM doi_cases WHERE case_id=?",
            (case_id.value,),
        ).fetchone()
        if case is None or str(case[0]) != link.parent_order_id.to_json_value():
            raise DOIPersistenceError("DOI_RESULTING_LINK_CASE_MISMATCH")
        payload = encode_payload(link)
        link_head = link.revisions[-1].hash_binding().sha256
        retained = self.connection.execute(
            "SELECT current_revision, head_sha256, projection_payload, case_id, "
            "intervention_id, parent_order_id, child_order_id, state "
            "FROM doi_resulting_order_links WHERE link_id=?",
            (link.link_id.value,),
        ).fetchone()
        if retained is not None:
            if (
                tuple(retained[3:])
                != (
                    case_id.value,
                    link.intervention_id.value,
                    link.parent_order_id.to_json_value(),
                    link.child_order_id.to_json_value(),
                    link.revisions[int(retained[0]) - 1].state.value,
                )
                or int(retained[0]) > len(link.revisions)
            ):
                raise DOIPersistenceConflict(
                    "DOI_RESULTING_LINK_REVISION_CONFLICT"
                )
        self._artifact(
            case_id.value,
            "RESULTING_LINK",
            f"{link.link_id.value}:{link.hash_binding().sha256[:24]}",
            link,
            created_at,
        )
        inserted = retained is None
        if inserted:
            self.connection.execute(
                "INSERT INTO doi_resulting_order_links"
                "(link_id, case_id, intervention_id, parent_order_id, child_order_id, "
                "state, current_revision, head_sha256, projection_payload) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    link.link_id.value,
                    case_id.value,
                    link.intervention_id.value,
                    link.parent_order_id.to_json_value(),
                    link.child_order_id.to_json_value(),
                    link.state.value,
                    len(link.revisions),
                    link_head,
                    payload,
                ),
            )
        for revision in link.revisions:
            material = _encoded(revision)
            row = self.connection.execute(
                "SELECT record_sha256, record_canonical_bytes FROM "
                "doi_resulting_order_link_revisions WHERE revision_id=?",
                (revision.revision_id.value,),
            ).fetchone()
            if row is not None:
                if (
                    str(row[0]) != material.binding.sha256
                    or _stored_bytes(row[1]) != material.binding.canonical_bytes
                ):
                    raise DOIPersistenceConflict(
                        "DOI_RESULTING_LINK_OCCURRENCE_CONFLICT"
                    )
                continue
            self.connection.execute(
                "INSERT INTO doi_resulting_order_link_revisions"
                "(link_id, revision_no, revision_id, predecessor_sha256, record_domain, "
                "record_sha256, record_canonical_bytes, record_payload) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    link.link_id.value,
                    revision.revision,
                    revision.revision_id.value,
                    revision.predecessor_sha256,
                    material.binding.domain,
                    material.binding.sha256,
                    material.binding.canonical_bytes,
                    material.payload,
                ),
            )
            for ordinal, component in enumerate(revision.mappings, start=1):
                self.connection.execute(
                    "INSERT INTO doi_resulting_order_mapping_components"
                    "(link_id, revision_no, parent_line_id, child_line_id, "
                    "quantity_text, ordinal) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        link.link_id.value,
                        revision.revision,
                        component.parent_line_id.to_json_value(),
                        component.child_line_id.to_json_value(),
                        component.quantity.to_json_value(),
                        ordinal,
                    ),
                )
        if inserted:
            replayed = False
        elif int(retained[0]) == len(link.revisions):
            if str(retained[1]) != link_head or _stored_bytes(retained[2]) != payload:
                raise DOIPersistenceConflict("DOI_RESULTING_LINK_CONFLICT")
            replayed = True
        else:
            prior_revision = int(retained[0])
            if (
                prior_revision >= len(link.revisions)
                or link.revisions[prior_revision - 1].hash_binding().sha256
                != str(retained[1])
            ):
                raise DOIPersistenceConflict("DOI_RESULTING_LINK_HISTORY_CONFLICT")
            cursor = self.connection.execute(
                "UPDATE doi_resulting_order_links SET state=?, current_revision=?, "
                "head_sha256=?, projection_payload=? WHERE link_id=? "
                "AND current_revision=? AND head_sha256=? AND projection_payload=?",
                (
                    link.state.value,
                    len(link.revisions),
                    link_head,
                    payload,
                    link.link_id.value,
                    prior_revision,
                    str(retained[1]),
                    _stored_bytes(retained[2]),
                ),
            )
            if cursor.rowcount != 1:
                raise DOIPersistenceConflict("DOI_RESULTING_LINK_PROJECTION_RACE")
            replayed = False
        readback = self.connection.execute(
            "SELECT case_id, intervention_id, parent_order_id, child_order_id, "
            "state, current_revision, head_sha256, projection_payload "
            "FROM doi_resulting_order_links WHERE link_id=?",
            (link.link_id.value,),
        ).fetchone()
        if readback is None or tuple(readback) != (
            case_id.value,
            link.intervention_id.value,
            link.parent_order_id.to_json_value(),
            link.child_order_id.to_json_value(),
            link.state.value,
            len(link.revisions),
            link_head,
            payload,
        ):
            raise DOIPersistenceIntegrityError("DOI_RESULTING_LINK_READBACK_MISMATCH")
        return PersistenceResult(replayed)

    def _artifact(
        self,
        case_id: str,
        kind: str,
        artifact_id: str,
        record: object,
        created_at: CanonicalTimestamp,
    ) -> tuple[int, bool]:
        material = _encoded(record)
        retained = self.connection.execute(
            "SELECT artifact_pk, case_id, record_domain, record_sha256, "
            "record_canonical_bytes, record_payload FROM doi_case_artifacts "
            "WHERE artifact_kind=? AND artifact_id=?",
            (kind, artifact_id),
        ).fetchone()
        if retained is not None:
            if (
                str(retained[1]) != case_id
                or str(retained[2]) != material.binding.domain
                or str(retained[3]) != material.binding.sha256
                or _stored_bytes(retained[4]) != material.binding.canonical_bytes
                or _stored_bytes(retained[5]) != material.payload
            ):
                raise DOIPersistenceConflict("DOI_IMMUTABLE_ARTIFACT_CONFLICT")
            return int(retained[0]), True
        cursor = self.connection.execute(
            "INSERT INTO doi_case_artifacts"
            "(case_id, artifact_kind, artifact_id, record_domain, record_sha256, "
            "record_canonical_bytes, record_payload, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                case_id,
                kind,
                artifact_id,
                material.binding.domain,
                material.binding.sha256,
                material.binding.canonical_bytes,
                material.payload,
                created_at.value,
            ),
        )
        return int(cursor.lastrowid), False

    def _canonical_artifact(
        self,
        case_id: str,
        kind: str,
        artifact_id: str,
        record: object,
        created_at: CanonicalTimestamp,
    ) -> tuple[int, bool]:
        binding = getattr(record, "hash_binding")()
        canonical = getattr(record, "canonical_bytes")()
        if type(binding) is not HashBinding or canonical != binding.canonical_bytes:
            raise DOIPersistenceError("DOI_CANONICAL_ARTIFACT_INVALID")
        retained = self.connection.execute(
            "SELECT artifact_pk, case_id, record_domain, record_sha256, "
            "record_canonical_bytes, record_payload FROM doi_case_artifacts "
            "WHERE artifact_kind=? AND artifact_id=?",
            (kind, artifact_id),
        ).fetchone()
        if retained is not None:
            if tuple(retained[1:]) != (
                case_id,
                binding.domain,
                binding.sha256,
                canonical,
                canonical,
            ):
                raise DOIPersistenceConflict("DOI_IMMUTABLE_ARTIFACT_CONFLICT")
            return int(retained[0]), True
        cursor = self.connection.execute(
            "INSERT INTO doi_case_artifacts"
            "(case_id, artifact_kind, artifact_id, record_domain, record_sha256, "
            "record_canonical_bytes, record_payload, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                case_id,
                kind,
                artifact_id,
                binding.domain,
                binding.sha256,
                canonical,
                canonical,
                created_at.value,
            ),
        )
        return int(cursor.lastrowid), False

    def persist_case_owner_decision(
        self,
        decision: CaseOwnerDecision,
    ) -> PersistenceResult:
        """Persist one validated case admission and its exact batch owner binding."""

        if type(decision) is not CaseOwnerDecision:
            raise DOIPersistenceError("DOI_CASE_OWNER_DECISION_INVALID")
        validate_case_owner_decision(decision)
        event = decision.result.event
        binding = event.source_binding
        proof = binding.admission_proof
        case_id = event.case_id.value
        order_id = event.order_id.to_json_value()
        retained_case = self.connection.execute(
            "SELECT case_id FROM doi_cases WHERE order_id=?",
            (order_id,),
        ).fetchone()
        if retained_case is None:
            self.connection.execute(
                "INSERT INTO doi_cases(case_id, order_id, created_at) VALUES (?, ?, ?)",
                (case_id, order_id, event.occurred_at.value),
            )
        elif str(retained_case[0]) != case_id:
            raise DOIPersistenceConflict("DOI_ONE_CASE_PER_ORDER_CONFLICT")
        batch_id = binding.source_batch_id.to_json_value()
        batch = self.connection.execute(
            "SELECT identity_domain, identity_sha256, identity_canonical_bytes "
            "FROM doi_source_batches WHERE batch_id=?",
            (batch_id,),
        ).fetchone()
        if batch is None or tuple(batch) != (
            proof.content_binding.domain,
            proof.content_binding.sha256,
            proof.content_binding.canonical_bytes,
        ):
            raise DOIPersistenceConflict("DOI_CASE_ADMISSION_BATCH_CONFLICT")
        proof_pk, _ = self._canonical_artifact(
            case_id,
            "CASE_ADMISSION_PROOF",
            proof.proof_id.value,
            proof,
            event.occurred_at,
        )
        binding_pk, _ = self._canonical_artifact(
            case_id,
            "CASE_SOURCE_BINDING",
            binding.binding_id.value,
            binding,
            event.occurred_at,
        )
        retained_reference = self.connection.execute(
            "SELECT binding_artifact_pk, admission_artifact_pk "
            "FROM doi_case_source_batch_references WHERE case_id=? AND batch_id=?",
            (case_id, batch_id),
        ).fetchone()
        if retained_reference is None:
            self.connection.execute(
                "INSERT INTO doi_case_source_batch_references"
                "(case_id, batch_id, binding_artifact_pk, admission_artifact_pk) "
                "VALUES (?, ?, ?, ?)",
                (case_id, batch_id, binding_pk, proof_pk),
            )
        elif tuple(retained_reference) != (binding_pk, proof_pk):
            raise DOIPersistenceConflict("DOI_CASE_SOURCE_REFERENCE_CONFLICT")
        return self.append_owner_event(
            stream_family="CASE",
            stream_id=case_id,
            current_state=event.case_projection.lifecycle_state.value,
            event_id=event.event_id.value,
            event=event,
            occurred_at=event.occurred_at,
            transition_id=event.transition.transition_id,
            case_id=case_id,
        )

    def persist_extraction(
        self,
        *,
        case_id: EvidenceId,
        result: DOIExtractionResult,
        created_at: CanonicalTimestamp,
    ) -> PersistenceResult:
        """Retain one terminal extraction attempt before evaluation starts."""

        if (
            type(case_id) is not EvidenceId
            or type(result) is not DOIExtractionResult
            or type(created_at) is not CanonicalTimestamp
        ):
            raise DOIPersistenceError("DOI_EXTRACTION_RESULT_INVALID")
        attempt = result.attempt
        run_id = attempt.run_id.to_json_value()
        order_id = attempt.order_id.to_json_value()
        if self.connection.execute(
            "SELECT 1 FROM doi_runs WHERE run_id=?",
            (run_id,),
        ).fetchone() is None:
            raise DOIPersistenceError("DOI_EXTRACTION_RUN_MISSING")
        case = self.connection.execute(
            "SELECT case_id FROM doi_cases WHERE order_id=?",
            (order_id,),
        ).fetchone()
        if case is None:
            self.connection.execute(
                "INSERT INTO doi_cases(case_id, order_id, created_at) VALUES (?, ?, ?)",
                (case_id.value, order_id, created_at.value),
            )
        elif str(case[0]) != case_id.value:
            raise DOIPersistenceConflict("DOI_ONE_CASE_PER_ORDER_CONFLICT")
        artifact_pk, artifact_replayed = self._artifact(
            case_id.value,
            "EXTRACTION_ATTEMPT",
            attempt.attempt_id.to_json_value(),
            attempt,
            created_at,
        )
        retained = self.connection.execute(
            "SELECT record_artifact_pk FROM doi_extraction_attempts "
            "WHERE attempt_id=?",
            (attempt.attempt_id.to_json_value(),),
        ).fetchone()
        if retained is not None:
            if not artifact_replayed or int(retained[0]) != artifact_pk:
                raise DOIPersistenceConflict("DOI_EXTRACTION_ATTEMPT_CONFLICT")
            return PersistenceResult(True)
        expected_snapshot = None
        if attempt.status is ExtractionStatus.SUCCEEDED:
            if result.snapshot is None or result.snapshot.snapshot_id != attempt.snapshot_id:
                raise DOIPersistenceError("DOI_EXTRACTION_SNAPSHOT_INVALID")
            expected_snapshot = attempt.snapshot_id.to_json_value()
        elif result.snapshot is not None:
            raise DOIPersistenceError("DOI_EXTRACTION_FAILURE_SNAPSHOT_INVALID")
        self.connection.execute(
            "INSERT INTO doi_extraction_attempts"
            "(attempt_id, case_id, run_id, order_id, status, snapshot_id, started_at, "
            "completed_at, record_artifact_pk) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                attempt.attempt_id.to_json_value(),
                case_id.value,
                run_id,
                order_id,
                attempt.status.value,
                expected_snapshot,
                attempt.started_at.value,
                attempt.completed_at.value,
                artifact_pk,
            ),
        )
        return PersistenceResult(False)

    def persist_evaluation(
        self,
        *,
        case_id: EvidenceId,
        snapshot: DOIOrderSnapshot,
        evaluation: DOIEvaluation,
        created_at: CanonicalTimestamp,
        reopen_event_id: EvidenceId | None = None,
        fault_injector: FaultInjector | None = None,
    ) -> PersistenceResult:
        if (
            type(case_id) is not EvidenceId
            or type(snapshot) is not DOIOrderSnapshot
            or type(evaluation) is not DOIEvaluation
            or type(created_at) is not CanonicalTimestamp
            or evaluation.snapshot_id != snapshot.snapshot_id
            or evaluation.run_id != snapshot.run_id
            or evaluation.order_id != snapshot.order_id
            or type(reopen_event_id) not in {EvidenceId, type(None)}
        ):
            raise DOIPersistenceError("DOI_EVALUATION_GRAPH_INVALID")
        injector = FaultInjector() if fault_injector is None else fault_injector
        case_key = case_id.value
        order_key = snapshot.order_id.to_json_value()
        run_key = snapshot.run_id.to_json_value()
        lifecycle_state = (
            CaseLifecycleState.ACTIVE
            if evaluation.closure_proposal is None
            else evaluation.closure_proposal.lifecycle_state
        )
        closure_reason = (
            None
            if evaluation.closure_proposal is None
            else evaluation.closure_proposal.reason
        )
        if (
            self.connection.execute(
                "SELECT 1 FROM doi_runs WHERE run_id=?", (run_key,)
            ).fetchone()
            is None
        ):
            raise DOIPersistenceError("DOI_EVALUATION_RUN_MISSING")
        retained_evaluation = self.connection.execute(
            "SELECT a.record_domain, a.record_sha256, a.record_canonical_bytes, "
            "a.record_payload FROM doi_evaluations e JOIN doi_case_artifacts a "
            "ON a.artifact_pk=e.record_artifact_pk WHERE e.evaluation_id=?",
            (evaluation.evaluation_id.value,),
        ).fetchone()
        if retained_evaluation is not None:
            retained = decode_payload(_stored_bytes(retained_evaluation[3]), DOIEvaluation)
            _verify_binding(retained_evaluation, 0, retained)
            normalized = self.connection.execute(
                "SELECT case_id, snapshot_id, run_id, order_id, top_level_state, "
                "transition_id, input_domain, input_sha256, input_canonical_bytes, "
                "output_domain, output_sha256, output_canonical_bytes "
                "FROM doi_evaluations WHERE evaluation_id=?",
                (evaluation.evaluation_id.value,),
            ).fetchone()
            if (
                retained.hash_binding() != evaluation.hash_binding()
                or _stored_bytes(retained_evaluation[3]) != encode_payload(evaluation)
                or normalized is None
                or tuple(normalized)
                != (
                    case_key,
                    snapshot.snapshot_id.to_json_value(),
                    run_key,
                    order_key,
                    evaluation.state.value,
                    evaluation.transition.transition_id,
                    evaluation.input_binding.domain,
                    evaluation.input_binding.sha256,
                    evaluation.input_binding.canonical_bytes,
                    evaluation.output_binding.domain,
                    evaluation.output_binding.sha256,
                    evaluation.output_binding.canonical_bytes,
                )
            ):
                raise DOIPersistenceConflict("DOI_EVALUATION_CONFLICT")
            self._assert_case_projection_consistent(case_key)
            if (
                self._verify_snapshot_proof_children()
                or self._verify_evaluation_children()
            ):
                raise DOIPersistenceIntegrityError(
                    "DOI_EVALUATION_REPLAY_CHILD_MISMATCH"
                )
            return PersistenceResult(True)

        case_row = self.connection.execute(
            "SELECT case_id FROM doi_cases WHERE order_id=?", (order_key,)
        ).fetchone()
        if case_row is None:
            if reopen_event_id is not None:
                raise DOIPersistenceConflict("DOI_REOPEN_CASE_MISSING")
            self.connection.execute(
                "INSERT INTO doi_cases(case_id, order_id, created_at) VALUES (?, ?, ?)",
                (case_key, order_key, created_at.value),
            )
            injector.hit(FaultPoint.AFTER_FIRST_INSERT)
            prior_version = 0
        elif str(case_row[0]) != case_key:
            raise DOIPersistenceConflict("DOI_ONE_CASE_PER_ORDER_CONFLICT")
        else:
            projection_row = self.connection.execute(
                "SELECT projection_version, lifecycle_state, head_sha256, "
                "record_payload "
                "FROM doi_case_projections WHERE case_id=?",
                (case_key,),
            ).fetchone()
            prior_version = 0 if projection_row is None else int(projection_row[0])
            prior_state = None if projection_row is None else str(projection_row[1])
            if projection_row is not None:
                self._assert_case_projection_consistent(case_key)
            if prior_state == CaseLifecycleState.CLOSED_HARD.value:
                raise DOIPersistenceConflict("DOI_HARD_CLOSURE_REOPEN_FORBIDDEN")
            reopening = (
                prior_state == CaseLifecycleState.CLOSED_REVERSIBLE.value
                and lifecycle_state is CaseLifecycleState.ACTIVE
            )
            if reopening:
                canceled = self.connection.execute(
                    "SELECT 1 FROM doi_retention_deadlines WHERE case_id=? "
                    "AND canceled_by_reopen_event_id=?",
                    (
                        case_key,
                        None if reopen_event_id is None else reopen_event_id.value,
                    ),
                ).fetchone()
                if reopen_event_id is None or canceled is None:
                    raise DOIPersistenceConflict(
                        "DOI_REVERSIBLE_REOPEN_DEADLINE_NOT_CANCELED"
                    )
            elif reopen_event_id is not None:
                raise DOIPersistenceConflict("DOI_REOPEN_STATE_CONFLICT")

        snapshot_pk, snapshot_replayed = self._artifact(
            case_key,
            "ORDER_SNAPSHOT",
            snapshot.snapshot_id.to_json_value(),
            snapshot,
            created_at,
        )
        completeness_pk, _ = self._artifact(
            case_key,
            "COMPLETENESS_PROOF",
            snapshot.completeness_proof.hash_binding().sha256,
            snapshot.completeness_proof,
            created_at,
        )
        if not snapshot_replayed:
            self.connection.execute(
                "INSERT INTO doi_order_snapshots"
                "(snapshot_id, case_id, run_id, order_id, source_observed_at, "
                "completeness_sha256, record_artifact_pk) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    snapshot.snapshot_id.to_json_value(), case_key, run_key, order_key,
                    snapshot.source_observed_at.value,
                    snapshot.completeness_proof.hash_binding().sha256,
                    snapshot_pk,
                ),
            )
        completeness_reference = self.connection.execute(
            "SELECT proof_artifact_pk "
            "FROM doi_snapshot_completeness_proof_references WHERE snapshot_id=?",
            (snapshot.snapshot_id.to_json_value(),),
        ).fetchone()
        if completeness_reference is None:
            self.connection.execute(
                "INSERT INTO doi_snapshot_completeness_proof_references"
                "(snapshot_id, proof_artifact_pk) VALUES (?, ?)",
                (snapshot.snapshot_id.to_json_value(), completeness_pk),
            )
        elif int(completeness_reference[0]) != completeness_pk:
            raise DOIPersistenceConflict("DOI_SNAPSHOT_COMPLETENESS_CONFLICT")
        for ordinal, line in enumerate(snapshot.lines, start=1):
            line_key = line.line_snapshot_id.to_json_value()
            if not snapshot_replayed:
                line_pk, line_replayed = self._artifact(
                    case_key, "LINE_SNAPSHOT", line_key, line, created_at
                )
                if line_replayed:
                    continue
                self.connection.execute(
                    "INSERT INTO doi_line_snapshots"
                    "(line_snapshot_id, case_id, snapshot_id, line_ordinal, "
                    "relevant_merchandise, continuity_state, record_artifact_pk) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        line_key, case_key, snapshot.snapshot_id.to_json_value(), ordinal,
                        int(line.relevant_merchandise), line.continuity.state.value, line_pk,
                    ),
                )
            continuity_pk, _ = self._artifact(
                case_key,
                "LINE_CONTINUITY_PROOF",
                line.continuity.hash_binding().sha256,
                line.continuity,
                created_at,
            )
            continuity_reference = self.connection.execute(
                "SELECT proof_artifact_pk FROM doi_line_continuity_proof_references "
                "WHERE line_snapshot_id=?",
                (line_key,),
            ).fetchone()
            if continuity_reference is None:
                self.connection.execute(
                    "INSERT INTO doi_line_continuity_proof_references"
                    "(line_snapshot_id, proof_artifact_pk) VALUES (?, ?)",
                    (line_key, continuity_pk),
                )
            elif int(continuity_reference[0]) != continuity_pk:
                raise DOIPersistenceConflict("DOI_LINE_CONTINUITY_CONFLICT")

        injector.hit(FaultPoint.BEFORE_EVENT_APPEND)
        evaluation_pk, replayed = self._artifact(
            case_key,
            "EVALUATION",
            evaluation.evaluation_id.value,
            evaluation,
            created_at,
        )
        if replayed:
            raise DOIPersistenceIntegrityError("DOI_EVALUATION_ROW_MISSING")
        self.connection.execute(
            "INSERT INTO doi_evaluations"
            "(evaluation_id, case_id, snapshot_id, run_id, order_id, top_level_state, "
            "transition_id, input_domain, input_sha256, input_canonical_bytes, "
            "output_domain, output_sha256, output_canonical_bytes, record_artifact_pk) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                evaluation.evaluation_id.value, case_key,
                evaluation.snapshot_id.to_json_value(), run_key, order_key,
                evaluation.state.value, evaluation.transition.transition_id,
                evaluation.input_binding.domain, evaluation.input_binding.sha256,
                evaluation.input_binding.canonical_bytes,
                evaluation.output_binding.domain, evaluation.output_binding.sha256,
                evaluation.output_binding.canonical_bytes, evaluation_pk,
            ),
        )
        for ordinal, route in enumerate(evaluation.reason_routes, start=1):
            self.connection.execute(
                "INSERT INTO doi_evaluation_reasons"
                "(evaluation_id, reason_code, owning_transition_id, effective_overlay, ordinal) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    evaluation.evaluation_id.value, route.reason.code,
                    None
                    if route.owning_transition is None
                    else route.owning_transition.transition_id,
                    int(route.effective_overlay), ordinal,
                ),
            )
        for opportunity in evaluation.opportunities:
            opportunity_pk, opportunity_replayed = self._artifact(
                case_key,
                "OPPORTUNITY",
                opportunity.opportunity_id.value,
                opportunity,
                created_at,
            )
            if opportunity_replayed:
                raise DOIPersistenceIntegrityError("DOI_OPPORTUNITY_ROW_MISSING")
            money = opportunity.potential_value
            self.connection.execute(
                "INSERT INTO doi_opportunities"
                "(opportunity_id, evaluation_id, case_id, opportunity_type, "
                "potential_state, amount_minor_units, currency_code, "
                "currency_registry_version, currency_scale, mutual_exclusion_group_id, "
                "record_artifact_pk) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    opportunity.opportunity_id.value, evaluation.evaluation_id.value,
                    case_key, opportunity.opportunity_type.value,
                    opportunity.potential_value_state.value,
                    None if money is None else money.minor_units,
                    None if money is None else money.currency_code,
                    None if money is None else money.registry_version,
                    None if money is None else money.scale,
                    None
                    if opportunity.mutual_exclusion_group is None
                    else opportunity.mutual_exclusion_group.value,
                    opportunity_pk,
                ),
            )
            for ordinal, component in enumerate(opportunity.scope.components, start=1):
                self.connection.execute(
                    "INSERT INTO doi_opportunity_scope_components"
                    "(opportunity_id, line_snapshot_id, role, quantity_text, ordinal) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        opportunity.opportunity_id.value,
                        component.line_snapshot_id.to_json_value(), component.role.value,
                        component.quantity.to_json_value(), ordinal,
                    ),
                )
        injector.hit(FaultPoint.AFTER_EVENT_BEFORE_PROJECTION)
        case_record = DOIOrderCase(
            case_id=case_id,
            order_id=snapshot.order_id,
            lifecycle_state=lifecycle_state,
            current_snapshot_id=snapshot.snapshot_id,
            current_evaluation_id=evaluation.evaluation_id,
            terminal_closure_reason=closure_reason,
        )
        projection_payload = encode_payload(case_record)
        new_version = prior_version + 1
        if prior_version == 0:
            self.connection.execute(
                "INSERT INTO doi_case_projections"
                "(case_id, lifecycle_state, current_snapshot_id, current_evaluation_id, "
                "terminal_closure_reason, projection_version, head_sha256, record_payload) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    case_key, lifecycle_state.value, snapshot.snapshot_id.to_json_value(),
                    evaluation.evaluation_id.value,
                    None if closure_reason is None else closure_reason.value,
                    new_version, evaluation.hash_binding().sha256, projection_payload,
                ),
            )
        else:
            cursor = self.connection.execute(
                "UPDATE doi_case_projections SET lifecycle_state=?, current_snapshot_id=?, "
                "current_evaluation_id=?, terminal_closure_reason=?, projection_version=?, "
                "head_sha256=?, record_payload=? WHERE case_id=? AND projection_version=? "
                "AND lifecycle_state=? AND head_sha256=? AND record_payload=?",
                (
                    lifecycle_state.value, snapshot.snapshot_id.to_json_value(),
                    evaluation.evaluation_id.value,
                    None if closure_reason is None else closure_reason.value,
                    new_version, evaluation.hash_binding().sha256, projection_payload,
                    case_key, prior_version, str(projection_row[1]),
                    str(projection_row[2]), _stored_bytes(projection_row[3]),
                ),
            )
            if cursor.rowcount != 1:
                raise DOIPersistenceConflict("DOI_CASE_PROJECTION_RACE")
        readback = self.connection.execute(
            "SELECT lifecycle_state, current_snapshot_id, current_evaluation_id, "
            "terminal_closure_reason, projection_version, head_sha256, record_payload "
            "FROM doi_case_projections WHERE case_id=?",
            (case_key,),
        ).fetchone()
        if readback is None or tuple(readback) != (
            lifecycle_state.value,
            snapshot.snapshot_id.to_json_value(),
            evaluation.evaluation_id.value,
            None if closure_reason is None else closure_reason.value,
            new_version,
            evaluation.hash_binding().sha256,
            projection_payload,
        ):
            raise DOIPersistenceIntegrityError("DOI_CASE_PROJECTION_READBACK_MISMATCH")
        injector.hit(FaultPoint.AFTER_PROJECTION_BEFORE_RECEIPT)
        return PersistenceResult(False)

    def _assert_case_projection_consistent(self, case_id: str) -> None:
        row = self.connection.execute(
            "SELECT p.case_id, c.order_id, p.lifecycle_state, "
            "p.current_snapshot_id, p.current_evaluation_id, "
            "p.terminal_closure_reason, p.projection_version, p.head_sha256, "
            "p.record_payload, a.record_sha256 FROM doi_case_projections p "
            "JOIN doi_cases c ON c.case_id=p.case_id "
            "LEFT JOIN doi_evaluations e "
            "ON e.evaluation_id=p.current_evaluation_id "
            "LEFT JOIN doi_case_artifacts a ON a.artifact_pk=e.record_artifact_pk "
            "WHERE p.case_id=?",
            (case_id,),
        ).fetchone()
        if row is None:
            raise DOIPersistenceIntegrityError("DOI_CASE_PROJECTION_MISSING")
        case = decode_payload(_stored_bytes(row[8]), DOIOrderCase)
        evaluation_count = int(
            self.connection.execute(
                "SELECT COUNT(*) FROM doi_evaluations WHERE case_id=?",
                (case_id,),
            ).fetchone()[0]
        )
        if (
            case.case_id.value != row[0]
            or case.order_id.to_json_value() != row[1]
            or case.lifecycle_state.value != row[2]
            or case.current_snapshot_id is None
            or case.current_snapshot_id.to_json_value() != row[3]
            or case.current_evaluation_id is None
            or case.current_evaluation_id.value != row[4]
            or (
                None
                if case.terminal_closure_reason is None
                else case.terminal_closure_reason.value
            )
            != row[5]
            or evaluation_count != int(row[6])
            or row[9] is None
            or str(row[7]) != str(row[9])
        ):
            raise DOIPersistenceIntegrityError("DOI_CASE_PROJECTION_MISMATCH")

    def get_evaluation(self, evaluation_id: str) -> DOIEvaluation | None:
        row = self.connection.execute(
            "SELECT a.record_domain, a.record_sha256, a.record_canonical_bytes, "
            "a.record_payload FROM doi_evaluations e JOIN doi_case_artifacts a "
            "ON a.artifact_pk=e.record_artifact_pk WHERE e.evaluation_id=?",
            (evaluation_id,),
        ).fetchone()
        if row is None:
            return None
        evaluation = decode_payload(_stored_bytes(row[3]), DOIEvaluation)
        _verify_binding(row, 0, evaluation)
        return evaluation

    def get_snapshot(self, snapshot_id: str) -> DOIOrderSnapshot | None:
        row = self.connection.execute(
            "SELECT a.record_domain, a.record_sha256, a.record_canonical_bytes, "
            "a.record_payload FROM doi_order_snapshots s JOIN doi_case_artifacts a "
            "ON a.artifact_pk=s.record_artifact_pk WHERE s.snapshot_id=?",
            (snapshot_id,),
        ).fetchone()
        if row is None:
            return None
        snapshot = decode_payload(_stored_bytes(row[3]), DOIOrderSnapshot)
        _verify_binding(row, 0, snapshot)
        return snapshot

    def get_case(self, order_id: str) -> DOIOrderCase | None:
        row = self.connection.execute(
            "SELECT p.record_payload FROM doi_cases c JOIN doi_case_projections p "
            "ON p.case_id=c.case_id WHERE c.order_id=?",
            (order_id,),
        ).fetchone()
        if row is None:
            return None
        return decode_payload(_stored_bytes(row[0]), DOIOrderCase)

    def evaluation_recorded_at(
        self,
        *,
        case_id: str,
        evaluation_id: str,
    ) -> CanonicalTimestamp | None:
        row = self.connection.execute(
            "SELECT a.record_domain, a.record_sha256, a.record_canonical_bytes, "
            "a.record_payload, a.created_at FROM doi_case_artifacts a "
            "WHERE a.case_id=? AND a.artifact_kind='EVALUATION' "
            "AND a.artifact_id=?",
            (case_id, evaluation_id),
        ).fetchone()
        if row is None:
            return None
        evaluation = decode_payload(_stored_bytes(row[3]), DOIEvaluation)
        _verify_binding(row, 0, evaluation)
        if evaluation.evaluation_id.value != evaluation_id:
            raise DOIPersistenceIntegrityError("DOI_EVALUATION_ARTIFACT_MISMATCH")
        case = self.connection.execute(
            "SELECT 1 FROM doi_cases WHERE case_id=? AND order_id=?",
            (case_id, evaluation.order_id.to_json_value()),
        ).fetchone()
        if case is None:
            raise DOIPersistenceIntegrityError("DOI_EVALUATION_ARTIFACT_MISMATCH")
        return CanonicalTimestamp(str(row[4]))

    def case_owner_events(
        self,
        *,
        case_id: str,
        limit: int,
    ) -> tuple[DOIOwnerEventRecord, ...]:
        if type(case_id) is not str or type(limit) is not int or limit < 1:
            raise DOIPersistenceError("DOI_OWNER_HISTORY_READ_INVALID")
        rows = self.connection.execute(
            "SELECT e.stream_family, e.stream_id, e.event_id, e.sequence_no, "
            "e.transition_id, e.projection_state, e.predecessor_sha256, "
            "e.occurred_at, e.record_domain, e.record_sha256, "
            "e.record_canonical_bytes, e.record_payload FROM doi_owner_events e "
            "JOIN doi_owner_streams s ON s.stream_family=e.stream_family "
            "AND s.stream_id=e.stream_id WHERE s.case_id=? AND "
            "e.stream_family IN ('CASE', 'LIFECYCLE', 'ATTENTION') "
            "ORDER BY e.occurred_at, e.stream_family, e.sequence_no LIMIT ?",
            (case_id, limit + 1),
        ).fetchall()
        if len(rows) > limit:
            raise DOIPersistenceError("DOI_OWNER_HISTORY_READ_LIMIT_EXCEEDED")
        result: list[DOIOwnerEventRecord] = []
        expected = {
            "event_canonical_b64",
            "event_domain",
            "event_id",
            "event_payload_b64",
            "event_sha256",
            "occurred_at",
            "projected_state",
            "stream_family",
            "stream_id",
            "transition_id",
        }
        for row in rows:
            canonical = _stored_bytes(row[10])
            payload = _stored_bytes(row[11])
            if (
                str(row[8]) != "doi-owner-event-envelope/v1"
                or domain_hash(str(row[8]), canonical).sha256 != str(row[9])
                or payload != canonical
            ):
                raise DOIPersistenceIntegrityError("DOI_OWNER_EVENT_BINDING_MISMATCH")
            try:
                value = parse_canonical_json_bytes(
                    canonical,
                    expected_members=expected,
                )
                if type(value) is not dict:
                    raise ValueError
                event_canonical = base64.b64decode(
                    str(value["event_canonical_b64"]),
                    validate=True,
                )
                base64.b64decode(str(value["event_payload_b64"]), validate=True)
                event_binding = domain_hash(str(value["event_domain"]), event_canonical)
            except (TypeError, ValueError, KeyError):
                raise DOIPersistenceIntegrityError(
                    "DOI_OWNER_EVENT_MATERIAL_INVALID"
                ) from None
            transition = None if row[4] is None else str(row[4])
            if (
                value["stream_family"] != str(row[0])
                or value["stream_id"] != str(row[1])
                or value["event_id"] != str(row[2])
                or value["transition_id"] != transition
                or value["projected_state"] != str(row[5])
                or value["occurred_at"] != str(row[7])
                or value["event_sha256"] != event_binding.sha256
            ):
                raise DOIPersistenceIntegrityError(
                    "DOI_OWNER_EVENT_PROJECTION_MISMATCH"
                )
            result.append(
                DOIOwnerEventRecord(
                    stream_family=str(row[0]),
                    event_id=str(row[2]),
                    projection_state=str(row[5]),
                    occurred_at=CanonicalTimestamp(str(row[7])),
                    transition_id=transition,
                )
            )
        return tuple(result)

    def case_interventions(
        self,
        *,
        case_id: str,
        limit: int,
    ) -> tuple[DOIInterventionHistoryRecord, ...]:
        if type(case_id) is not str or type(limit) is not int or limit < 1:
            raise DOIPersistenceError("DOI_INTERVENTION_HISTORY_READ_INVALID")
        rows = self.connection.execute(
            "SELECT i.case_id, i.intervention_id, i.opportunity_id, "
            "i.intervention_type, i.status, i.action_occurred_at, a.created_at, "
            "a.record_domain, a.record_sha256, a.record_canonical_bytes, "
            "a.record_payload FROM doi_interventions i JOIN doi_case_artifacts a "
            "ON a.artifact_pk=i.record_artifact_pk WHERE i.case_id=? "
            "AND a.artifact_kind='INTERVENTION' "
            "ORDER BY a.created_at, i.intervention_id LIMIT ?",
            (case_id, limit + 1),
        ).fetchall()
        if len(rows) > limit:
            raise DOIPersistenceError("DOI_INTERVENTION_HISTORY_LIMIT_EXCEEDED")
        result: list[DOIInterventionHistoryRecord] = []
        for row in rows:
            intervention = decode_payload(_stored_bytes(row[10]), DOIIntervention)
            _verify_binding(row, 7, intervention)
            action_at = (
                None
                if intervention.action_occurred_at is None
                else intervention.action_occurred_at.value
            )
            if (
                str(row[0]) != case_id
                or str(row[1]) != intervention.intervention_id.value
                or str(row[2]) != intervention.opportunity_id.value
                or str(row[3]) != intervention.intervention_type.value
                or str(row[4]) != intervention.status.value
                or row[5] != action_at
            ):
                raise DOIPersistenceIntegrityError(
                    "DOI_INTERVENTION_HISTORY_PROJECTION_MISMATCH"
                )
            result.append(
                DOIInterventionHistoryRecord(
                    intervention=intervention,
                    created_at=CanonicalTimestamp(str(row[6])),
                )
            )
        return tuple(result)

    def append_owner_event(
        self,
        *,
        stream_family: str,
        stream_id: str,
        current_state: str,
        event_id: str,
        event: object,
        occurred_at: CanonicalTimestamp,
        transition_id: str | None = None,
        case_id: str | None = None,
        run_id: str | None = None,
    ) -> PersistenceResult:
        allowed = {
            "CASE", "LIFECYCLE", "ACTION_CONTEXT", "CONTACT", "CONTACT_WORKFLOW",
            "WWC", "DEDUPE", "ATTENTION", "HUMAN_FACT", "RESULTING_SEARCH",
            "RESULTING_LINK", "INTERVENTION_VALUE", "KPI",
        }
        if stream_family not in allowed or type(occurred_at) is not CanonicalTimestamp:
            raise DOIPersistenceError("DOI_OWNER_STREAM_INVALID")
        try:
            material = _encoded(event)
        except DOIPersistenceIntegrityError:
            binding = getattr(event, "hash_binding")()
            canonical = getattr(event, "canonical_bytes")()
            if type(binding) is not HashBinding or canonical != binding.canonical_bytes:
                raise DOIPersistenceError("DOI_OWNER_EVENT_INVALID") from None
            material = _EncodedRecord(canonical, binding)
        envelope_value = {
            "event_canonical_b64": base64.b64encode(
                material.binding.canonical_bytes
            ).decode("ascii"),
            "event_domain": material.binding.domain,
            "event_id": event_id,
            "event_payload_b64": base64.b64encode(material.payload).decode("ascii"),
            "event_sha256": material.binding.sha256,
            "occurred_at": occurred_at.value,
            "projected_state": current_state,
            "stream_family": stream_family,
            "stream_id": stream_id,
            "transition_id": transition_id,
        }
        envelope = canonical_json_bytes(
            envelope_value,
            expected_members=set(envelope_value),
        )
        material = _EncodedRecord(
            envelope,
            domain_hash("doi-owner-event-envelope/v1", envelope),
        )
        retained = self.connection.execute(
            "SELECT stream_id, sequence_no, projection_state, record_domain, "
            "record_sha256, record_canonical_bytes, record_payload "
            "FROM doi_owner_events WHERE stream_family=? AND event_id=?",
            (stream_family, event_id),
        ).fetchone()
        if retained is not None:
            if (
                str(retained[0]) != stream_id
                or str(retained[2]) != current_state
                or str(retained[3]) != material.binding.domain
                or str(retained[4]) != material.binding.sha256
                or _stored_bytes(retained[5]) != material.binding.canonical_bytes
                or _stored_bytes(retained[6]) != material.payload
            ):
                raise DOIPersistenceConflict("DOI_OWNER_EVENT_CONFLICT")
            stream = self.connection.execute(
                "SELECT case_id, run_id, current_state, sequence_no, head_sha256, "
                "projection_payload FROM doi_owner_streams "
                "WHERE stream_family=? AND stream_id=?",
                (stream_family, stream_id),
            ).fetchone()
            anchor = self.connection.execute(
                "SELECT case_id, run_id FROM doi_owner_stream_anchors "
                "WHERE stream_family=? AND stream_id=?",
                (stream_family, stream_id),
            ).fetchone()
            expected_stream = (
                case_id,
                run_id,
                current_state,
                int(retained[1]),
                material.binding.sha256,
                material.payload,
            )
            if (
                stream is None
                or anchor is None
                or tuple(anchor) != (case_id, run_id)
                or tuple(stream) != expected_stream
            ):
                raise DOIPersistenceIntegrityError(
                    "DOI_OWNER_STREAM_REPLAY_MISMATCH"
                )
            return PersistenceResult(True)
        stream = self.connection.execute(
            "SELECT sequence_no, head_sha256 FROM doi_owner_streams "
            "WHERE stream_family=? AND stream_id=?",
            (stream_family, stream_id),
        ).fetchone()
        if stream is None:
            sequence = 1
            predecessor = None
            self.connection.execute(
                "INSERT INTO doi_owner_stream_anchors"
                "(stream_family, stream_id, case_id, run_id, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (stream_family, stream_id, case_id, run_id, occurred_at.value),
            )
            self.connection.execute(
                "INSERT INTO doi_owner_streams"
                "(stream_id, stream_family, case_id, run_id, current_state, sequence_no, "
                "head_sha256, projection_payload) VALUES (?, ?, ?, ?, ?, 0, NULL, ?)",
                (stream_id, stream_family, case_id, run_id, current_state, material.payload),
            )
        else:
            sequence = int(stream[0]) + 1
            predecessor = None if stream[1] is None else str(stream[1])
        self.connection.execute(
            "INSERT INTO doi_owner_events"
            "(stream_family, stream_id, event_id, sequence_no, transition_id, "
            "projection_state, predecessor_sha256, occurred_at, record_domain, record_sha256, "
            "record_canonical_bytes, record_payload) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                stream_family, stream_id, event_id, sequence, transition_id, current_state,
                predecessor, occurred_at.value, material.binding.domain, material.binding.sha256,
                material.binding.canonical_bytes, material.payload,
            ),
        )
        cursor = self.connection.execute(
            "UPDATE doi_owner_streams SET current_state=?, sequence_no=?, head_sha256=?, "
            "projection_payload=? WHERE stream_family=? AND stream_id=? AND sequence_no=?",
            (
                current_state, sequence, material.binding.sha256, material.payload,
                stream_family, stream_id, sequence - 1,
            ),
        )
        if cursor.rowcount != 1:
            raise DOIPersistenceConflict("DOI_OWNER_STREAM_RACE")
        readback = self.connection.execute(
            "SELECT current_state, sequence_no, head_sha256, projection_payload "
            "FROM doi_owner_streams WHERE stream_family=? AND stream_id=?",
            (stream_family, stream_id),
        ).fetchone()
        if readback is None or tuple(readback) != (
            current_state,
            sequence,
            material.binding.sha256,
            material.payload,
        ):
            raise DOIPersistenceIntegrityError("DOI_OWNER_STREAM_READBACK_MISMATCH")
        return PersistenceResult(False)

    def retain_kpi(
        self,
        *,
        case_id: EvidenceId,
        event: KPIContributionEvent,
        contribution: RetainedKPIContribution,
    ) -> PersistenceResult:
        if (
            type(case_id) is not EvidenceId
            or type(event) is not KPIContributionEvent
            or type(contribution) is not RetainedKPIContribution
            or event.intervention_id != contribution.intervention_id
            or event.sequence != contribution.revision
            or event.hash_binding() != contribution.head_event_binding
        ):
            raise DOIPersistenceError("DOI_KPI_GRAPH_INVALID")
        event_material = _encoded(event)
        payload = encode_payload(contribution)
        intervention_id = contribution.intervention_id.value
        self._artifact(
            case_id.value,
            "KPI_CONTRIBUTION",
            f"{intervention_id}:{contribution.hash_binding().sha256[:24]}",
            contribution,
            event.action_occurred_at,
        )
        retained = self.connection.execute(
            "SELECT sequence_no, predecessor_sha256, record_sha256, "
            "record_canonical_bytes, record_payload "
            "FROM doi_kpi_contribution_events WHERE event_id=?",
            (event.event_id.value,),
        ).fetchone()
        if retained is not None:
            retained_projection = self.connection.execute(
                "SELECT case_id, intervention_type, action_date, amount_minor_units, "
                "currency_code, currency_registry_version, currency_scale, revision, "
                "head_sha256, record_payload "
                "FROM doi_retained_kpi_contributions "
                "WHERE intervention_id=?",
                (intervention_id,),
            ).fetchone()
            if (
                int(retained[0]) != event.sequence
                or retained[1]
                != (
                    None
                    if event.predecessor_binding is None
                    else event.predecessor_binding.sha256
                )
                or str(retained[2]) != event_material.binding.sha256
                or _stored_bytes(retained[3]) != event_material.binding.canonical_bytes
                or _stored_bytes(retained[4]) != event_material.payload
                or retained_projection is None
                or tuple(retained_projection)
                != (
                    case_id.value,
                    contribution.intervention_type.value,
                    contribution.action_date.isoformat(),
                    contribution.current_value.minor_units,
                    contribution.current_value.currency_code,
                    contribution.current_value.registry_version,
                    contribution.current_value.scale,
                    contribution.revision,
                    contribution.head_event_binding.sha256,
                    payload,
                )
            ):
                raise DOIPersistenceConflict("DOI_KPI_EVENT_CONFLICT")
            return PersistenceResult(True)
        intervention = self.connection.execute(
            "SELECT case_id, intervention_type FROM doi_interventions "
            "WHERE intervention_id=?",
            (intervention_id,),
        ).fetchone()
        if (
            intervention is None
            or str(intervention[0]) != case_id.value
            or str(intervention[1]) != contribution.intervention_type.value
        ):
            raise DOIPersistenceError("DOI_KPI_INTERVENTION_MISSING")
        predecessor = self.connection.execute(
            "SELECT sequence_no, record_sha256 FROM doi_kpi_contribution_events "
            "WHERE intervention_id=? ORDER BY sequence_no DESC LIMIT 1",
            (intervention_id,),
        ).fetchone()
        expected_sequence = 1 if predecessor is None else int(predecessor[0]) + 1
        expected_predecessor = None if predecessor is None else str(predecessor[1])
        supplied_predecessor = (
            None
            if event.predecessor_binding is None
            else event.predecessor_binding.sha256
        )
        if (
            event.sequence != expected_sequence
            or supplied_predecessor != expected_predecessor
        ):
            raise DOIPersistenceConflict("DOI_KPI_SEQUENCE_CONFLICT")
        prior_projection = self.connection.execute(
            "SELECT revision, head_sha256, record_payload "
            "FROM doi_retained_kpi_contributions WHERE intervention_id=?",
            (intervention_id,),
        ).fetchone()
        if prior_projection is None:
            if contribution.revision != 1:
                raise DOIPersistenceConflict("DOI_KPI_PROJECTION_GAP")
        elif (
            int(prior_projection[0]) != contribution.revision - 1
            or str(prior_projection[1]) != expected_predecessor
        ):
            raise DOIPersistenceConflict("DOI_KPI_PROJECTION_CONFLICT")
        self.connection.execute(
            "INSERT INTO doi_kpi_contribution_events"
            "(intervention_id, sequence_no, event_id, predecessor_sha256, record_domain, "
            "record_sha256, record_canonical_bytes, record_payload) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                intervention_id, event.sequence, event.event_id.value,
                None if event.predecessor_binding is None else event.predecessor_binding.sha256,
                event_material.binding.domain, event_material.binding.sha256,
                event_material.binding.canonical_bytes, event_material.payload,
            ),
        )
        money = contribution.current_value
        projection_values = (
            case_id.value,
            contribution.intervention_type.value,
            contribution.action_date.isoformat(),
            money.minor_units,
            money.currency_code,
            money.registry_version,
            money.scale,
            contribution.revision,
            contribution.head_event_binding.sha256,
            payload,
        )
        if prior_projection is None:
            self.connection.execute(
                "INSERT INTO doi_retained_kpi_contributions"
                "(intervention_id, case_id, intervention_type, action_date, "
                "amount_minor_units, currency_code, currency_registry_version, "
                "currency_scale, revision, head_sha256, record_payload) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (intervention_id, *projection_values),
            )
        else:
            cursor = self.connection.execute(
                "UPDATE doi_retained_kpi_contributions SET case_id=?, "
                "intervention_type=?, action_date=?, amount_minor_units=?, "
                "currency_code=?, currency_registry_version=?, currency_scale=?, "
                "revision=?, head_sha256=?, record_payload=? WHERE intervention_id=? "
                "AND revision=? AND head_sha256=? AND record_payload=?",
                (
                    *projection_values,
                    intervention_id,
                    int(prior_projection[0]),
                    str(prior_projection[1]),
                    _stored_bytes(prior_projection[2]),
                ),
            )
            if cursor.rowcount != 1:
                raise DOIPersistenceConflict("DOI_KPI_PROJECTION_RACE")
        readback = self.connection.execute(
            "SELECT case_id, intervention_type, action_date, amount_minor_units, "
            "currency_code, currency_registry_version, currency_scale, revision, "
            "head_sha256, record_payload FROM doi_retained_kpi_contributions "
            "WHERE intervention_id=?",
            (intervention_id,),
        ).fetchone()
        if readback is None or tuple(readback) != projection_values:
            raise DOIPersistenceIntegrityError("DOI_KPI_PROJECTION_READBACK_MISMATCH")
        return PersistenceResult(False)

    def schedule_retention(
        self,
        projection: DoiRetentionProjection,
        *,
        created_at: CanonicalTimestamp,
    ) -> PersistenceResult:
        if (
            type(projection) is not DoiRetentionProjection
            or type(created_at) is not CanonicalTimestamp
            or projection.purge_eligible_at is None
        ):
            raise DOIPersistenceError("DOI_RETENTION_PROJECTION_INVALID")
        binding = projection.binding
        case_key = binding.case_id.value
        case_row = self.connection.execute(
            "SELECT lifecycle_state FROM doi_case_projections WHERE case_id=?",
            (case_key,),
        ).fetchone()
        if case_row is None or str(case_row[0]) != binding.lifecycle_state.value:
            raise DOIPersistenceConflict("DOI_RETENTION_CASE_STATE_CONFLICT")
        retained = self.connection.execute(
            "SELECT record_payload FROM doi_retention_deadlines WHERE deadline_id=?",
            (binding.closure_event_id.value,),
        ).fetchone()
        payload = encode_payload(projection)
        if retained is not None:
            if _stored_bytes(retained[0]) != payload:
                raise DOIPersistenceConflict("DOI_RETENTION_DEADLINE_CONFLICT")
            return PersistenceResult(True)
        self._artifact(
            case_key,
            "RETENTION_BINDING",
            binding.closure_event_id.value,
            binding,
            created_at,
        )
        self.connection.execute(
            "INSERT INTO doi_retention_deadlines"
            "(deadline_id, case_id, closure_event_id, lifecycle_state, closure_reason, "
            "closed_at, purge_eligible_at, policy_version, timezone_database_binding, "
            "canceled_by_reopen_event_id, record_payload) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)",
            (
                binding.closure_event_id.value,
                case_key,
                binding.closure_event_id.value,
                binding.lifecycle_state.value,
                binding.closure_reason.value,
                binding.closed_at.value,
                projection.purge_eligible_at.value,
                binding.retention_policy_version,
                binding.timezone_database_binding,
                payload,
            ),
        )
        return PersistenceResult(False)

    def cancel_retention_on_reopen(
        self,
        projection: DoiRetentionProjection,
    ) -> PersistenceResult:
        """Cancel only the exact active reversible deadline proved by the domain."""

        if (
            type(projection) is not DoiRetentionProjection
            or projection.purge_eligible_at is not None
            or projection.canceled_by_reopen_event_id is None
            or projection.binding.lifecycle_state
            is not CaseLifecycleState.CLOSED_REVERSIBLE
        ):
            raise DOIPersistenceError("DOI_REOPEN_RETENTION_INVALID")
        binding = projection.binding
        retained = self.connection.execute(
            "SELECT d.record_payload, d.canceled_by_reopen_event_id, "
            "p.lifecycle_state FROM doi_retention_deadlines d "
            "JOIN doi_case_projections p ON p.case_id=d.case_id "
            "WHERE d.deadline_id=? AND d.case_id=?",
            (binding.closure_event_id.value, binding.case_id.value),
        ).fetchone()
        if retained is None:
            raise DOIPersistenceConflict("DOI_REOPEN_DEADLINE_MISSING")
        stored = decode_payload(
            _stored_bytes(retained[0]),
            DoiRetentionProjection,
        )
        if stored.binding.canonical_bytes() != binding.canonical_bytes():
            raise DOIPersistenceConflict("DOI_REOPEN_BINDING_CONFLICT")
        canceled_by = projection.canceled_by_reopen_event_id.value
        if retained[1] is not None:
            if str(retained[1]) != canceled_by or stored != projection:
                raise DOIPersistenceConflict("DOI_REOPEN_OCCURRENCE_CONFLICT")
            return PersistenceResult(True)
        if str(retained[2]) != CaseLifecycleState.CLOSED_REVERSIBLE.value:
            raise DOIPersistenceConflict("DOI_REOPEN_CASE_STATE_CONFLICT")
        self.connection.execute(
            "UPDATE doi_retention_deadlines SET canceled_by_reopen_event_id=?, "
            "record_payload=? WHERE deadline_id=? "
            "AND canceled_by_reopen_event_id IS NULL",
            (
                canceled_by,
                encode_payload(projection),
                binding.closure_event_id.value,
            ),
        )
        return PersistenceResult(False)

    def _verify_normalized_source_children(self) -> tuple[str, ...]:
        attempts = self.connection.execute(
            "SELECT attempt_id, run_id, ordinal, source_identity_id, state, "
            "started_at, completed_at, source_batch_id, portal_read_count, "
            "projection_version, head_sha256, record_domain, record_sha256, "
            "record_canonical_bytes, record_payload "
            "FROM doi_source_import_attempts ORDER BY attempt_id"
        ).fetchall()
        for row in attempts:
            try:
                attempt = decode_payload(
                    _stored_bytes(row[14]),
                    DOISourceImportAttempt,
                )
                _verify_binding(row, 11, attempt)
                events = self.connection.execute(
                    "SELECT sequence_no, event_kind, occurred_at, "
                    "predecessor_sha256, record_domain, record_sha256, "
                    "record_canonical_bytes, record_payload "
                    "FROM doi_source_import_attempt_events WHERE attempt_id=? "
                    "ORDER BY sequence_no",
                    (str(row[0]),),
                ).fetchall()
                predecessor = None
                for sequence, event in enumerate(events, start=1):
                    decoded_event = decode_payload(
                        _stored_bytes(event[7]),
                        DOISourceImportAttemptEvent,
                    )
                    _verify_binding(event, 4, decoded_event)
                    if (
                        int(event[0]) != sequence
                        or decoded_event.sequence.value != sequence
                        or str(event[1]) != decoded_event.event_kind.value
                        or str(event[2]) != decoded_event.occurred_at.value
                        or event[3] != predecessor
                    ):
                        raise DOIPersistenceIntegrityError(
                            "DOI_SOURCE_ATTEMPT_PROJECTION_MISMATCH"
                        )
                    predecessor = str(event[5])
                if (
                    attempt.attempt_id.to_json_value() != row[0]
                    or tuple(row[1:9])
                    != (
                        attempt.run_id.value,
                        attempt.ordinal.value,
                        _text_id(attempt.source_identity_id),
                        attempt.state.value,
                        attempt.started_at.value,
                        None
                        if attempt.completed_at is None
                        else attempt.completed_at.value,
                        None
                        if attempt.source_batch_id is None
                        else attempt.source_batch_id.to_json_value(),
                        attempt.portal_read_count.value,
                    )
                    or len(events) != int(row[9])
                    or predecessor != row[10]
                ):
                    raise DOIPersistenceIntegrityError(
                        "DOI_SOURCE_ATTEMPT_PROJECTION_MISMATCH"
                    )
            except (DOIPersistenceError, TypeError, ValueError):
                return ("DOI_SOURCE_ATTEMPT_PROJECTION_MISMATCH",)
        references = self.connection.execute(
            "SELECT r.attempt_id, r.batch_id, a.source_batch_id, "
            "b.record_domain, b.record_sha256, b.record_canonical_bytes, "
            "b.record_payload FROM doi_attempt_batch_references r "
            "JOIN doi_source_import_attempts a ON a.attempt_id=r.attempt_id "
            "JOIN doi_source_batches b ON b.batch_id=r.batch_id "
            "ORDER BY r.attempt_id"
        ).fetchall()
        expected_reference_attempts = tuple(
            str(item[0])
            for item in self.connection.execute(
                "SELECT attempt_id FROM doi_source_import_attempts "
                "WHERE source_batch_id IS NOT NULL ORDER BY attempt_id"
            ).fetchall()
        )
        if tuple(str(item[0]) for item in references) != expected_reference_attempts:
            return ("DOI_SOURCE_BATCH_REFERENCE_MISMATCH",)
        for row in references:
            try:
                batch = decode_payload(_stored_bytes(row[6]), DOISourceBatch)
                _verify_binding(row, 3, batch)
                if row[1] != row[2] or batch.batch_id.to_json_value() != row[1]:
                    raise DOIPersistenceIntegrityError(
                        "DOI_SOURCE_BATCH_REFERENCE_MISMATCH"
                    )
                staged_rows = self.connection.execute(
                    "SELECT order_id, batch_id, record_domain, record_sha256, "
                    "record_canonical_bytes, record_payload FROM doi_staged_orders "
                    "WHERE attempt_id=? ORDER BY order_id",
                    (str(row[0]),),
                ).fetchall()
                expected_staged = tuple(
                    sorted(batch.staged_orders, key=lambda item: item.order_id.value)
                )
                if len(staged_rows) != len(expected_staged):
                    raise DOIPersistenceIntegrityError(
                        "DOI_STAGED_ORDER_CHILD_MISMATCH"
                    )
                for stored, staged in zip(
                    staged_rows,
                    expected_staged,
                    strict=True,
                ):
                    decoded = decode_payload(_stored_bytes(stored[5]), type(staged))
                    _verify_binding(stored, 2, decoded)
                    source_refs = tuple(
                        str(item[0])
                        for item in self.connection.execute(
                            "SELECT source_ref_id FROM doi_staged_order_source_refs "
                            "WHERE attempt_id=? AND order_id=? ORDER BY ordinal",
                            (str(row[0]), staged.order_id.value),
                        ).fetchall()
                    )
                    if (
                        str(stored[0]) != staged.order_id.value
                        or str(stored[1]) != str(row[1])
                        or decoded != staged
                        or source_refs
                        != tuple(item.to_json_value() for item in staged.source_ref_ids)
                    ):
                        raise DOIPersistenceIntegrityError(
                            "DOI_STAGED_ORDER_CHILD_MISMATCH"
                        )
                rejected_rows = self.connection.execute(
                    "SELECT record_domain, record_sha256, record_canonical_bytes, "
                    "record_payload FROM doi_rejected_source_records "
                    "WHERE attempt_id=? ORDER BY order_id",
                    (str(row[0]),),
                ).fetchall()
                expected_rejected = tuple(
                    sorted(batch.rejected_records, key=lambda item: item.order_id.value)
                )
                if len(rejected_rows) != len(expected_rejected):
                    raise DOIPersistenceIntegrityError(
                        "DOI_REJECTED_SOURCE_CHILD_MISMATCH"
                    )
                for stored, rejected in zip(
                    rejected_rows,
                    expected_rejected,
                    strict=True,
                ):
                    decoded = decode_payload(_stored_bytes(stored[3]), type(rejected))
                    _verify_binding(stored, 0, decoded)
                    if decoded != rejected:
                        raise DOIPersistenceIntegrityError(
                            "DOI_REJECTED_SOURCE_CHILD_MISMATCH"
                        )
            except (DOIPersistenceError, TypeError, ValueError):
                return ("DOI_SOURCE_NORMALIZED_CHILD_MISMATCH",)
        work_rows = self.connection.execute(
            "SELECT work_item_id, run_id, order_id, origin, source_batch_id, "
            "record_domain, record_sha256, record_canonical_bytes, record_payload "
            "FROM doi_run_work_items ORDER BY run_id, work_item_id"
        ).fetchall()
        disposition_rows = self.connection.execute(
            "SELECT work_item_id, run_id, disposition_kind, occurred_at, "
            "record_domain, record_sha256, record_canonical_bytes, record_payload "
            "FROM doi_run_work_dispositions ORDER BY run_id, work_item_id"
        ).fetchall()
        try:
            for row in work_rows:
                item = decode_payload(_stored_bytes(row[8]), DOIRunWorkItem)
                _verify_binding(row, 5, item)
                if tuple(row[:5]) != (
                    item.work_item_id.to_json_value(),
                    item.run_id.value,
                    item.order_id.value,
                    item.origin.value,
                    None
                    if item.source_batch_id is None
                    else item.source_batch_id.to_json_value(),
                ):
                    raise DOIPersistenceIntegrityError(
                        "DOI_RUN_WORK_ITEM_CHILD_MISMATCH"
                    )
            for row in disposition_rows:
                disposition = decode_payload(
                    _stored_bytes(row[7]),
                    DOIRunWorkDisposition,
                )
                _verify_binding(row, 4, disposition)
                if tuple(row[:4]) != (
                    disposition.work_item_id.to_json_value(),
                    disposition.run_id.value,
                    disposition.kind.value,
                    disposition.occurred_at.value,
                ):
                    raise DOIPersistenceIntegrityError(
                        "DOI_RUN_WORK_DISPOSITION_CHILD_MISMATCH"
                    )
            run_counts = self.connection.execute(
                "SELECT run_id, work_item_count, disposition_subject_count "
                "FROM doi_run_projections ORDER BY run_id"
            ).fetchall()
            for row in run_counts:
                work_count = sum(
                    1 for item in work_rows if str(item[1]) == str(row[0])
                )
                disposition_count = sum(
                    1
                    for item in disposition_rows
                    if str(item[1]) == str(row[0])
                )
                if work_count != int(row[1]) or disposition_count != int(row[2]):
                    raise DOIPersistenceIntegrityError(
                        "DOI_RUN_WORK_CHILD_COUNT_MISMATCH"
                    )
        except (DOIPersistenceError, TypeError, ValueError):
            return ("DOI_RUN_WORK_CHILD_MISMATCH",)
        return ()

    def _verify_case_source_and_proof_children(self) -> tuple[str, ...]:
        references = self.connection.execute(
            "SELECT r.case_id, r.batch_id, b.record_domain, b.record_sha256, "
            "b.record_canonical_bytes, b.record_payload, p.record_domain, "
            "p.record_sha256, p.record_canonical_bytes, p.record_payload "
            "FROM doi_case_source_batch_references r "
            "JOIN doi_case_artifacts b ON b.artifact_pk=r.binding_artifact_pk "
            "JOIN doi_case_artifacts p ON p.artifact_pk=r.admission_artifact_pk "
            "ORDER BY r.case_id, r.batch_id"
        ).fetchall()
        artifact_counts = tuple(
            int(item[0])
            for item in self.connection.execute(
                "SELECT COUNT(*) FROM doi_case_artifacts "
                "WHERE artifact_kind='CASE_SOURCE_BINDING' UNION ALL "
                "SELECT COUNT(*) FROM doi_case_artifacts "
                "WHERE artifact_kind='CASE_ADMISSION_PROOF'"
            ).fetchall()
        )
        admitted_case_ids = tuple(
            str(item[0])
            for item in self.connection.execute(
                "SELECT DISTINCT stream_id FROM doi_owner_events "
                "WHERE stream_family='CASE' ORDER BY stream_id"
            ).fetchall()
        )
        referenced_case_ids = tuple(str(row[0]) for row in references)
        if (
            artifact_counts != (len(references), len(references))
            or referenced_case_ids != admitted_case_ids
        ):
            return ("DOI_CASE_SOURCE_PROOF_MISMATCH",)
        for row in references:
            try:
                binding_canonical = _stored_bytes(row[4])
                proof_canonical = _stored_bytes(row[8])
                binding_hash = domain_hash(
                    str(row[2]),
                    binding_canonical,
                )
                proof_hash = domain_hash(
                    str(row[6]),
                    proof_canonical,
                )
                binding = json.loads(binding_canonical.decode("utf-8"))
                proof = json.loads(proof_canonical.decode("utf-8"))
                batch = self.connection.execute(
                    "SELECT identity_domain, identity_sha256, identity_canonical_bytes "
                    "FROM doi_source_batches WHERE batch_id=?",
                    (str(row[1]),),
                ).fetchone()
                if (
                    binding_hash.sha256 != row[3]
                    or proof_hash.sha256 != row[7]
                    or _stored_bytes(row[5]) != binding_canonical
                    or _stored_bytes(row[9]) != proof_canonical
                    or binding["case_id"] != row[0]
                    or binding["source_batch_id"] != row[1]
                    or binding["admission_proof"]
                    != {
                        "domain": proof_hash.domain,
                        "sha256": proof_hash.sha256,
                    }
                    or batch is None
                    or str(batch[0]) != proof["content_binding"]["domain"]
                    or str(batch[1]) != proof["content_binding"]["sha256"]
                    or domain_hash(
                        str(batch[0]),
                        _stored_bytes(batch[2]),
                    ).sha256
                    != str(batch[1])
                ):
                    raise DOIPersistenceIntegrityError(
                        "DOI_CASE_SOURCE_PROOF_MISMATCH"
                    )
            except (DOIPersistenceError, KeyError, TypeError, ValueError):
                return ("DOI_CASE_SOURCE_PROOF_MISMATCH",)
        return ()

    def _verify_snapshot_proof_children(self) -> tuple[str, ...]:
        snapshots = self.connection.execute(
            "SELECT s.snapshot_id, s.case_id, a.record_domain, a.record_sha256, "
            "a.record_canonical_bytes, a.record_payload, p.record_domain, "
            "p.record_sha256, p.record_canonical_bytes, p.record_payload "
            "FROM doi_order_snapshots s JOIN doi_case_artifacts a "
            "ON a.artifact_pk=s.record_artifact_pk "
            "JOIN doi_snapshot_completeness_proof_references r "
            "ON r.snapshot_id=s.snapshot_id JOIN doi_case_artifacts p "
            "ON p.artifact_pk=r.proof_artifact_pk ORDER BY s.snapshot_id"
        ).fetchall()
        snapshot_count = int(
            self.connection.execute(
                "SELECT COUNT(*) FROM doi_order_snapshots"
            ).fetchone()[0]
        )
        if snapshot_count != len(snapshots):
            return ("DOI_SNAPSHOT_PROOF_CHILD_MISMATCH",)
        for row in snapshots:
            try:
                snapshot = decode_payload(_stored_bytes(row[5]), DOIOrderSnapshot)
                proof = decode_payload(
                    _stored_bytes(row[9]),
                    WholeOrderCompletenessProof,
                )
                _verify_binding(row, 2, snapshot)
                _verify_binding(row, 6, proof)
                if snapshot.completeness_proof != proof:
                    raise DOIPersistenceIntegrityError(
                        "DOI_SNAPSHOT_PROOF_CHILD_MISMATCH"
                    )
                line_rows = self.connection.execute(
                    "SELECT l.line_snapshot_id, a.record_domain, a.record_sha256, "
                    "a.record_canonical_bytes, a.record_payload, p.record_domain, "
                    "p.record_sha256, p.record_canonical_bytes, p.record_payload "
                    "FROM doi_line_snapshots l JOIN doi_case_artifacts a "
                    "ON a.artifact_pk=l.record_artifact_pk "
                    "JOIN doi_line_continuity_proof_references r "
                    "ON r.line_snapshot_id=l.line_snapshot_id "
                    "JOIN doi_case_artifacts p ON p.artifact_pk=r.proof_artifact_pk "
                    "WHERE l.snapshot_id=? ORDER BY l.line_ordinal",
                    (str(row[0]),),
                ).fetchall()
                if len(line_rows) != len(snapshot.lines):
                    raise DOIPersistenceIntegrityError(
                        "DOI_LINE_PROOF_CHILD_MISMATCH"
                    )
                for stored, line in zip(line_rows, snapshot.lines, strict=True):
                    decoded_line = decode_payload(
                        _stored_bytes(stored[4]),
                        DOILineItemSnapshot,
                    )
                    continuity = decode_payload(
                        _stored_bytes(stored[8]),
                        LineContinuityProof,
                    )
                    _verify_binding(stored, 1, decoded_line)
                    _verify_binding(stored, 5, continuity)
                    if (
                        stored[0] != line.line_snapshot_id.to_json_value()
                        or decoded_line != line
                        or continuity != line.continuity
                    ):
                        raise DOIPersistenceIntegrityError(
                            "DOI_LINE_PROOF_CHILD_MISMATCH"
                        )
            except (DOIPersistenceError, TypeError, ValueError):
                return ("DOI_SNAPSHOT_PROOF_CHILD_MISMATCH",)
        return ()

    def _verify_evaluation_children(self) -> tuple[str, ...]:
        rows = self.connection.execute(
            "SELECT e.evaluation_id, a.record_domain, a.record_sha256, "
            "a.record_canonical_bytes, a.record_payload FROM doi_evaluations e "
            "JOIN doi_case_artifacts a ON a.artifact_pk=e.record_artifact_pk "
            "ORDER BY e.evaluation_id"
        ).fetchall()
        for row in rows:
            try:
                evaluation = decode_payload(_stored_bytes(row[4]), DOIEvaluation)
                _verify_binding(row, 1, evaluation)
                reasons = self.connection.execute(
                    "SELECT reason_code, owning_transition_id, effective_overlay, "
                    "ordinal FROM doi_evaluation_reasons WHERE evaluation_id=? "
                    "ORDER BY ordinal",
                    (str(row[0]),),
                ).fetchall()
                expected_reasons = tuple(
                    (
                        route.reason.code,
                        None
                        if route.owning_transition is None
                        else route.owning_transition.transition_id,
                        int(route.effective_overlay),
                        ordinal,
                    )
                    for ordinal, route in enumerate(
                        evaluation.reason_routes,
                        start=1,
                    )
                )
                if tuple(tuple(item) for item in reasons) != expected_reasons:
                    raise DOIPersistenceIntegrityError(
                        "DOI_EVALUATION_REASON_CHILD_MISMATCH"
                    )
                opportunity_rows = self.connection.execute(
                    "SELECT o.opportunity_id, a.record_domain, a.record_sha256, "
                    "a.record_canonical_bytes, a.record_payload "
                    "FROM doi_opportunities o JOIN doi_case_artifacts a "
                    "ON a.artifact_pk=o.record_artifact_pk "
                    "WHERE o.evaluation_id=? ORDER BY o.opportunity_id",
                    (str(row[0]),),
                ).fetchall()
                expected_opportunities = tuple(
                    sorted(
                        evaluation.opportunities,
                        key=lambda item: item.opportunity_id.value,
                    )
                )
                if len(opportunity_rows) != len(expected_opportunities):
                    raise DOIPersistenceIntegrityError(
                        "DOI_OPPORTUNITY_CHILD_MISMATCH"
                    )
                for stored, opportunity in zip(
                    opportunity_rows,
                    expected_opportunities,
                    strict=True,
                ):
                    decoded = decode_payload(
                        _stored_bytes(stored[4]),
                        DOIOpportunity,
                    )
                    _verify_binding(stored, 1, decoded)
                    scopes = self.connection.execute(
                        "SELECT line_snapshot_id, role, quantity_text, ordinal "
                        "FROM doi_opportunity_scope_components "
                        "WHERE opportunity_id=? ORDER BY ordinal",
                        (opportunity.opportunity_id.value,),
                    ).fetchall()
                    expected_scopes = tuple(
                        (
                            component.line_snapshot_id.to_json_value(),
                            component.role.value,
                            component.quantity.to_json_value(),
                            ordinal,
                        )
                        for ordinal, component in enumerate(
                            opportunity.scope.components,
                            start=1,
                        )
                    )
                    if (
                        decoded != opportunity
                        or tuple(tuple(item) for item in scopes) != expected_scopes
                    ):
                        raise DOIPersistenceIntegrityError(
                            "DOI_OPPORTUNITY_CHILD_MISMATCH"
                        )
            except (DOIPersistenceError, TypeError, ValueError):
                return ("DOI_EVALUATION_NORMALIZED_CHILD_MISMATCH",)
        return ()

    def _verify_result_children(self) -> tuple[str, ...]:
        searches = self.connection.execute(
            "SELECT search_id, case_id, parent_order_id, intervention_type, state, "
            "revision, head_sha256, projection_payload "
            "FROM doi_resulting_order_searches ORDER BY search_id"
        ).fetchall()
        for row in searches:
            try:
                projection = decode_payload(
                    _stored_bytes(row[7]),
                    DOIResultingOrderLinkSearch,
                )
                events = self.connection.execute(
                    "SELECT sequence_no, predecessor_sha256, record_sha256, "
                    "record_domain, record_canonical_bytes, record_payload "
                    "FROM doi_resulting_order_search_events "
                    "WHERE search_id=? ORDER BY sequence_no",
                    (str(row[0]),),
                ).fetchall()
                predecessor = None
                for sequence, event_row in enumerate(events, start=1):
                    event = decode_payload(
                        _stored_bytes(event_row[5]),
                        ResultingLinkSearchEvent,
                    )
                    _verify_binding(event_row, 3, event)
                    if (
                        int(event_row[0]) != sequence
                        or event.sequence != sequence
                        or event_row[1] != predecessor
                    ):
                        raise DOIPersistenceIntegrityError(
                            "DOI_RESULTING_SEARCH_CHILD_MISMATCH"
                        )
                    predecessor = str(event_row[2])
                case_order = self.connection.execute(
                    "SELECT order_id FROM doi_cases WHERE case_id=?",
                    (str(row[1]),),
                ).fetchone()
                if (
                    projection.search_id.value != row[0]
                    or projection.parent_order_id.to_json_value() != row[2]
                    or projection.intervention_type.value != row[3]
                    or projection.state.value != row[4]
                    or len(events) != int(row[5])
                    or projection.revision != int(row[5])
                    or projection.head_event_binding.sha256 != row[6]
                    or predecessor != row[6]
                    or case_order is None
                    or str(case_order[0]) != str(row[2])
                ):
                    raise DOIPersistenceIntegrityError(
                        "DOI_RESULTING_SEARCH_CHILD_MISMATCH"
                    )
            except (DOIPersistenceError, TypeError, ValueError):
                return ("DOI_RESULTING_SEARCH_CHILD_MISMATCH",)
        links = self.connection.execute(
            "SELECT link_id, case_id, intervention_id, parent_order_id, "
            "child_order_id, state, current_revision, head_sha256, projection_payload "
            "FROM doi_resulting_order_links ORDER BY link_id"
        ).fetchall()
        for row in links:
            try:
                link = decode_payload(_stored_bytes(row[8]), DOIResultingOrderLink)
                revisions = self.connection.execute(
                    "SELECT revision_no, record_sha256 FROM "
                    "doi_resulting_order_link_revisions WHERE link_id=? "
                    "ORDER BY revision_no",
                    (str(row[0]),),
                ).fetchall()
                if len(revisions) != len(link.revisions):
                    raise DOIPersistenceIntegrityError(
                        "DOI_RESULTING_LINK_CHILD_MISMATCH"
                    )
                for stored, revision in zip(
                    revisions,
                    link.revisions,
                    strict=True,
                ):
                    mappings = self.connection.execute(
                        "SELECT parent_line_id, child_line_id, quantity_text, ordinal "
                        "FROM doi_resulting_order_mapping_components "
                        "WHERE link_id=? AND revision_no=? ORDER BY ordinal",
                        (str(row[0]), revision.revision),
                    ).fetchall()
                    expected = tuple(
                        (
                            component.parent_line_id.to_json_value(),
                            component.child_line_id.to_json_value(),
                            component.quantity.to_json_value(),
                            ordinal,
                        )
                        for ordinal, component in enumerate(
                            revision.mappings,
                            start=1,
                        )
                    )
                    if (
                        int(stored[0]) != revision.revision
                        or str(stored[1]) != revision.hash_binding().sha256
                        or tuple(tuple(item) for item in mappings) != expected
                    ):
                        raise DOIPersistenceIntegrityError(
                            "DOI_RESULTING_LINK_CHILD_MISMATCH"
                        )
                if (
                    link.link_id.value != row[0]
                    or link.intervention_id.value != row[2]
                    or link.parent_order_id.to_json_value() != row[3]
                    or link.child_order_id.to_json_value() != row[4]
                    or link.state.value != row[5]
                    or int(row[6]) != len(link.revisions)
                    or str(row[7]) != link.revisions[-1].hash_binding().sha256
                ):
                    raise DOIPersistenceIntegrityError(
                        "DOI_RESULTING_LINK_CHILD_MISMATCH"
                    )
            except (DOIPersistenceError, TypeError, ValueError):
                return ("DOI_RESULTING_LINK_CHILD_MISMATCH",)
        try:
            search_artifacts = self.connection.execute(
                "SELECT record_domain, record_sha256, record_canonical_bytes, "
                "record_payload FROM doi_case_artifacts "
                "WHERE artifact_kind='RESULTING_SEARCH'"
            ).fetchall()
            search_ids: set[str] = set()
            for artifact in search_artifacts:
                projection = decode_payload(
                    _stored_bytes(artifact[3]),
                    DOIResultingOrderLinkSearch,
                )
                _verify_binding(artifact, 0, projection)
                search_ids.add(projection.search_id.value)
            link_artifacts = self.connection.execute(
                "SELECT record_domain, record_sha256, record_canonical_bytes, "
                "record_payload FROM doi_case_artifacts "
                "WHERE artifact_kind='RESULTING_LINK'"
            ).fetchall()
            link_ids: set[str] = set()
            for artifact in link_artifacts:
                link = decode_payload(
                    _stored_bytes(artifact[3]),
                    DOIResultingOrderLink,
                )
                _verify_binding(artifact, 0, link)
                link_ids.add(link.link_id.value)
            if search_ids != {str(row[0]) for row in searches}:
                raise DOIPersistenceIntegrityError(
                    "DOI_RESULTING_SEARCH_PROJECTION_MISSING"
                )
            if link_ids != {str(row[0]) for row in links}:
                raise DOIPersistenceIntegrityError(
                    "DOI_RESULTING_LINK_PROJECTION_MISSING"
                )
        except (DOIPersistenceError, TypeError, ValueError):
            return ("DOI_RESULTING_PROJECTION_COMPLETENESS_MISMATCH",)
        return ()

    def _verify_product_children(self) -> tuple[str, ...]:
        relationships = self.connection.execute(
            "SELECT relationship_id, relationship_type, ordered_sku, candidate_sku, "
            "current_revision, current_state, head_sha256 "
            "FROM doi_product_relationships ORDER BY relationship_id"
        ).fetchall()
        try:
            for row in relationships:
                revisions = self.connection.execute(
                    "SELECT revision_no, revision_id, predecessor_sha256, "
                    "record_domain, record_sha256, record_canonical_bytes, "
                    "record_payload FROM doi_product_relationship_revisions "
                    "WHERE relationship_id=? ORDER BY revision_no",
                    (str(row[0]),),
                ).fetchall()
                predecessor = None
                state = None
                for sequence, stored in enumerate(revisions, start=1):
                    revision = decode_payload(
                        _stored_bytes(stored[6]),
                        DOIAlternateRelationshipRevision,
                    )
                    _verify_binding(stored, 3, revision)
                    if (
                        int(stored[0]) != sequence
                        or str(stored[1]) != revision.revision_id.value
                        or stored[2] != predecessor
                        or revision.relationship_id.value != row[0]
                        or revision.relationship_type.value != row[1]
                        or revision.ordered_sku.value != row[2]
                        or revision.candidate_sku.value != row[3]
                    ):
                        raise DOIPersistenceIntegrityError(
                            "DOI_RELATIONSHIP_REVISION_CHILD_MISMATCH"
                        )
                    predecessor = revision.hash_binding().sha256
                    state = revision.state.value
                if (
                    not revisions
                    or len(revisions) != int(row[4])
                    or state != row[5]
                    or predecessor != row[6]
                ):
                    raise DOIPersistenceIntegrityError(
                        "DOI_RELATIONSHIP_PROJECTION_MISMATCH"
                    )
            observations = self.connection.execute(
                "SELECT observation_id, relationship_id, case_id, "
                "action_context_id, observed_at, record_domain, record_sha256, "
                "record_canonical_bytes, record_payload "
                "FROM doi_product_observations ORDER BY observation_id"
            ).fetchall()
            for row in observations:
                payload = _stored_bytes(row[8])
                try:
                    observation: DOIAlternateObservation | DOIExactSKUObservation = (
                        decode_payload(payload, DOIAlternateObservation)
                    )
                except DOIPersistenceIntegrityError:
                    observation = decode_payload(payload, DOIExactSKUObservation)
                _verify_binding(row, 5, observation)
                if (
                    observation.observation_id.value != row[0]
                    or observation.action_context_id.value != row[3]
                    or observation.observed_at.value != row[4]
                ):
                    raise DOIPersistenceIntegrityError(
                        "DOI_PRODUCT_OBSERVATION_CHILD_MISMATCH"
                    )
        except (DOIPersistenceError, TypeError, ValueError):
            return ("DOI_PRODUCT_KNOWLEDGE_PROJECTION_MISMATCH",)
        return ()

    def _verify_projection_completeness(self) -> tuple[str, ...]:
        run_ids = {
            str(row[0])
            for row in self.connection.execute("SELECT run_id FROM doi_runs")
        }
        run_projection_ids = {
            str(row[0])
            for row in self.connection.execute(
                "SELECT run_id FROM doi_run_projections"
            )
        }
        if run_ids != run_projection_ids:
            return ("DOI_RUN_PROJECTION_COMPLETENESS_MISMATCH",)
        evaluated_case_ids = {
            str(row[0])
            for row in self.connection.execute(
                "SELECT DISTINCT case_id FROM doi_evaluations"
            )
        }
        case_projection_ids = {
            str(row[0])
            for row in self.connection.execute(
                "SELECT case_id FROM doi_case_projections"
            )
        }
        if evaluated_case_ids != case_projection_ids:
            return ("DOI_CASE_PROJECTION_COMPLETENESS_MISMATCH",)
        anchor_ids = {
            (str(row[0]), str(row[1]))
            for row in self.connection.execute(
                "SELECT stream_family, stream_id FROM doi_owner_stream_anchors"
            )
        }
        stream_ids = {
            (str(row[0]), str(row[1]))
            for row in self.connection.execute(
                "SELECT stream_family, stream_id FROM doi_owner_streams"
            )
        }
        if anchor_ids != stream_ids:
            return ("DOI_OWNER_PROJECTION_COMPLETENESS_MISMATCH",)
        try:
            extraction_artifacts = self.connection.execute(
                "SELECT record_domain, record_sha256, record_canonical_bytes, "
                "record_payload FROM doi_case_artifacts "
                "WHERE artifact_kind='EXTRACTION_ATTEMPT'"
            ).fetchall()
            extraction_ids: set[str] = set()
            for artifact in extraction_artifacts:
                attempt = decode_payload(
                    _stored_bytes(artifact[3]),
                    DOIExtractionAttempt,
                )
                _verify_binding(artifact, 0, attempt)
                extraction_ids.add(attempt.attempt_id.to_json_value())
            retained_extraction_ids = {
                str(row[0])
                for row in self.connection.execute(
                    "SELECT attempt_id FROM doi_extraction_attempts"
                )
            }
            if extraction_ids != retained_extraction_ids:
                raise DOIPersistenceIntegrityError(
                    "DOI_EXTRACTION_PROJECTION_COMPLETENESS_MISMATCH"
                )
            intervention_artifacts = self.connection.execute(
                "SELECT record_domain, record_sha256, record_canonical_bytes, "
                "record_payload FROM doi_case_artifacts "
                "WHERE artifact_kind='INTERVENTION'"
            ).fetchall()
            intervention_ids: set[str] = set()
            for artifact in intervention_artifacts:
                intervention = decode_payload(
                    _stored_bytes(artifact[3]),
                    DOIIntervention,
                )
                _verify_binding(artifact, 0, intervention)
                intervention_ids.add(intervention.intervention_id.value)
            retained_intervention_ids = {
                str(row[0])
                for row in self.connection.execute(
                    "SELECT intervention_id FROM doi_interventions"
                )
            }
            if intervention_ids != retained_intervention_ids:
                raise DOIPersistenceIntegrityError(
                    "DOI_INTERVENTION_PROJECTION_COMPLETENESS_MISMATCH"
                )
            kpi_artifacts = self.connection.execute(
                "SELECT record_domain, record_sha256, record_canonical_bytes, "
                "record_payload FROM doi_case_artifacts "
                "WHERE artifact_kind='KPI_CONTRIBUTION'"
            ).fetchall()
            kpi_ids: set[str] = set()
            for artifact in kpi_artifacts:
                contribution = decode_payload(
                    _stored_bytes(artifact[3]),
                    RetainedKPIContribution,
                )
                _verify_binding(artifact, 0, contribution)
                kpi_ids.add(contribution.intervention_id.value)
            retained_kpi_ids = {
                str(row[0])
                for row in self.connection.execute(
                    "SELECT intervention_id FROM doi_retained_kpi_contributions"
                )
            }
            if kpi_ids != retained_kpi_ids:
                raise DOIPersistenceIntegrityError(
                    "DOI_KPI_PROJECTION_COMPLETENESS_MISMATCH"
                )
        except (DOIPersistenceError, TypeError, ValueError):
            return ("DOI_ARTIFACT_PROJECTION_COMPLETENESS_MISMATCH",)
        return ()

    def verify_projections(self) -> ProjectionVerification:
        errors: list[str] = []
        run_rows = self.connection.execute(
            "SELECT run_id, status, projection_version, head_sha256, material_version, "
            "material_event_sha256, source_batch_id, completed_at, purge_eligible_at, "
            "source_attempt_count, work_item_count, "
            "disposition_subject_count, successful_evaluation_count, "
            "order_exception_count, blocked_order_count, portal_read_count, "
            "record_domain, record_sha256, record_canonical_bytes, record_payload "
            "FROM doi_run_projections ORDER BY run_id"
        ).fetchall()
        for row in run_rows:
            try:
                run = decode_payload(_stored_bytes(row[19]), DOIRun)
                _verify_binding(row, 16, run)
                source_batch_id = (
                    None
                    if run.source_batch_id is None
                    else _text_id(run.source_batch_id)
                )
                projected = (
                    run.run_id.value,
                    run.status.value,
                    source_batch_id,
                    None if run.completed_at is None else run.completed_at.value,
                    None
                    if run.purge_eligible_at is None
                    else run.purge_eligible_at.value,
                    run.counts.source_attempt_count.value,
                    run.counts.work_item_count.value,
                    run.counts.disposition_subject_count.value,
                    run.counts.successful_evaluation_count.value,
                    run.counts.order_exception_count.value,
                    run.counts.blocked_order_count.value,
                    run.counts.portal_read_count.value,
                )
                stored = (
                    str(row[0]),
                    str(row[1]),
                    row[6],
                    row[7],
                    row[8],
                    *tuple(int(row[index]) for index in range(9, 16)),
                )
                if projected != stored:
                    raise DOIPersistenceIntegrityError(
                        "DOI_RUN_PROJECTION_RECORD_MISMATCH"
                    )
                events = self.connection.execute(
                    "SELECT sequence_no, predecessor_sha256, record_sha256, "
                    "record_payload FROM doi_run_events WHERE run_id=? "
                    "ORDER BY sequence_no",
                    (str(row[0]),),
                ).fetchall()
                if len(events) != int(row[2]):
                    raise DOIPersistenceIntegrityError(
                        "DOI_RUN_PROJECTION_VERSION_MISMATCH"
                    )
                predecessor = None
                for sequence, event_row in enumerate(events, start=1):
                    event = decode_payload(_stored_bytes(event_row[3]), DOIRunEvent)
                    if (
                        int(event_row[0]) != sequence
                        or event.sequence.value != sequence
                        or event.run_id.value != row[0]
                        or event_row[1] != predecessor
                    ):
                        raise DOIPersistenceIntegrityError(
                            "DOI_RUN_EVENT_HISTORY_MISMATCH"
                        )
                    predecessor = str(event_row[2])
                if not events or str(row[3]) != predecessor:
                    raise DOIPersistenceIntegrityError(
                        "DOI_RUN_PROJECTION_HEAD_MISMATCH"
                    )
                material_event = self.connection.execute(
                    "SELECT 1 FROM doi_run_events WHERE run_id=? AND record_sha256=? "
                    "UNION ALL SELECT 1 FROM doi_source_import_attempt_events e "
                    "JOIN doi_source_import_attempts a ON a.attempt_id=e.attempt_id "
                    "WHERE a.run_id=? AND e.record_sha256=? LIMIT 1",
                    (str(row[0]), str(row[5]), str(row[0]), str(row[5])),
                ).fetchone()
                if int(row[4]) < int(row[2]) or material_event is None:
                    raise DOIPersistenceIntegrityError(
                        "DOI_RUN_MATERIAL_EVENT_MISMATCH"
                    )
                material_rows = self.connection.execute(
                    "SELECT material_version, cause_sha256, record_sha256 "
                    "FROM doi_run_material_events WHERE run_id=? "
                    "ORDER BY material_version",
                    (str(row[0]),),
                ).fetchall()
                if (
                    len(material_rows) != int(row[4])
                    or any(
                        int(item[0]) != version
                        for version, item in enumerate(material_rows, start=1)
                    )
                    or not material_rows
                    or str(material_rows[-1][1]) != str(row[5])
                    or str(material_rows[-1][2]) != str(row[17])
                ):
                    raise DOIPersistenceIntegrityError(
                        "DOI_RUN_MATERIAL_HISTORY_MISMATCH"
                    )
            except DOIPersistenceError as exc:
                errors.append(str(exc))
        case_rows = self.connection.execute(
            "SELECT p.case_id, c.order_id, p.lifecycle_state, p.current_snapshot_id, "
            "p.current_evaluation_id, p.terminal_closure_reason, p.projection_version, "
            "p.head_sha256, p.record_payload, a.record_sha256 FROM doi_case_projections p "
            "JOIN doi_cases c ON c.case_id=p.case_id LEFT JOIN doi_evaluations e "
            "ON e.evaluation_id=p.current_evaluation_id LEFT JOIN doi_case_artifacts a "
            "ON a.artifact_pk=e.record_artifact_pk ORDER BY p.case_id"
        ).fetchall()
        for row in case_rows:
            try:
                case = decode_payload(_stored_bytes(row[8]), DOIOrderCase)
                evaluation_count = int(
                    self.connection.execute(
                        "SELECT COUNT(*) FROM doi_evaluations WHERE case_id=?",
                        (str(row[0]),),
                    ).fetchone()[0]
                )
                if (
                    case.case_id.value != row[0]
                    or case.order_id.to_json_value() != row[1]
                    or case.lifecycle_state.value != row[2]
                    or case.current_snapshot_id is None
                    or case.current_snapshot_id.to_json_value() != row[3]
                    or case.current_evaluation_id is None
                    or case.current_evaluation_id.value != row[4]
                    or (
                        None
                        if case.terminal_closure_reason is None
                        else case.terminal_closure_reason.value
                    )
                    != row[5]
                    or evaluation_count != int(row[6])
                    or row[9] is None
                    or str(row[7]) != str(row[9])
                ):
                    raise DOIPersistenceIntegrityError("DOI_CASE_PROJECTION_MISMATCH")
            except DOIPersistenceError as exc:
                errors.append(str(exc))
        owner_rows = self.connection.execute(
            "SELECT s.stream_family, s.stream_id, s.current_state, s.sequence_no, "
            "s.head_sha256, s.projection_payload, e.projection_state, "
            "e.record_domain, e.record_sha256, e.record_canonical_bytes, "
            "e.record_payload "
            "FROM doi_owner_streams s LEFT JOIN doi_owner_events e "
            "ON e.stream_family=s.stream_family AND e.stream_id=s.stream_id "
            "AND e.sequence_no=s.sequence_no ORDER BY s.stream_family, s.stream_id"
        ).fetchall()
        for row in owner_rows:
            if int(row[3]) == 0:
                if row[4] is not None or row[8] is not None:
                    errors.append("DOI_OWNER_EMPTY_PROJECTION_MISMATCH")
                continue
            history = self.connection.execute(
                "SELECT sequence_no, projection_state, predecessor_sha256, "
                "record_domain, record_sha256, record_canonical_bytes, record_payload "
                "FROM doi_owner_events WHERE stream_family=? AND stream_id=? "
                "ORDER BY sequence_no",
                (str(row[0]), str(row[1])),
            ).fetchall()
            predecessor = None
            valid = len(history) == int(row[3])
            for sequence, event_row in enumerate(history, start=1):
                canonical = _stored_bytes(event_row[5])
                try:
                    envelope = json.loads(canonical.decode("utf-8"))
                except (UnicodeError, ValueError):
                    valid = False
                    envelope = {}
                valid = valid and (
                    int(event_row[0]) == sequence
                    and event_row[2] == predecessor
                    and str(event_row[3]) == "doi-owner-event-envelope/v1"
                    and domain_hash(str(event_row[3]), canonical).sha256
                    == str(event_row[4])
                    and _stored_bytes(event_row[6]) == canonical
                    and envelope.get("stream_family") == row[0]
                    and envelope.get("stream_id") == row[1]
                    and envelope.get("projected_state") == event_row[1]
                )
                predecessor = str(event_row[4])
            if (
                not valid
                or row[8] is None
                or str(row[4]) != predecessor
                or str(row[2]) != str(row[6])
                or _stored_bytes(row[5]) != _stored_bytes(row[10])
            ):
                family = str(row[0])
                errors.append(f"DOI_{family}_PROJECTION_HISTORY_MISMATCH")
        intervention_rows = self.connection.execute(
            "SELECT i.intervention_id, i.case_id, i.opportunity_id, "
            "i.intervention_type, i.status, i.action_occurred_at, a.record_domain, "
            "a.record_sha256, a.record_canonical_bytes, a.record_payload, "
            "i.projection_version, i.head_sha256 "
            "FROM doi_interventions i JOIN doi_case_artifacts a "
            "ON a.artifact_pk=i.record_artifact_pk ORDER BY i.intervention_id"
        ).fetchall()
        for row in intervention_rows:
            try:
                intervention = decode_payload(_stored_bytes(row[9]), DOIIntervention)
                _verify_binding(row, 6, intervention)
                stored_projection = (
                    str(row[0]),
                    str(row[2]),
                    str(row[3]),
                    str(row[4]),
                    row[5],
                )
                expected_projection = (
                    intervention.intervention_id.value,
                    intervention.opportunity_id.value,
                    intervention.intervention_type.value,
                    intervention.status.value,
                    None
                    if intervention.action_occurred_at is None
                    else intervention.action_occurred_at.value,
                )
                projection_events = (
                    *intervention.action_events,
                    *intervention.value_events,
                )
                expected_version = max(1, len(projection_events))
                expected_head = (
                    intervention.hash_binding().sha256
                    if not projection_events
                    else projection_events[-1].hash_binding().sha256
                )
                action_rows = self.connection.execute(
                    "SELECT event_id, record_sha256, record_payload "
                    "FROM doi_action_verification_events WHERE intervention_id=? "
                    "ORDER BY event_id",
                    (intervention.intervention_id.value,),
                ).fetchall()
                value_rows = self.connection.execute(
                    "SELECT sequence_no, event_id, predecessor_sha256, record_sha256, "
                    "record_payload FROM doi_value_events WHERE intervention_id=? "
                    "ORDER BY sequence_no",
                    (intervention.intervention_id.value,),
                ).fetchall()
                actions = tuple(
                    sorted(
                        intervention.action_events,
                        key=lambda item: item.event_id.value,
                    )
                )
                action_valid = len(action_rows) == len(actions) and all(
                    str(stored[0]) == event.event_id.value
                    and str(stored[1]) == event.hash_binding().sha256
                    and _stored_bytes(stored[2]) == encode_payload(event)
                    for stored, event in zip(action_rows, actions, strict=True)
                )
                value_valid = len(value_rows) == len(intervention.value_events) and all(
                    int(stored[0]) == sequence
                    and str(stored[1]) == event.event_id.value
                    and stored[2]
                    == (
                        None
                        if event.predecessor_event_binding is None
                        else event.predecessor_event_binding.sha256
                    )
                    and str(stored[3]) == event.hash_binding().sha256
                    and _stored_bytes(stored[4]) == encode_payload(event)
                    for sequence, (stored, event) in enumerate(
                        zip(value_rows, intervention.value_events, strict=True),
                        start=1,
                    )
                )
                if (
                    stored_projection != expected_projection
                    or int(row[10]) != expected_version
                    or str(row[11]) != expected_head
                    or not action_valid
                    or not value_valid
                ):
                    raise DOIPersistenceIntegrityError(
                        "DOI_INTERVENTION_VALUE_PROJECTION_MISMATCH"
                    )
            except DOIPersistenceError as exc:
                errors.append(str(exc))
        kpi_rows = self.connection.execute(
            "SELECT k.intervention_id, k.case_id, k.intervention_type, "
            "k.action_date, k.amount_minor_units, k.currency_code, "
            "k.currency_registry_version, k.currency_scale, k.revision, "
            "k.head_sha256, k.record_payload, e.record_sha256 "
            "FROM doi_retained_kpi_contributions k "
            "LEFT JOIN doi_kpi_contribution_events e "
            "ON e.intervention_id=k.intervention_id AND e.sequence_no=k.revision "
            "ORDER BY k.intervention_id"
        ).fetchall()
        for row in kpi_rows:
            try:
                contribution = decode_payload(
                    _stored_bytes(row[10]),
                    RetainedKPIContribution,
                )
                event_count = int(
                    self.connection.execute(
                        "SELECT COUNT(*) FROM doi_kpi_contribution_events "
                        "WHERE intervention_id=?",
                        (str(row[0]),),
                    ).fetchone()[0]
                )
                intervention_case = self.connection.execute(
                    "SELECT case_id FROM doi_interventions WHERE intervention_id=?",
                    (str(row[0]),),
                ).fetchone()
                if (
                    contribution.intervention_id.value != row[0]
                    or contribution.intervention_type.value != row[2]
                    or intervention_case is None
                    or str(intervention_case[0]) != row[1]
                    or contribution.action_date.isoformat() != row[3]
                    or contribution.current_value.minor_units != int(row[4])
                    or contribution.current_value.currency_code != row[5]
                    or contribution.current_value.registry_version != row[6]
                    or contribution.current_value.scale != int(row[7])
                    or contribution.revision != int(row[8])
                    or contribution.head_event_binding.sha256 != row[9]
                    or event_count != int(row[8])
                    or row[11] is None
                    or str(row[9]) != str(row[11])
                ):
                    raise DOIPersistenceIntegrityError(
                        "DOI_KPI_PROJECTION_MISMATCH"
                    )
            except DOIPersistenceError as exc:
                errors.append(str(exc))
        errors.extend(self._verify_normalized_source_children())
        errors.extend(self._verify_case_source_and_proof_children())
        errors.extend(self._verify_snapshot_proof_children())
        errors.extend(self._verify_evaluation_children())
        errors.extend(self._verify_product_children())
        errors.extend(self._verify_result_children())
        errors.extend(self._verify_projection_completeness())
        return ProjectionVerification(
            len(run_rows),
            len(case_rows),
            len(owner_rows),
            len(intervention_rows),
            tuple(sorted(errors)),
        )

    def purge_case(
        self,
        case_id: EvidenceId,
        *,
        now: CanonicalTimestamp,
        fault_injector: FaultInjector | None = None,
    ) -> PurgeResult:
        if type(case_id) is not EvidenceId or type(now) is not CanonicalTimestamp:
            raise DOIPersistenceError("DOI_PURGE_CASE_INVALID")
        injector = FaultInjector() if fault_injector is None else fault_injector
        case_key = case_id.value
        if (
            self.connection.execute(
                "SELECT 1 FROM doi_cases WHERE case_id=?", (case_key,)
            ).fetchone()
            is None
        ):
            return PurgeResult(False, 0, 0)
        deadline_row = self.connection.execute(
            "SELECT purge_eligible_at FROM doi_retention_deadlines "
            "WHERE case_id=? AND canceled_by_reopen_event_id IS NULL",
            (case_key,),
        ).fetchone()
        if deadline_row is None:
            raise DOIPersistenceError("DOI_PURGE_ACTIVE_DEADLINE_REQUIRED")
        deadline = CanonicalTimestamp.from_sqlite_text(deadline_row[0])
        if (now.epoch_seconds, now.nanosecond) < (
            deadline.epoch_seconds,
            deadline.nanosecond,
        ):
            raise DOIPersistenceError("DOI_PURGE_NOT_ELIGIBLE")
        run_rows = self.connection.execute(
            "SELECT DISTINCT run_id FROM doi_order_snapshots WHERE case_id=? ORDER BY run_id",
            (case_key,),
        ).fetchall()
        contributions = self.connection.execute(
            "SELECT action_date, intervention_type, currency_code, "
            "currency_registry_version, currency_scale, amount_minor_units "
            "FROM doi_retained_kpi_contributions WHERE case_id=? ORDER BY intervention_id",
            (case_key,),
        ).fetchall()
        for row in contributions:
            self.connection.execute(
                "INSERT INTO doi_kpi_daily_buckets"
                "(action_date, intervention_type, currency_code, currency_registry_version, "
                "currency_scale, amount_minor_units, intervention_count) "
                "VALUES (?, ?, ?, ?, ?, ?, 1) "
                "ON CONFLICT(action_date, intervention_type, currency_code, "
                "currency_registry_version, currency_scale) DO UPDATE SET "
                "amount_minor_units=amount_minor_units+excluded.amount_minor_units, "
                "intervention_count=intervention_count+1",
                tuple(row),
            )
        injector.hit(FaultPoint.DURING_KPI_FINALIZATION)
        injector.hit(FaultPoint.DURING_CASE_PURGE)
        receipt_rows = self.connection.execute(
            "SELECT command_id FROM durable_receipt_owners "
            "WHERE owner_domain='DOI' AND owner_id=? ORDER BY command_id",
            (case_key,),
        ).fetchall()
        self.connection.execute("DELETE FROM doi_cases WHERE case_id=?", (case_key,))
        deleted_runs = 0
        for row in run_rows:
            run_id = str(row[0])
            remaining = self.connection.execute(
                "SELECT 1 FROM doi_order_snapshots WHERE run_id=? LIMIT 1", (run_id,)
            ).fetchone()
            if remaining is None:
                deleted_runs += self.connection.execute(
                    "DELETE FROM doi_runs WHERE run_id=?", (run_id,)
                ).rowcount
        for receipt_row in receipt_rows:
            self.connection.execute(
                "DELETE FROM durable_commands WHERE command_id=?",
                (str(receipt_row[0]),),
            )
        return PurgeResult(True, len(contributions), deleted_runs)

    def purge_terminal_run(
        self,
        run_id: str,
        *,
        now: CanonicalTimestamp,
        fault_injector: FaultInjector | None = None,
    ) -> PersistenceResult:
        """Delete one eligible terminal run identity graph without a tombstone."""

        if type(run_id) is not str or not run_id or type(now) is not CanonicalTimestamp:
            raise DOIPersistenceError("DOI_RUN_PURGE_INVALID")
        retained = self.connection.execute(
            "SELECT status, purge_eligible_at, source_batch_id "
            "FROM doi_run_projections WHERE run_id=?",
            (run_id,),
        ).fetchone()
        if retained is None:
            return PersistenceResult(True)
        if str(retained[0]) == RunStatus.IN_PROGRESS.value or retained[1] is None:
            raise DOIPersistenceConflict("DOI_RUN_PURGE_NOT_TERMINAL")
        deadline = CanonicalTimestamp.from_sqlite_text(retained[1])
        if (now.epoch_seconds, now.nanosecond) < (
            deadline.epoch_seconds,
            deadline.nanosecond,
        ):
            raise DOIPersistenceConflict("DOI_RUN_PURGE_NOT_ELIGIBLE")
        if self.connection.execute(
            "SELECT 1 FROM doi_order_snapshots WHERE run_id=? LIMIT 1",
            (run_id,),
        ).fetchone() is not None:
            raise DOIPersistenceConflict("DOI_RUN_PURGE_LIVE_CASE_REFERENCE")
        batch_rows = self.connection.execute(
            "SELECT batch_id FROM doi_attempt_batch_references r "
            "JOIN doi_source_import_attempts a ON a.attempt_id=r.attempt_id "
            "WHERE a.run_id=? UNION SELECT source_batch_id "
            "FROM doi_run_projections WHERE run_id=? AND source_batch_id IS NOT NULL",
            (run_id, run_id),
        ).fetchall()
        injector = FaultInjector() if fault_injector is None else fault_injector
        injector.hit(FaultPoint.DURING_CASE_PURGE)
        self.connection.execute("DELETE FROM doi_runs WHERE run_id=?", (run_id,))
        for row in batch_rows:
            batch_id = str(row[0])
            references = self.connection.execute(
                "SELECT 1 FROM doi_attempt_batch_references WHERE batch_id=? "
                "UNION SELECT 1 FROM doi_case_source_batch_references WHERE batch_id=? "
                "UNION SELECT 1 FROM doi_run_projections WHERE source_batch_id=? LIMIT 1",
                (batch_id, batch_id, batch_id),
            ).fetchone()
            if references is None:
                self.connection.execute(
                    "DELETE FROM doi_source_batches WHERE batch_id=?",
                    (batch_id,),
                )
        return PersistenceResult(False)

    def identity_occurrences(self, value: str) -> int:
        if type(value) is not str or not value:
            raise DOIPersistenceError("DOI_IDENTITY_SCAN_INVALID")
        count = 0
        tables = self.connection.execute(
            "SELECT name FROM sqlite_schema WHERE type='table' "
            "AND (name LIKE 'doi_%' OR name LIKE 'durable_%') ORDER BY name"
        ).fetchall()
        needle = value.encode("utf-8")
        for table_row in tables:
            table = str(table_row[0])
            columns = self.connection.execute(f'PRAGMA table_info("{table}")').fetchall()
            for column in columns:
                name = str(column[1])
                rows = self.connection.execute(
                    f'SELECT "{name}" FROM "{table}" WHERE "{name}" IS NOT NULL'
                ).fetchall()
                for row in rows:
                    stored = row[0]
                    if type(stored) is str and value in stored:
                        count += 1
                    elif isinstance(stored, (bytes, memoryview)) and needle in bytes(stored):
                        count += 1
        return count


__all__ = [
    "DOIInterventionHistoryRecord",
    "DOIOwnerEventRecord",
    "DOIPersistenceConflict",
    "DOIPersistenceError",
    "DOIPersistenceIntegrityError",
    "DOIRepository",
    "PersistenceResult",
    "ProjectionVerification",
    "PurgeResult",
    "decode_payload",
    "encode_payload",
]
