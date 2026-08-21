"""Typed durable Sales Credit repository over one caller-owned SQLite UoW."""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone

from synthetic_sales_assist.domain.canonical import (
    canonical_json_bytes,
    domain_hash,
    parse_canonical_json_bytes,
)
from synthetic_sales_assist.domain.identities import (
    EvidenceId,
    EvaluationId,
    OrderId,
    RepId,
    SnapshotId,
)
from synthetic_sales_assist.domain.numeric import Money
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp
from synthetic_sales_assist.persistence.faults import FaultInjector, FaultPoint
from synthetic_sales_assist.persistence.records import (
    SalesCreditPurgeResult,
    StoredSalesCreditCase,
    StoredSalesCreditEvent,
)
from synthetic_sales_assist.sales_credit.accumulator import (
    CaseMutation,
    _MANAGER_OUTCOME_STATES,
    _TERMINAL_SYSTEM_STATES,
    _discovery_interactions_for_order,
    _evidence_dict,
    _interaction_dict,
    _replacement_candidate_dict,
    _search_run_bytes,
    _snapshot_dict,
)
from synthetic_sales_assist.sales_credit.discovery import OrderSearchRun, plan_discovery
from synthetic_sales_assist.sales_credit.models import (
    AttributionClassification,
    ClosedAuditRecord,
    HumanOutcomeType,
    ManagerOutcome,
    OrderValueStatus,
    ReplacementStatus,
    SalesCreditReason,
    SalesCreditEvaluation,
    WorkflowState,
)
from synthetic_sales_assist.sales_credit.retention import (
    ClosureProjection,
    NoOrderClosedAuditRecord,
    NoOrderClosureProjection,
)
from synthetic_sales_assist.sales_credit.windows import business_local_date


class SalesCreditRepositoryError(RuntimeError):
    """Base closed persistence error for Sales Credit state."""


class SalesCreditPersistenceConflict(SalesCreditRepositoryError):
    """A retained identity or expected projection was reused inconsistently."""


def _canonical(value: dict[str, object]) -> bytes:
    return canonical_json_bytes(value, expected_members=set(value))


def _money_columns(value: Money | None) -> tuple[str | None, str | None, str | None, int | None]:
    if value is None:
        return (None, None, None, None)
    return (
        str(value.minor_units),
        value.currency_code,
        value.registry_version,
        value.scale,
    )


def _money_from_row(
    minor_units: object,
    currency: object,
    registry: object,
    scale: object,
) -> Money | None:
    if minor_units is None:
        if any(item is not None for item in (currency, registry, scale)):
            raise SalesCreditRepositoryError("PERSISTED_MONEY_PARTITION_INVALID")
        return None
    try:
        return Money.from_minor_units(
            int(str(minor_units)),
            currency_code=str(currency),
            registry_version=str(registry),
            scale=int(scale),
        )
    except (TypeError, ValueError) as exc:
        raise SalesCreditRepositoryError("PERSISTED_MONEY_INVALID") from exc


def _manager_outcome_from_row(row: sqlite3.Row) -> ManagerOutcome:
    try:
        material = bytes(row["canonical_bytes"])
        binding = domain_hash(ManagerOutcome.HASH_DOMAIN, material)
        if binding.sha256 != str(row["material_sha256"]):
            raise SalesCreditRepositoryError("MANAGER_OUTCOME_HASH_MISMATCH")
        value = parse_canonical_json_bytes(
            material,
            expected_members={
                "active_note",
                "actor",
                "approved_amount",
                "controlled_reason",
                "decided_at",
                "occurrence_id",
                "outcome",
                "recorded_at",
                "schema_version",
            },
        )
        if type(value) is not dict:
            raise SalesCreditRepositoryError("MANAGER_OUTCOME_MATERIAL_INVALID")
        approved_value = value["approved_amount"]
        approved = (
            None if approved_value is None else Money.from_json_value(approved_value)
        )
        controlled_value = value["controlled_reason"]
        outcome = ManagerOutcome(
            occurrence_id=EvidenceId(str(value["occurrence_id"])),
            outcome=HumanOutcomeType(str(value["outcome"])),
            decided_at=CanonicalTimestamp(str(value["decided_at"])),
            actor=RepId(str(value["actor"])),
            recorded_at=CanonicalTimestamp(str(value["recorded_at"])),
            approved_amount=approved,
            controlled_reason=(
                None
                if controlled_value is None
                else SalesCreditReason(str(controlled_value))
            ),
            active_note=(
                None if value["active_note"] is None else str(value["active_note"])
            ),
            schema_version=str(value["schema_version"]),
        )
    except SalesCreditRepositoryError:
        raise
    except (TypeError, ValueError, KeyError) as exc:
        raise SalesCreditRepositoryError(
            "MANAGER_OUTCOME_MATERIAL_INVALID"
        ) from exc
    if (
        outcome.canonical_bytes() != material
        or outcome.occurrence_id.value != str(row["occurrence_id"])
        or outcome.outcome.value != str(row["outcome"])
        or outcome.decided_at.value != str(row["decided_at"])
        or outcome.recorded_at.value != str(row["recorded_at"])
        or outcome.actor.value != str(row["actor_id"])
        or outcome.approved_amount
        != _money_from_row(
            row["approved_minor_units"],
            row["approved_currency"],
            row["approved_registry_version"],
            row["approved_scale"],
        )
    ):
        raise SalesCreditRepositoryError("MANAGER_OUTCOME_PROJECTION_MISMATCH")
    return outcome


def _purge_at(closed_at: CanonicalTimestamp) -> CanonicalTimestamp:
    seconds = closed_at.epoch_seconds + 90 * 24 * 60 * 60
    base = datetime.fromtimestamp(seconds, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    fraction = "" if closed_at.nanosecond == 0 else f".{closed_at.nanosecond:09d}".rstrip("0")
    return CanonicalTimestamp(base + fraction + "Z")


def _replacement_event_id(
    parent_event_id: EvidenceId,
    candidate_order_id: OrderId,
) -> EvidenceId:
    material = (
        parent_event_id.value.encode("ascii")
        + b"\n"
        + candidate_order_id.value.encode("ascii")
    )
    digest = hashlib.sha256(material).hexdigest().upper()
    return EvidenceId(f"SYN-EVIDENCE-M4-SC-REPLACEMENT-{digest[:24]}")


def _replacement_detach_identity(
    parent_order_id: OrderId,
    candidate_order_id: OrderId,
    predecessor_event_id: EvidenceId,
) -> tuple[EvidenceId, str]:
    material = b"\n".join(
        (
            parent_order_id.value.encode("ascii"),
            candidate_order_id.value.encode("ascii"),
            predecessor_event_id.value.encode("ascii"),
        )
    )
    digest = hashlib.sha256(material).hexdigest().upper()
    return (
        EvidenceId(f"SYN-EVIDENCE-M4-SC-REPLACEMENT-DETACHED-{digest[:24]}"),
        f"SYN-EVIDENCE-M4-SC-DETACH-COMMAND-{digest[:24]}",
    )


class SalesCreditRepository:
    """Persist already-validated M2 domain records without reinterpreting rules."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        fault_injector: FaultInjector | None = None,
    ) -> None:
        if not isinstance(connection, sqlite3.Connection):
            raise SalesCreditRepositoryError("SALES_CREDIT_CONNECTION_INVALID")
        self.connection = connection
        self.faults = FaultInjector() if fault_injector is None else fault_injector

    def _ensure_immutable(
        self,
        *,
        table: str,
        key_column: str,
        key: str,
        canonical_bytes: bytes,
        insert_sql: str,
        parameters: tuple[object, ...],
    ) -> bool:
        retained = self.connection.execute(
            f"SELECT canonical_bytes FROM {table} WHERE {key_column} = ?",
            (key,),
        ).fetchone()
        if retained is not None:
            if bytes(retained[0]) != canonical_bytes:
                raise SalesCreditPersistenceConflict("IMMUTABLE_IDENTITY_CONFLICT")
            return False
        self.connection.execute(insert_sql, parameters)
        return True

    def persist_interaction(self, interaction: object) -> None:
        from synthetic_sales_assist.sales_credit.models import InteractionRecord

        if type(interaction) is not InteractionRecord:
            raise SalesCreditRepositoryError("INTERACTION_TYPE_INVALID")
        value = interaction
        material = _canonical(_interaction_dict(value))
        self._ensure_immutable(
            table="sc_interactions",
            key_column="interaction_id",
            key=value.interaction_id.value,
            canonical_bytes=material,
            insert_sql="""
                INSERT INTO sc_interactions (
                    interaction_id, source_ref_id, recorded_at, timestamp_precision,
                    workflow_state, canonical_bytes
                ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            parameters=(
                value.interaction_id.value,
                value.source_ref.value,
                value.recorded_at.value,
                value.timestamp_precision.value,
                value.workflow_state.value,
                material,
            ),
        )

    def persist_search_run(self, run: OrderSearchRun) -> None:
        if type(run) is not OrderSearchRun:
            raise SalesCreditRepositoryError("SEARCH_RUN_TYPE_INVALID")
        for interaction in run.interactions:
            self.persist_interaction(interaction)
        material = _search_run_bytes(run)
        inserted = self._ensure_immutable(
            table="sc_search_runs",
            key_column="run_id",
            key=run.run_id.value,
            canonical_bytes=material,
            insert_sql="""
                INSERT INTO sc_search_runs (
                    run_id, trigger_type, started_at, completed_at, adapter_version,
                    enumeration_complete, terminal_outcome, canonical_bytes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            parameters=(
                run.run_id.value,
                run.trigger.value,
                run.started_at.value,
                run.completed_at.value,
                run.adapter.version,
                int(run.result.enumeration_complete),
                run.result.outcome.value,
                material,
            ),
        )
        if not inserted:
            return
        for result in run.native_result_sets:
            owners = []
            for interaction in run.interactions:
                plan = plan_discovery(
                    email_values=(
                        () if interaction.email is None else (interaction.email,)
                    ),
                    phone_values=(
                        () if interaction.phone is None else (interaction.phone,)
                    ),
                )
                if result.identifier in plan.identifiers:
                    owners.append(interaction)
            if not owners:
                raise SalesCreditRepositoryError("SEARCH_IDENTIFIER_OWNER_MISSING")
            for interaction in owners:
                self.connection.execute(
                    """
                    INSERT INTO sc_search_identifiers (
                        run_id, interaction_id, identifier_kind, normalized_value, completeness
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        run.run_id.value,
                        interaction.interaction_id.value,
                        result.identifier.kind.value,
                        result.identifier.value,
                        result.completeness.value,
                    ),
                )
                for order_id in result.order_ids:
                    self.connection.execute(
                        """
                        INSERT INTO sc_search_result_orders (
                            run_id, interaction_id, identifier_kind, order_id
                        ) VALUES (?, ?, ?, ?)
                        """,
                        (
                            run.run_id.value,
                            interaction.interaction_id.value,
                            result.identifier.kind.value,
                            order_id.value,
                        ),
                    )

    def persist_snapshot(self, snapshot: object) -> None:
        from synthetic_sales_assist.sales_credit.models import OrderSnapshot

        if type(snapshot) is not OrderSnapshot or snapshot.order_id is None:
            raise SalesCreditRepositoryError("SNAPSHOT_TYPE_INVALID")
        value = snapshot
        material = _canonical(_snapshot_dict(value))
        inserted = self._ensure_immutable(
            table="sc_snapshots",
            key_column="snapshot_id",
            key=value.snapshot_id.value,
            canonical_bytes=material,
            insert_sql="""
                INSERT INTO sc_snapshots (
                    snapshot_id, order_id, captured_at, extraction_status,
                    lifecycle_status, parser_version, canonical_bytes
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            parameters=(
                value.snapshot_id.value,
                value.order_id.value,
                value.captured_at.value,
                value.extraction_status.value,
                value.lifecycle_status.value,
                value.parser.version,
                material,
            ),
        )
        if not inserted:
            return
        for line in value.lines:
            amount = _money_columns(line.line_value)
            self.connection.execute(
                """
                INSERT INTO sc_snapshot_lines (
                    snapshot_id, line_id, sku_id, quantity, line_minor_units,
                    currency, currency_registry_version, currency_scale, canonical_bytes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    value.snapshot_id.value,
                    line.line_id.value,
                    line.sku_id.value,
                    str(line.quantity.value),
                    *amount,
                    line.content.canonical_bytes,
                ),
            )

    def persist_evidence(self, evidence: object) -> None:
        from synthetic_sales_assist.sales_credit.models import EvidenceEvent

        if type(evidence) is not EvidenceEvent:
            raise SalesCreditRepositoryError("EVIDENCE_TYPE_INVALID")
        value = evidence
        material = _canonical(_evidence_dict(value))
        self._ensure_immutable(
            table="sc_evidence_events",
            key_column="evidence_id",
            key=value.evidence_id.value,
            canonical_bytes=material,
            insert_sql="""
                INSERT INTO sc_evidence_events (
                    evidence_id, order_id, interaction_id, source_type,
                    classification, occurred_at, canonical_bytes
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            parameters=(
                value.evidence_id.value,
                value.order_id.value,
                value.interaction_id.value,
                value.source_type.value,
                value.classification.value,
                value.occurred_at.value,
                material,
            ),
        )

    def persist_evaluation(self, evaluation: SalesCreditEvaluation) -> None:
        if type(evaluation) is not SalesCreditEvaluation:
            raise SalesCreditRepositoryError("EVALUATION_TYPE_INVALID")
        material = evaluation.canonical_bytes()
        inserted = self._ensure_immutable(
            table="sc_evaluations",
            key_column="evaluation_id",
            key=evaluation.evaluation_id.value,
            canonical_bytes=material,
            insert_sql="""
                INSERT INTO sc_evaluations (
                    evaluation_id, order_id, snapshot_id, workflow_state, attribution,
                    order_value_status, human_review_required, rule_pack_version,
                    material_sha256, canonical_bytes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            parameters=(
                evaluation.evaluation_id.value,
                evaluation.order_id.value,
                evaluation.snapshot_id.value,
                evaluation.workflow_state.value,
                evaluation.attribution.classification.value,
                evaluation.value.status.value,
                int(evaluation.human_review_required),
                evaluation.rule_pack_version,
                evaluation.hash_binding().sha256,
                material,
            ),
        )
        if inserted:
            for ordinal, reason in enumerate(evaluation.reasons, start=1):
                self.connection.execute(
                    """
                    INSERT INTO sc_evaluation_reasons (evaluation_id, ordinal, reason_code)
                    VALUES (?, ?, ?)
                    """,
                    (evaluation.evaluation_id.value, ordinal, reason.value),
                )

    def _event_material(
        self,
        *,
        event_id: EvidenceId,
        order_id: OrderId,
        sequence: int,
        predecessor: EvidenceId | None,
        event_kind: str,
        workflow: WorkflowState,
        attribution: AttributionClassification,
        value_status: OrderValueStatus,
        human_outcome: HumanOutcomeType | None,
        evaluation_id: EvaluationId | None,
        replacement_parent: OrderId | None,
        occurred_at: CanonicalTimestamp,
        command_id: str,
    ) -> bytes:
        return _canonical(
            {
                "attribution": attribution.value,
                "command_id": command_id,
                "current_evaluation_id": None if evaluation_id is None else evaluation_id.value,
                "event_id": event_id.value,
                "event_kind": event_kind,
                "human_outcome": None if human_outcome is None else human_outcome.value,
                "occurred_at": occurred_at.value,
                "order_id": order_id.value,
                "order_value_status": value_status.value,
                "predecessor_event_id": None if predecessor is None else predecessor.value,
                "replacement_parent_present": replacement_parent is not None,
                "sequence": sequence,
                "workflow_state": workflow.value,
            }
        )

    def _append_event(
        self,
        *,
        event_id: EvidenceId,
        order_id: OrderId,
        sequence: int,
        predecessor: EvidenceId | None,
        event_kind: str,
        workflow: WorkflowState,
        attribution: AttributionClassification,
        value_status: OrderValueStatus,
        human_outcome: HumanOutcomeType | None,
        evaluation_id: EvaluationId | None,
        replacement_parent: OrderId | None,
        occurred_at: CanonicalTimestamp,
        command_id: str,
    ) -> None:
        if replacement_parent is not None and type(replacement_parent) is not OrderId:
            raise SalesCreditRepositoryError("REPLACEMENT_PARENT_ID_INVALID")
        material = self._event_material(
            event_id=event_id,
            order_id=order_id,
            sequence=sequence,
            predecessor=predecessor,
            event_kind=event_kind,
            workflow=workflow,
            attribution=attribution,
            value_status=value_status,
            human_outcome=human_outcome,
            evaluation_id=evaluation_id,
            replacement_parent=replacement_parent,
            occurred_at=occurred_at,
            command_id=command_id,
        )
        self.faults.hit(FaultPoint.BEFORE_EVENT_APPEND)
        self.connection.execute(
            """
            INSERT INTO sc_case_events (
                event_id, order_id, sequence, predecessor_event_id, event_kind,
                workflow_state, attribution, order_value_status, manager_outcome,
                current_evaluation_id, replacement_parent_present, occurred_at,
                command_id, canonical_bytes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id.value,
                order_id.value,
                sequence,
                None if predecessor is None else predecessor.value,
                event_kind,
                workflow.value,
                attribution.value,
                value_status.value,
                None if human_outcome is None else human_outcome.value,
                None if evaluation_id is None else evaluation_id.value,
                int(replacement_parent is not None),
                occurred_at.value,
                command_id,
                material,
            ),
        )
        self.faults.hit(FaultPoint.AFTER_EVENT_BEFORE_PROJECTION)

    def append_mutation(
        self,
        mutation: CaseMutation,
        *,
        command_id: str,
        event_id: EvidenceId,
    ) -> StoredSalesCreditCase:
        if type(mutation) is not CaseMutation or type(event_id) is not EvidenceId:
            raise SalesCreditRepositoryError("CASE_MUTATION_TYPE_INVALID")
        for interaction in mutation.interactions:
            self.persist_interaction(interaction)
        for run in (mutation.discovery_run, mutation.replacement_run):
            if run is not None:
                self.persist_search_run(run)
        for snapshot in mutation.snapshots:
            self.persist_snapshot(snapshot)
        for evidence in mutation.evidence:
            self.persist_evidence(evidence)
        if mutation.evaluation is not None:
            self.persist_evaluation(mutation.evaluation)

        retained = self.get_case(mutation.order_id)
        evaluation = mutation.evaluation
        if retained is not None and retained.workflow_state is WorkflowState.CLOSED:
            raise SalesCreditPersistenceConflict("CLOSED_CASE_MUTATION")
        if retained is not None:
            projection_authority = self.connection.execute(
                """
                SELECT replacement_parent_order_id
                FROM sc_cases WHERE order_id = ?
                """,
                (mutation.order_id.value,),
            ).fetchone()
            if projection_authority is None:
                raise SalesCreditRepositoryError("CASE_PROJECTION_READBACK_FAILED")
            if projection_authority[0] is not None:
                raise SalesCreditPersistenceConflict("REPLACEMENT_CHILD_PENDING_PARENT")
            if retained.manager_occurrence_id is not None:
                raise SalesCreditPersistenceConflict("RESOLVED_CASE_MUTATION")
            if retained.workflow_state in _TERMINAL_SYSTEM_STATES:
                raise SalesCreditPersistenceConflict("TERMINAL_CASE_MUTATION")
            if (
                mutation.occurred_at.epoch_seconds,
                mutation.occurred_at.nanosecond,
            ) < (retained.updated_at.epoch_seconds, retained.updated_at.nanosecond):
                raise SalesCreditPersistenceConflict("CASE_MUTATION_TIME_REGRESSION")
        if evaluation is None:
            if retained is None:
                workflow = WorkflowState.AWAITING_SOURCE_REVIEW
                attribution = AttributionClassification.UNKNOWN
                value_status = OrderValueStatus.UNKNOWN
                placed_value = None
                evaluation_id = None
            else:
                workflow = retained.workflow_state
                attribution = retained.attribution
                value_status = retained.order_value_status
                placed_value = retained.placed_value
                evaluation_id = retained.current_evaluation_id
        else:
            workflow = evaluation.workflow_state
            attribution = evaluation.attribution.classification
            value_status = evaluation.value.status
            placed_value = evaluation.value.placed_value
            evaluation_id = evaluation.evaluation_id
        if retained is None:
            sequence = 1
            predecessor = None
            event_kind = "CASE_CREATED"
            created_at = mutation.occurred_at
        else:
            sequence = retained.last_event_sequence + 1
            predecessor = retained.last_event_id
            event_kind = "FACTS_APPENDED"
            created_at = retained.created_at
        self._append_event(
            event_id=event_id,
            order_id=mutation.order_id,
            sequence=sequence,
            predecessor=predecessor,
            event_kind=event_kind,
            workflow=workflow,
            attribution=attribution,
            value_status=value_status,
            human_outcome=None,
            evaluation_id=evaluation_id,
            replacement_parent=None if retained is None else retained.replacement_parent,
            occurred_at=mutation.occurred_at,
            command_id=command_id,
        )
        money = _money_columns(placed_value)
        if retained is None:
            self.connection.execute(
                """
                INSERT INTO sc_cases (
                    order_id, projection_version, workflow_state, attribution,
                    order_value_status, placed_minor_units, placed_currency,
                    placed_registry_version, placed_scale, manager_occurrence_id,
                    replacement_parent_order_id, current_evaluation_id,
                    last_event_sequence, last_event_id, created_at, updated_at
                ) VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, 1, ?, ?, ?)
                """,
                (
                    mutation.order_id.value,
                    workflow.value,
                    attribution.value,
                    value_status.value,
                    *money,
                    None if evaluation_id is None else evaluation_id.value,
                    event_id.value,
                    created_at.value,
                    mutation.occurred_at.value,
                ),
            )
        else:
            cursor = self.connection.execute(
                """
                UPDATE sc_cases
                SET projection_version = projection_version + 1,
                    workflow_state = ?, attribution = ?, order_value_status = ?,
                    placed_minor_units = ?, placed_currency = ?,
                    placed_registry_version = ?, placed_scale = ?,
                    current_evaluation_id = ?, last_event_sequence = ?,
                    last_event_id = ?, updated_at = ?
                WHERE order_id = ? AND projection_version = ? AND last_event_id = ?
                """,
                (
                    workflow.value,
                    attribution.value,
                    value_status.value,
                    *money,
                    None if evaluation_id is None else evaluation_id.value,
                    sequence,
                    event_id.value,
                    mutation.occurred_at.value,
                    mutation.order_id.value,
                    retained.projection_version,
                    retained.last_event_id.value,
                ),
            )
            if cursor.rowcount != 1:
                raise SalesCreditPersistenceConflict("CASE_PROJECTION_CONFLICT")
        self.faults.hit(FaultPoint.AFTER_PROJECTION_BEFORE_RECEIPT)
        for interaction in mutation.interactions:
            self.connection.execute(
                """
                INSERT OR IGNORE INTO sc_case_interactions (order_id, interaction_id)
                VALUES (?, ?)
                """,
                (mutation.order_id.value, interaction.interaction_id.value),
            )
        for run in (mutation.discovery_run, mutation.replacement_run):
            if run is not None:
                self.connection.execute(
                    "INSERT OR IGNORE INTO sc_case_search_runs (order_id, run_id) VALUES (?, ?)",
                    (mutation.order_id.value, run.run_id.value),
                )
        for snapshot in mutation.snapshots:
            self.connection.execute(
                "INSERT OR IGNORE INTO sc_case_snapshots (order_id, snapshot_id) VALUES (?, ?)",
                (mutation.order_id.value, snapshot.snapshot_id.value),
            )
        for evidence in mutation.evidence:
            self.connection.execute(
                "INSERT OR IGNORE INTO sc_case_evidence (order_id, evidence_id) VALUES (?, ?)",
                (mutation.order_id.value, evidence.evidence_id.value),
            )
        if evaluation is not None:
            self.connection.execute(
                "INSERT OR IGNORE INTO sc_case_evaluations (order_id, evaluation_id) VALUES (?, ?)",
                (mutation.order_id.value, evaluation.evaluation_id.value),
            )
        self._persist_replacement_candidates(
            mutation,
            command_id=command_id,
            parent_event_id=event_id,
        )
        result = self.get_case(mutation.order_id)
        if result is None or result.last_event_id != event_id:
            raise SalesCreditRepositoryError("CASE_PROJECTION_READBACK_FAILED")
        return result

    def _persist_replacement_candidates(
        self,
        mutation: CaseMutation,
        *,
        command_id: str,
        parent_event_id: EvidenceId,
    ) -> None:
        if not mutation.replacement_candidates:
            return
        evaluation = mutation.evaluation
        run = mutation.replacement_run
        if evaluation is None or run is None:
            raise SalesCreditRepositoryError("REPLACEMENT_AUTHORITY_MISSING")
        results = {
            item.order_id: item
            for item in evaluation.replacement.candidate_results
        }
        for candidate_input in mutation.replacement_candidates:
            snapshot = candidate_input.snapshot
            candidate_order_id = snapshot.order_id
            if candidate_order_id is None:
                raise SalesCreditRepositoryError("REPLACEMENT_CANDIDATE_IDENTITY_MISSING")
            result = results.get(candidate_order_id)
            if result is None or result.snapshot_id != snapshot.snapshot_id:
                raise SalesCreditRepositoryError("REPLACEMENT_RESULT_MISMATCH")
            self.persist_snapshot(snapshot)
            material = _canonical(
                {
                    "candidate": _replacement_candidate_dict(candidate_input),
                    "evaluation_id": evaluation.evaluation_id.value,
                    "parent_order_id": mutation.order_id.value,
                    "replacement_run_id": run.run_id.value,
                    "result": result.to_dict(),
                }
            )
            retained_material = self.connection.execute(
                """
                SELECT canonical_bytes FROM sc_replacement_candidates
                WHERE evaluation_id = ? AND candidate_order_id = ?
                """,
                (evaluation.evaluation_id.value, candidate_order_id.value),
            ).fetchone()
            if retained_material is not None:
                if bytes(retained_material[0]) != material:
                    raise SalesCreditPersistenceConflict(
                        "REPLACEMENT_CANDIDATE_IDENTITY_CONFLICT"
                    )
            else:
                self.connection.execute(
                    """
                    INSERT INTO sc_replacement_candidates (
                        parent_order_id, evaluation_id, replacement_run_id,
                        candidate_order_id, snapshot_id, candidate_status,
                        customer_continuity, product_continuity,
                        line_universe_complete, possible_nonexact_continuity,
                        canonical_bytes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        mutation.order_id.value,
                        evaluation.evaluation_id.value,
                        run.run_id.value,
                        candidate_order_id.value,
                        snapshot.snapshot_id.value,
                        result.status.value,
                        result.customer_continuity.value,
                        result.product_continuity.value,
                        int(candidate_input.line_universe_complete),
                        int(candidate_input.possible_nonexact_continuity),
                        material,
                    ),
                )
            if result.status not in {
                ReplacementStatus.EXACT_RELEVANT,
                ReplacementStatus.POSSIBLE_REVIEW,
            }:
                continue
            closed = self.connection.execute(
                "SELECT 1 FROM sc_closed_audits WHERE order_id = ?",
                (candidate_order_id.value,),
            ).fetchone()
            if closed is not None:
                continue
            self._link_replacement_candidate(
                candidate_order_id=candidate_order_id,
                snapshot_id=snapshot.snapshot_id,
                run=run,
                parent_order_id=mutation.order_id,
                occurred_at=mutation.occurred_at,
                command_id=command_id,
                event_id=_replacement_event_id(parent_event_id, candidate_order_id),
            )

    def _link_replacement_candidate(
        self,
        *,
        candidate_order_id: OrderId,
        snapshot_id: SnapshotId,
        run: OrderSearchRun,
        parent_order_id: OrderId,
        occurred_at: CanonicalTimestamp,
        command_id: str,
        event_id: EvidenceId,
    ) -> None:
        if type(snapshot_id) is not SnapshotId:
            raise SalesCreditRepositoryError("REPLACEMENT_SNAPSHOT_ID_INVALID")
        retained = self.get_case(candidate_order_id)
        if retained is not None:
            if (
                retained.workflow_state in _TERMINAL_SYSTEM_STATES
                or retained.workflow_state is WorkflowState.CLOSED
                or retained.manager_occurrence_id is not None
            ):
                raise SalesCreditPersistenceConflict("REPLACEMENT_LINK_RESOLVED")
            if retained.replacement_parent not in {None, parent_order_id}:
                raise SalesCreditPersistenceConflict("REPLACEMENT_PARENT_CONFLICT")
            if (occurred_at.epoch_seconds, occurred_at.nanosecond) < (
                retained.updated_at.epoch_seconds,
                retained.updated_at.nanosecond,
            ):
                raise SalesCreditPersistenceConflict("REPLACEMENT_LINK_TIME_REGRESSION")
            workflow = retained.workflow_state
            attribution = retained.attribution
            value_status = retained.order_value_status
            evaluation_id = retained.current_evaluation_id
            sequence = retained.last_event_sequence + 1
            predecessor = retained.last_event_id
            created_at = retained.created_at
        else:
            workflow = WorkflowState.AWAITING_SOURCE_REVIEW
            attribution = AttributionClassification.UNKNOWN
            value_status = OrderValueStatus.UNKNOWN
            evaluation_id = None
            sequence = 1
            predecessor = None
            created_at = occurred_at
        self._append_event(
            event_id=event_id,
            order_id=candidate_order_id,
            sequence=sequence,
            predecessor=predecessor,
            event_kind="CASE_CREATED" if retained is None else "FACTS_APPENDED",
            workflow=workflow,
            attribution=attribution,
            value_status=value_status,
            human_outcome=None,
            evaluation_id=evaluation_id,
            replacement_parent=parent_order_id,
            occurred_at=occurred_at,
            command_id=command_id,
        )
        if retained is None:
            self.connection.execute(
                """
                INSERT INTO sc_cases (
                    order_id, projection_version, workflow_state, attribution,
                    order_value_status, placed_minor_units, placed_currency,
                    placed_registry_version, placed_scale, manager_occurrence_id,
                    replacement_parent_order_id, current_evaluation_id,
                    last_event_sequence, last_event_id, created_at, updated_at
                ) VALUES (?, 1, ?, ?, ?, NULL, NULL, NULL, NULL, NULL, ?, NULL,
                          1, ?, ?, ?)
                """,
                (
                    candidate_order_id.value,
                    workflow.value,
                    attribution.value,
                    value_status.value,
                    parent_order_id.value,
                    event_id.value,
                    created_at.value,
                    occurred_at.value,
                ),
            )
        else:
            cursor = self.connection.execute(
                """
                UPDATE sc_cases
                SET projection_version = projection_version + 1,
                    replacement_parent_order_id = ?, last_event_sequence = ?,
                    last_event_id = ?, updated_at = ?
                WHERE order_id = ? AND projection_version = ? AND last_event_id = ?
                """,
                (
                    parent_order_id.value,
                    sequence,
                    event_id.value,
                    occurred_at.value,
                    candidate_order_id.value,
                    retained.projection_version,
                    retained.last_event_id.value,
                ),
            )
            if cursor.rowcount != 1:
                raise SalesCreditPersistenceConflict("CASE_PROJECTION_CONFLICT")
        prior_link = self.connection.execute(
            """
            SELECT parent_order_id FROM sc_active_replacement_links
            WHERE candidate_order_id = ?
            """,
            (candidate_order_id.value,),
        ).fetchone()
        if prior_link is not None and str(prior_link[0]) != parent_order_id.value:
            raise SalesCreditPersistenceConflict("REPLACEMENT_PARENT_CONFLICT")
        self.connection.execute(
            """
            INSERT INTO sc_active_replacement_links (
                candidate_order_id, parent_order_id, replacement_run_id, linked_at
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT (candidate_order_id) DO UPDATE SET
                replacement_run_id = excluded.replacement_run_id,
                linked_at = excluded.linked_at
            """,
            (
                candidate_order_id.value,
                parent_order_id.value,
                run.run_id.value,
                occurred_at.value,
            ),
        )
        selected_interactions = _discovery_interactions_for_order(
            run,
            candidate_order_id,
        )
        for interaction in selected_interactions:
            self.connection.execute(
                """
                INSERT OR IGNORE INTO sc_case_interactions (order_id, interaction_id)
                VALUES (?, ?)
                """,
                (candidate_order_id.value, interaction.interaction_id.value),
            )
        self.connection.execute(
            """
            INSERT OR IGNORE INTO sc_case_snapshots (order_id, snapshot_id)
            VALUES (?, ?)
            """,
            (candidate_order_id.value, snapshot_id.value),
        )
        self.connection.execute(
            """
            INSERT OR IGNORE INTO sc_case_search_runs (order_id, run_id)
            VALUES (?, ?)
            """,
            (candidate_order_id.value, run.run_id.value),
        )
        readback = self.get_case(candidate_order_id)
        if readback is None or readback.replacement_parent != parent_order_id:
            raise SalesCreditRepositoryError("REPLACEMENT_PROJECTION_READBACK_FAILED")

    def append_manager_outcome(
        self,
        *,
        order_id: OrderId,
        outcome: ManagerOutcome,
        command_id: str,
        event_id: EvidenceId,
    ) -> StoredSalesCreditCase:
        if type(order_id) is not OrderId or type(outcome) is not ManagerOutcome:
            raise SalesCreditRepositoryError("MANAGER_OUTCOME_TYPE_INVALID")
        retained = self.get_case(order_id)
        if retained is None or retained.workflow_state is WorkflowState.CLOSED:
            raise SalesCreditPersistenceConflict("MANAGER_OUTCOME_CASE_INVALID")
        authority = self.connection.execute(
            """
            SELECT cases.replacement_parent_order_id, evaluation.workflow_state
            FROM sc_cases AS cases
            LEFT JOIN sc_evaluations AS evaluation
                ON evaluation.evaluation_id = cases.current_evaluation_id
            WHERE cases.order_id = ?
            """,
            (order_id.value,),
        ).fetchone()
        if authority is None:
            raise SalesCreditPersistenceConflict("MANAGER_OUTCOME_CASE_INVALID")
        if authority[0] is not None:
            raise SalesCreditPersistenceConflict("REPLACEMENT_CHILD_PENDING_PARENT")
        if retained.workflow_state not in _MANAGER_OUTCOME_STATES:
            raise SalesCreditPersistenceConflict("MANAGER_OUTCOME_WORKFLOW_NOT_AUTHORIZED")
        if (
            retained.current_evaluation_id is None
            or authority[1] is None
            or str(authority[1]) != retained.workflow_state.value
        ):
            raise SalesCreditPersistenceConflict("MANAGER_OUTCOME_EVALUATION_MISMATCH")
        current_time = (retained.updated_at.epoch_seconds, retained.updated_at.nanosecond)
        if (
            (outcome.decided_at.epoch_seconds, outcome.decided_at.nanosecond) < current_time
            or (outcome.recorded_at.epoch_seconds, outcome.recorded_at.nanosecond)
            < current_time
        ):
            raise SalesCreditPersistenceConflict("MANAGER_OUTCOME_TIME_REGRESSION")
        material = outcome.canonical_bytes()
        inserted = self._ensure_immutable(
            table="sc_manager_outcomes",
            key_column="occurrence_id",
            key=outcome.occurrence_id.value,
            canonical_bytes=material,
            insert_sql="""
                INSERT INTO sc_manager_outcomes (
                    occurrence_id, order_id, outcome, decided_at, recorded_at, actor_id,
                    approved_minor_units, approved_currency, approved_registry_version,
                    approved_scale, material_sha256, canonical_bytes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            parameters=(
                outcome.occurrence_id.value,
                order_id.value,
                outcome.outcome.value,
                outcome.decided_at.value,
                outcome.recorded_at.value,
                outcome.actor.value,
                *_money_columns(outcome.approved_amount),
                outcome.hash_binding().sha256,
                material,
            ),
        )
        if not inserted:
            raise SalesCreditPersistenceConflict("MANAGER_OUTCOME_DUPLICATE_COMMAND_REQUIRED")
        sequence = retained.last_event_sequence + 1
        self._append_event(
            event_id=event_id,
            order_id=order_id,
            sequence=sequence,
            predecessor=retained.last_event_id,
            event_kind="OUTCOME_RECORDED",
            workflow=WorkflowState.CLOSED,
            attribution=retained.attribution,
            value_status=retained.order_value_status,
            human_outcome=outcome.outcome,
            evaluation_id=retained.current_evaluation_id,
            replacement_parent=retained.replacement_parent,
            occurred_at=outcome.recorded_at,
            command_id=command_id,
        )
        cursor = self.connection.execute(
            """
            UPDATE sc_cases
            SET projection_version = projection_version + 1,
                workflow_state = ?, manager_occurrence_id = ?,
                last_event_sequence = ?, last_event_id = ?, updated_at = ?
            WHERE order_id = ? AND projection_version = ? AND last_event_id = ?
            """,
            (
                WorkflowState.CLOSED.value,
                outcome.occurrence_id.value,
                sequence,
                event_id.value,
                outcome.recorded_at.value,
                order_id.value,
                retained.projection_version,
                retained.last_event_id.value,
            ),
        )
        if cursor.rowcount != 1:
            raise SalesCreditPersistenceConflict("CASE_PROJECTION_CONFLICT")
        self.faults.hit(FaultPoint.AFTER_PROJECTION_BEFORE_RECEIPT)
        result = self.get_case(order_id)
        if result is None:
            raise SalesCreditRepositoryError("CASE_PROJECTION_READBACK_FAILED")
        return result

    def close_and_minimize(
        self,
        *,
        projection: ClosureProjection,
        audit_id: EvidenceId,
        command_id: str,
        event_id: EvidenceId,
    ) -> StoredSalesCreditCase:
        if type(projection) is not ClosureProjection or type(audit_id) is not EvidenceId:
            raise SalesCreditRepositoryError("CLOSURE_TYPE_INVALID")
        record = projection.record
        retained = self.get_case(record.order_id)
        if retained is None:
            raise SalesCreditPersistenceConflict("CLOSURE_CASE_MISSING")
        closed_key = (record.closed_at.epoch_seconds, record.closed_at.nanosecond)
        current_key = (retained.updated_at.epoch_seconds, retained.updated_at.nanosecond)
        if (
            record.opened_at != retained.created_at
            or closed_key < current_key
            or record.attribution is not retained.attribution
            or record.order_value_status is not retained.order_value_status
            or retained.current_evaluation_id is None
        ):
            raise SalesCreditPersistenceConflict("CLOSURE_PROJECTION_MISMATCH")
        authority = self.connection.execute(
            """
            SELECT workflow_state FROM sc_evaluations
            WHERE evaluation_id = ? AND order_id = ?
            """,
            (retained.current_evaluation_id.value, record.order_id.value),
        ).fetchone()
        reasons = tuple(
            str(row[0])
            for row in self.connection.execute(
                """
                SELECT reason_code FROM sc_evaluation_reasons
                WHERE evaluation_id = ? ORDER BY ordinal
                """,
                (retained.current_evaluation_id.value,),
            ).fetchall()
        )
        if (
            authority is None
            or str(authority[0]) != record.system_workflow_before_close.value
            or reasons != tuple(reason.value for reason in record.reasons)
        ):
            raise SalesCreditPersistenceConflict("CLOSURE_EVALUATION_MISMATCH")
        relation_counts = tuple(
            int(
                self.connection.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE order_id = ?",
                    (record.order_id.value,),
                ).fetchone()[0]
            )
            for table in (
                "sc_case_interactions",
                "sc_case_snapshots",
                "sc_case_evidence",
                "sc_case_evaluations",
            )
        )
        if relation_counts != (
            projection.interactions_removed,
            projection.snapshots_removed,
            projection.evidence_removed,
            projection.evaluations_removed,
        ):
            raise SalesCreditPersistenceConflict("CLOSURE_REMOVAL_COUNT_MISMATCH")
        outcome = self.connection.execute(
            """
            SELECT outcome, decided_at, recorded_at, actor_id,
                   approved_minor_units, approved_currency,
                   approved_registry_version, approved_scale
            FROM sc_manager_outcomes WHERE order_id = ?
            """,
            (record.order_id.value,),
        ).fetchone()
        if record.human_outcome is None:
            if outcome is not None or retained.manager_occurrence_id is not None:
                raise SalesCreditPersistenceConflict("CLOSURE_OUTCOME_MISMATCH")
        elif (
            outcome is None
            or retained.manager_occurrence_id is None
            or str(outcome[0]) != record.human_outcome.value
            or str(outcome[1]) != record.human_decided_at.value
            or str(outcome[2]) != record.human_recorded_at.value
            or str(outcome[3]) != record.decision_actor.value
            or _money_from_row(outcome[4], outcome[5], outcome[6], outcome[7])
            != record.approved_amount
        ):
            raise SalesCreditPersistenceConflict("CLOSURE_OUTCOME_MISMATCH")
        material = record.canonical_bytes()
        self._ensure_immutable(
            table="sc_closed_audits",
            key_column="audit_id",
            key=audit_id.value,
            canonical_bytes=material,
            insert_sql="""
                INSERT INTO sc_closed_audits (
                    audit_id, order_id, closed_at, purge_eligible_at,
                    workflow_before_close, human_outcome, material_sha256, canonical_bytes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            parameters=(
                audit_id.value,
                record.order_id.value,
                record.closed_at.value,
                _purge_at(record.closed_at).value,
                record.system_workflow_before_close.value,
                None if record.human_outcome is None else record.human_outcome.value,
                record.hash_binding().sha256,
                material,
            ),
        )
        order_value = record.order_value_status
        attribution = record.attribution
        self.connection.execute(
            "DELETE FROM sc_case_events WHERE order_id = ?",
            (record.order_id.value,),
        )
        prior_commands = tuple(
            row[0]
            for row in self.connection.execute(
                """
                SELECT command_id FROM durable_receipt_owners
                WHERE owner_domain = 'SALES_CREDIT' AND owner_id = ? AND command_id != ?
                """,
                (record.order_id.value, command_id),
            ).fetchall()
        )
        for prior_command in prior_commands:
            self.connection.execute(
                "DELETE FROM durable_commands WHERE command_id = ?",
                (prior_command,),
            )
        case_run_ids = tuple(
            str(row[0])
            for row in self.connection.execute(
                "SELECT run_id FROM sc_case_search_runs WHERE order_id = ?",
                (record.order_id.value,),
            ).fetchall()
        )
        for table in (
            "sc_case_evaluations",
            "sc_case_evidence",
            "sc_case_snapshots",
            "sc_case_search_runs",
            "sc_case_interactions",
            "sc_manager_outcomes",
        ):
            self.connection.execute(
                f"DELETE FROM {table} WHERE order_id = ?",
                (record.order_id.value,),
            )
        self._delete_orphans(search_run_ids=case_run_ids)
        self._append_event(
            event_id=event_id,
            order_id=record.order_id,
            sequence=1,
            predecessor=None,
            event_kind="CLOSED_MINIMIZED",
            workflow=WorkflowState.CLOSED,
            attribution=attribution,
            value_status=order_value,
            human_outcome=record.human_outcome,
            evaluation_id=None,
            replacement_parent=retained.replacement_parent,
            occurred_at=record.closed_at,
            command_id=command_id,
        )
        cursor = self.connection.execute(
            """
            UPDATE sc_cases
            SET projection_version = projection_version + 1,
                workflow_state = ?, attribution = ?, order_value_status = ?,
                placed_minor_units = NULL, placed_currency = NULL,
                placed_registry_version = NULL, placed_scale = NULL,
                manager_occurrence_id = NULL, current_evaluation_id = NULL,
                last_event_sequence = 1, last_event_id = ?, updated_at = ?
            WHERE order_id = ? AND projection_version = ?
            """,
            (
                WorkflowState.CLOSED.value,
                attribution.value,
                order_value.value,
                event_id.value,
                record.closed_at.value,
                record.order_id.value,
                retained.projection_version,
            ),
        )
        if cursor.rowcount != 1:
            raise SalesCreditPersistenceConflict("CASE_PROJECTION_CONFLICT")
        self.faults.hit(FaultPoint.AFTER_PROJECTION_BEFORE_RECEIPT)
        result = self.get_case(record.order_id)
        if result is None:
            raise SalesCreditRepositoryError("CASE_PROJECTION_READBACK_FAILED")
        return result

    def close_no_order(
        self,
        *,
        run: OrderSearchRun,
        projection: NoOrderClosureProjection,
        audit_id: EvidenceId,
        command_id: str,
    ) -> NoOrderClosedAuditRecord:
        if (
            type(run) is not OrderSearchRun
            or type(projection) is not NoOrderClosureProjection
            or type(audit_id) is not EvidenceId
        ):
            raise SalesCreditRepositoryError("NO_ORDER_CLOSURE_TYPE_INVALID")
        record = projection.record
        opened_at = min(
            (item.effective_at for item in run.interactions),
            key=lambda item: (item.epoch_seconds, item.nanosecond),
        )
        precisions = tuple(
            sorted(
                {item.effective_precision for item in run.interactions},
                key=lambda item: item.value,
            )
        )
        if (
            run.result.order_ids
            or not run.result.enumeration_complete
            or run.result.outcome.value != "REVIEW_WINDOW_CLOSED_NO_ORDER"
            or projection.interactions_removed != len(run.interactions)
            or projection.identifiers_removed != len(run.attempted_identifiers)
            or projection.native_result_sets_removed != len(run.native_result_sets)
            or record.opened_at != opened_at
            or record.closed_at != run.completed_at
            or record.latest_review_window_end
            != max(item.review_window_end for item in run.interactions)
            or record.interaction_count != len(run.interactions)
            or record.interaction_precisions != precisions
            or record.search_trigger is not run.trigger
            or record.search_adapter_version != run.adapter.version
            or record.search_run_schema_version != run.schema_version
        ):
            raise SalesCreditPersistenceConflict("NO_ORDER_CLOSURE_MISMATCH")
        material = record.canonical_bytes()
        existing = self.connection.execute(
            """
            SELECT canonical_bytes FROM sc_no_order_closed_audits
            WHERE audit_id = ?
            """,
            (audit_id.value,),
        ).fetchone()
        if existing is not None:
            if bytes(existing[0]) != material:
                raise SalesCreditPersistenceConflict(
                    "NO_ORDER_AUDIT_IDENTITY_CONFLICT"
                )
            return record
        self.persist_search_run(run)
        case_owners = self.connection.execute(
            "SELECT COUNT(*) FROM sc_case_search_runs WHERE run_id = ?",
            (run.run_id.value,),
        ).fetchone()[0]
        if int(case_owners) != 0:
            raise SalesCreditPersistenceConflict("NO_ORDER_RUN_HAS_CASE_OWNER")
        self._ensure_immutable(
            table="sc_no_order_closed_audits",
            key_column="audit_id",
            key=audit_id.value,
            canonical_bytes=material,
            insert_sql="""
                INSERT INTO sc_no_order_closed_audits (
                    audit_id, command_id, closed_at, purge_eligible_at,
                    material_sha256, canonical_bytes
                ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            parameters=(
                audit_id.value,
                command_id,
                record.closed_at.value,
                _purge_at(record.closed_at).value,
                record.hash_binding().sha256,
                material,
            ),
        )
        prior_commands = tuple(
            str(row[0])
            for row in self.connection.execute(
                """
                SELECT command_id FROM durable_receipt_owners
                WHERE owner_domain = 'SYSTEM' AND owner_id = ? AND command_id != ?
                """,
                (run.run_id.value, command_id),
            ).fetchall()
        )
        self.connection.execute(
            "DELETE FROM sc_search_runs WHERE run_id = ?",
            (run.run_id.value,),
        )
        for prior_command in prior_commands:
            self.connection.execute(
                "DELETE FROM durable_commands WHERE command_id = ?",
                (prior_command,),
            )
        self._delete_orphans()
        self.faults.hit(FaultPoint.AFTER_PROJECTION_BEFORE_RECEIPT)
        readback = self.connection.execute(
            """
            SELECT canonical_bytes FROM sc_no_order_closed_audits
            WHERE audit_id = ?
            """,
            (audit_id.value,),
        ).fetchone()
        if readback is None or bytes(readback[0]) != material:
            raise SalesCreditRepositoryError("NO_ORDER_CLOSURE_READBACK_FAILED")
        return record

    def purge_no_order_audit(
        self,
        *,
        audit_id: EvidenceId,
        now: CanonicalTimestamp,
    ) -> int:
        if type(audit_id) is not EvidenceId or type(now) is not CanonicalTimestamp:
            raise SalesCreditRepositoryError("NO_ORDER_PURGE_INPUT_INVALID")
        audit = self.connection.execute(
            """
            SELECT command_id, closed_at, purge_eligible_at
            FROM sc_no_order_closed_audits WHERE audit_id = ?
            """,
            (audit_id.value,),
        ).fetchone()
        if audit is None:
            return 0
        eligible = CanonicalTimestamp(str(audit[2]))
        if (now.epoch_seconds, now.nanosecond) < (
            eligible.epoch_seconds,
            eligible.nanosecond,
        ):
            return 0
        self.faults.hit(FaultPoint.DURING_CASE_PURGE)
        receipt_ids = tuple(
            str(row[0])
            for row in self.connection.execute(
                """
                SELECT command_id FROM durable_receipt_owners
                WHERE owner_domain = 'SYSTEM' AND owner_id = ?
                """,
                (audit_id.value,),
            ).fetchall()
        )
        deleted = self.connection.execute(
            "DELETE FROM sc_no_order_closed_audits WHERE audit_id = ?",
            (audit_id.value,),
        ).rowcount
        for command_id in {*receipt_ids, str(audit[0])}:
            self.connection.execute(
                "DELETE FROM durable_commands WHERE command_id = ?",
                (command_id,),
            )
        business_date = business_local_date(
            CanonicalTimestamp(str(audit[1]))
        ).isoformat()
        self.connection.execute(
            """
            INSERT INTO sc_daily_aggregates (business_date, result_class, occurrence_count)
            VALUES (?, 'PURGED_NO_ORDER_AUDIT', 1)
            ON CONFLICT (business_date, result_class)
            DO UPDATE SET occurrence_count = occurrence_count + 1
            """,
            (business_date,),
        )
        self.faults.hit(FaultPoint.DURING_CASE_PURGE)
        return int(deleted)

    def _delete_orphans(
        self,
        *,
        search_run_ids: tuple[str, ...] = (),
    ) -> tuple[int, int, int, int]:
        evaluation_count = self.connection.execute(
            """
            DELETE FROM sc_evaluations
            WHERE NOT EXISTS (
                SELECT 1 FROM sc_case_evaluations AS owned
                WHERE owned.evaluation_id = sc_evaluations.evaluation_id
            )
            """
        ).rowcount
        evidence_count = self.connection.execute(
            """
            DELETE FROM sc_evidence_events
            WHERE NOT EXISTS (
                SELECT 1 FROM sc_case_evidence AS owned
                WHERE owned.evidence_id = sc_evidence_events.evidence_id
            )
            """
        ).rowcount
        snapshot_count = self.connection.execute(
            """
            DELETE FROM sc_snapshots
            WHERE NOT EXISTS (
                SELECT 1 FROM sc_case_snapshots AS owned
                WHERE owned.snapshot_id = sc_snapshots.snapshot_id
            )
            AND NOT EXISTS (
                SELECT 1 FROM sc_replacement_candidates AS candidate
                WHERE candidate.snapshot_id = sc_snapshots.snapshot_id
            )
            """
        ).rowcount
        for run_id in search_run_ids:
            self.connection.execute(
                """
                DELETE FROM sc_search_runs
                WHERE run_id = ?
                AND NOT EXISTS (
                    SELECT 1 FROM sc_case_search_runs AS owned
                    WHERE owned.run_id = sc_search_runs.run_id
                )
                AND NOT EXISTS (
                    SELECT 1 FROM sc_replacement_candidates AS candidate
                    WHERE candidate.replacement_run_id = sc_search_runs.run_id
                )
                AND NOT EXISTS (
                    SELECT 1 FROM sc_active_replacement_links AS active_link
                    WHERE active_link.replacement_run_id = sc_search_runs.run_id
                )
                """,
                (run_id,),
            )
        interaction_count = self.connection.execute(
            """
            DELETE FROM sc_interactions
            WHERE NOT EXISTS (
                SELECT 1 FROM sc_case_interactions AS owned
                WHERE owned.interaction_id = sc_interactions.interaction_id
            )
            AND NOT EXISTS (
                SELECT 1 FROM sc_search_identifiers AS searched
                WHERE searched.interaction_id = sc_interactions.interaction_id
            )
            """
        ).rowcount
        return (interaction_count, snapshot_count, evidence_count, evaluation_count)

    def purge_case(self, *, order_id: OrderId, now: CanonicalTimestamp) -> SalesCreditPurgeResult:
        if type(order_id) is not OrderId or type(now) is not CanonicalTimestamp:
            raise SalesCreditRepositoryError("PURGE_INPUT_INVALID")
        audit = self.connection.execute(
            """
            SELECT audit_id, closed_at, purge_eligible_at
            FROM sc_closed_audits WHERE order_id = ?
            """,
            (order_id.value,),
        ).fetchone()
        if audit is None:
            return SalesCreditPurgeResult(0, 0, 0, 0, 0, 0, 0)
        eligible = CanonicalTimestamp(str(audit[2]))
        if (now.epoch_seconds, now.nanosecond) < (eligible.epoch_seconds, eligible.nanosecond):
            return SalesCreditPurgeResult(0, 0, 0, 0, 0, 0, 0)
        self.faults.hit(FaultPoint.DURING_CASE_PURGE)
        receipt_ids = tuple(
            str(row[0])
            for row in self.connection.execute(
                """
                SELECT command_id FROM durable_receipt_owners
                WHERE owner_domain = 'SALES_CREDIT' AND owner_id = ?
                """,
                (order_id.value,),
            ).fetchall()
        )
        replacement_links = tuple(
            (str(row[0]), str(row[1]))
            for row in self.connection.execute(
                """
                SELECT candidate_order_id, replacement_run_id
                FROM sc_active_replacement_links
                WHERE parent_order_id = ? ORDER BY candidate_order_id
                """,
                (order_id.value,),
            ).fetchall()
        )
        for candidate_order_id, replacement_run_id in replacement_links:
            candidate = OrderId(candidate_order_id)
            retained_child = self.get_case(candidate)
            if (
                retained_child is None
                or retained_child.replacement_parent != order_id
            ):
                raise SalesCreditRepositoryError("REPLACEMENT_DETACH_MISMATCH")
            if (now.epoch_seconds, now.nanosecond) < (
                retained_child.updated_at.epoch_seconds,
                retained_child.updated_at.nanosecond,
            ):
                raise SalesCreditPersistenceConflict(
                    "REPLACEMENT_DETACH_TIME_REGRESSION"
                )
            detach_event_id, detach_command_id = _replacement_detach_identity(
                order_id,
                candidate,
                retained_child.last_event_id,
            )
            detach_sequence = retained_child.last_event_sequence + 1
            self._append_event(
                event_id=detach_event_id,
                order_id=candidate,
                sequence=detach_sequence,
                predecessor=retained_child.last_event_id,
                event_kind="REPLACEMENT_PARENT_DETACHED",
                workflow=retained_child.workflow_state,
                attribution=retained_child.attribution,
                value_status=retained_child.order_value_status,
                human_outcome=None,
                evaluation_id=retained_child.current_evaluation_id,
                replacement_parent=None,
                occurred_at=now,
                command_id=detach_command_id,
            )
            cursor = self.connection.execute(
                """
                UPDATE sc_cases
                SET projection_version = projection_version + 1,
                    replacement_parent_order_id = NULL,
                    last_event_sequence = ?, last_event_id = ?, updated_at = ?
                WHERE order_id = ?
                  AND replacement_parent_order_id = ?
                  AND projection_version = ?
                  AND last_event_sequence = ?
                  AND last_event_id = ?
                """,
                (
                    detach_sequence,
                    detach_event_id.value,
                    now.value,
                    candidate_order_id,
                    order_id.value,
                    retained_child.projection_version,
                    retained_child.last_event_sequence,
                    retained_child.last_event_id.value,
                ),
            )
            if cursor.rowcount != 1:
                raise SalesCreditPersistenceConflict("CASE_PROJECTION_CONFLICT")
            self.faults.hit(FaultPoint.AFTER_PROJECTION_BEFORE_RECEIPT)
            self.connection.execute(
                """
                DELETE FROM sc_case_search_runs
                WHERE order_id = ? AND run_id = ?
                """,
                (candidate_order_id, replacement_run_id),
            )
            self.connection.execute(
                """
                DELETE FROM sc_active_replacement_links
                WHERE candidate_order_id = ? AND parent_order_id = ?
                """,
                (candidate_order_id, order_id.value),
            )
            detached_child = self.get_case(candidate)
            if (
                detached_child is None
                or detached_child.projection_version
                != retained_child.projection_version + 1
                or detached_child.workflow_state is not retained_child.workflow_state
                or detached_child.attribution is not retained_child.attribution
                or detached_child.order_value_status
                is not retained_child.order_value_status
                or detached_child.placed_value != retained_child.placed_value
                or detached_child.manager_occurrence_id
                != retained_child.manager_occurrence_id
                or detached_child.current_evaluation_id
                != retained_child.current_evaluation_id
                or detached_child.replacement_parent is not None
                or detached_child.last_event_sequence != detach_sequence
                or detached_child.last_event_id != detach_event_id
                or detached_child.created_at != retained_child.created_at
                or detached_child.updated_at != now
            ):
                raise SalesCreditRepositoryError("REPLACEMENT_DETACH_MISMATCH")
        self.connection.execute("DELETE FROM sc_case_events WHERE order_id = ?", (order_id.value,))
        closed_deleted = self.connection.execute(
            "DELETE FROM sc_closed_audits WHERE order_id = ?", (order_id.value,)
        ).rowcount
        cases_deleted = self.connection.execute(
            "DELETE FROM sc_cases WHERE order_id = ?", (order_id.value,)
        ).rowcount
        for command_id in receipt_ids:
            self.connection.execute(
                "DELETE FROM durable_commands WHERE command_id = ?",
                (command_id,),
            )
        interactions, snapshots, evidence, evaluations = self._delete_orphans(
            search_run_ids=tuple(run_id for _candidate, run_id in replacement_links)
        )
        business_date = business_local_date(
            CanonicalTimestamp(str(audit[1]))
        ).isoformat()
        self.connection.execute(
            """
            INSERT INTO sc_daily_aggregates (business_date, result_class, occurrence_count)
            VALUES (?, 'PURGED_CLOSED_CASE', 1)
            ON CONFLICT (business_date, result_class)
            DO UPDATE SET occurrence_count = occurrence_count + 1
            """,
            (business_date,),
        )
        self.faults.hit(FaultPoint.DURING_CASE_PURGE)
        return SalesCreditPurgeResult(
            cases_deleted,
            closed_deleted,
            interactions,
            snapshots,
            evidence,
            evaluations,
            len(receipt_ids),
        )

    def get_case(self, order_id: OrderId) -> StoredSalesCreditCase | None:
        if type(order_id) is not OrderId:
            raise SalesCreditRepositoryError("ORDER_ID_INVALID")
        row = self.connection.execute(
            "SELECT * FROM sc_cases WHERE order_id = ?",
            (order_id.value,),
        ).fetchone()
        if row is None:
            return None
        return StoredSalesCreditCase(
            order_id=OrderId(str(row["order_id"])),
            projection_version=int(row["projection_version"]),
            workflow_state=WorkflowState(str(row["workflow_state"])),
            attribution=AttributionClassification(str(row["attribution"])),
            order_value_status=OrderValueStatus(str(row["order_value_status"])),
            placed_value=_money_from_row(
                row["placed_minor_units"],
                row["placed_currency"],
                row["placed_registry_version"],
                row["placed_scale"],
            ),
            manager_occurrence_id=(
                None
                if row["manager_occurrence_id"] is None
                else EvidenceId(str(row["manager_occurrence_id"]))
            ),
            replacement_parent=(
                None
                if row["replacement_parent_order_id"] is None
                else OrderId(str(row["replacement_parent_order_id"]))
            ),
            current_evaluation_id=(
                None
                if row["current_evaluation_id"] is None
                else EvaluationId(str(row["current_evaluation_id"]))
            ),
            last_event_sequence=int(row["last_event_sequence"]),
            last_event_id=EvidenceId(str(row["last_event_id"])),
            created_at=CanonicalTimestamp(str(row["created_at"])),
            updated_at=CanonicalTimestamp(str(row["updated_at"])),
        )

    def manager_outcomes(
        self,
        order_id: OrderId,
        *,
        limit: int,
    ) -> tuple[ManagerOutcome, ...]:
        """Return bounded outcomes after exact canonical/projection reconciliation."""

        if type(order_id) is not OrderId or type(limit) is not int or limit < 1:
            raise SalesCreditRepositoryError("MANAGER_OUTCOME_READ_INVALID")
        rows = self.connection.execute(
            "SELECT * FROM sc_manager_outcomes WHERE order_id=? "
            "ORDER BY decided_at, occurrence_id LIMIT ?",
            (order_id.value, limit + 1),
        ).fetchall()
        if len(rows) > limit:
            raise SalesCreditRepositoryError("MANAGER_OUTCOME_READ_LIMIT_EXCEEDED")
        return tuple(_manager_outcome_from_row(row) for row in rows)

    def case_history(self, order_id: OrderId) -> tuple[StoredSalesCreditEvent, ...]:
        if type(order_id) is not OrderId:
            raise SalesCreditRepositoryError("ORDER_ID_INVALID")
        rows = self.connection.execute(
            "SELECT * FROM sc_case_events WHERE order_id = ? ORDER BY sequence",
            (order_id.value,),
        ).fetchall()
        return tuple(
            StoredSalesCreditEvent(
                event_id=EvidenceId(str(row["event_id"])),
                order_id=OrderId(str(row["order_id"])),
                sequence=int(row["sequence"]),
                predecessor_event_id=(
                    None
                    if row["predecessor_event_id"] is None
                    else EvidenceId(str(row["predecessor_event_id"]))
                ),
                event_kind=str(row["event_kind"]),
                workflow_state=WorkflowState(str(row["workflow_state"])),
                attribution=AttributionClassification(str(row["attribution"])),
                order_value_status=OrderValueStatus(str(row["order_value_status"])),
                human_outcome=(
                    None
                    if row["manager_outcome"] is None
                    else HumanOutcomeType(str(row["manager_outcome"]))
                ),
                current_evaluation_id=(
                    None
                    if row["current_evaluation_id"] is None
                    else EvaluationId(str(row["current_evaluation_id"]))
                ),
                replacement_parent_present=bool(
                    int(row["replacement_parent_present"])
                ),
                occurred_at=CanonicalTimestamp(str(row["occurred_at"])),
                command_id=str(row["command_id"]),
            )
            for row in rows
        )


__all__ = [
    "SalesCreditPersistenceConflict",
    "SalesCreditRepository",
    "SalesCreditRepositoryError",
]
