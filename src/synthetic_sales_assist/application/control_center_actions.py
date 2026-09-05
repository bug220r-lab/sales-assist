"""Thin M7 adapters over committed local synthetic services and reducers."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path
from typing import Protocol, cast

from synthetic_sales_assist.doi.evaluator import evaluate_doi
from synthetic_sales_assist.doi.models import (
    ActionContextKind,
    DOIActionContext,
    DOIActionContextEvent,
    DOICaseAdmissionProof,
    DOICaseSourceBinding,
    DOIEvaluationInput,
    DOIHumanFactEvent,
    DOIHumanFactHistory,
    DOIOccurrenceGuard,
    DOIOpportunity,
    HumanFactEventType,
    HumanFactResultCode,
    HumanFactUsageKind,
    OpportunityType,
    ScenarioSelection,
    ScenarioSelectionState,
    StructuredHumanFact,
    reduce_human_fact,
    verify_action_context_opening_authority,
    verify_synthetic_human_authority,
)
from synthetic_sales_assist.domain.canonical import canonical_json_bytes
from synthetic_sales_assist.domain.idempotency import (
    DigestCollisionError,
    IdempotencyConflictError,
    NaturalKey,
)
from synthetic_sales_assist.domain.identities import (
    EvaluationId,
    EvidenceId,
    InteractionId,
    OrderId,
    RepId,
)
from synthetic_sales_assist.domain.numeric import CURRENCY_REGISTRY, Money
from synthetic_sales_assist.domain.records import (
    SourceKind,
    SourceObjectNamespace,
    SourceRef,
)
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp
from synthetic_sales_assist.persistence.backup import (
    BackupError,
    create_backup,
    verify_backup,
)
from synthetic_sales_assist.persistence.database import SQLiteDatabase
from synthetic_sales_assist.persistence.doi_repository import (
    DOIPersistenceConflict,
    DOIPersistenceError,
    DOIRepository,
    decode_payload,
)
from synthetic_sales_assist.persistence.idempotency import SQLiteIdempotencyRepository
from synthetic_sales_assist.persistence.sales_credit_repository import (
    SalesCreditPersistenceConflict,
    SalesCreditRepositoryError,
)
from synthetic_sales_assist.persistence.sales_credit_services import (
    SalesCreditPersistenceService,
)
from synthetic_sales_assist.sales_credit.models import HumanOutcomeType, ManagerOutcome


HUMAN_ACTION_RESULT_SCHEMA_VERSION = "synthetic-sales-assist-human-action-result/v1"
DOI_SELECTION_COMMAND_SCHEMA_VERSION = "synthetic-sales-assist-doi-selection-command/v1"
BACKUP_ACTION_RESULT_SCHEMA_VERSION = "synthetic-sales-assist-backup-action-result/v1"


class ScenarioSelectionSource(Protocol):
    """Internal source resolver; no source member crosses the HTTP boundary."""

    def doi_selection_input(self, order_id: str) -> DOIEvaluationInput: ...


class ControlCenterActionError(RuntimeError):
    """Closed action failure carrying only a stable safe code and category."""

    def __init__(self, code: str, category: str = "INVALID") -> None:
        self.code = code
        self.category = category
        super().__init__(code)


def _token(*parts: str) -> str:
    material = "\n".join(parts).encode("ascii")
    return hashlib.sha256(material).hexdigest().upper()[:32]


def _action_result(
    *,
    command_id: str,
    recorded_at: CanonicalTimestamp,
    replayed: bool,
    subject_id: str,
    evaluation_id: str | None = None,
) -> dict[str, object]:
    return {
        "command_id": command_id,
        "evaluation_id": evaluation_id,
        "recorded_at": recorded_at.value,
        "replayed": replayed,
        "schema_version": HUMAN_ACTION_RESULT_SCHEMA_VERSION,
        "status": "EXACT_REPLAY" if replayed else "RECORDED",
        "subject_id": subject_id,
    }


class ControlCenterActions:
    """No-rule application composition for the exact M7 rendered actions."""

    def __init__(
        self,
        database: SQLiteDatabase,
        *,
        scenario_application: ScenarioSelectionSource | None = None,
    ) -> None:
        if type(database) is not SQLiteDatabase:
            raise ControlCenterActionError("DATABASE_INVALID")
        self.database = database
        self.scenario_application = scenario_application

    def record_sales_credit_manager_outcome(
        self,
        order_id: str,
        *,
        actor_id: str,
        outcome: str,
        amount_minor_units: int | None,
        currency_code: str | None,
        request_key: str,
        confirmed: bool,
        decided_at: str,
    ) -> dict[str, object]:
        if confirmed is not True:
            raise ControlCenterActionError("CONFIRMATION_REQUIRED")
        try:
            key = NaturalKey("control_center.sc_manager_outcome", (request_key,))
            del key
            accepted_order = OrderId(order_id)
            actor = RepId(actor_id)
            accepted_outcome = HumanOutcomeType(outcome)
            timestamp = CanonicalTimestamp(decided_at)
        except (TypeError, ValueError):
            raise ControlCenterActionError("MANAGER_OUTCOME_INPUT_INVALID") from None
        amount: Money | None = None
        if accepted_outcome is HumanOutcomeType.PARTIAL:
            if type(amount_minor_units) is not int or type(currency_code) is not str:
                raise ControlCenterActionError("MANAGER_OUTCOME_MONEY_REQUIRED")
            definition = CURRENCY_REGISTRY.get(currency_code)
            if definition is None:
                raise ControlCenterActionError("MANAGER_OUTCOME_CURRENCY_INVALID")
            try:
                amount = Money.from_minor_units(
                    amount_minor_units,
                    currency_code=definition.code,
                    registry_version=definition.registry_version,
                    scale=definition.scale,
                )
            except ValueError:
                raise ControlCenterActionError("MANAGER_OUTCOME_MONEY_INVALID") from None
        elif amount_minor_units is not None or currency_code is not None:
            raise ControlCenterActionError("MANAGER_OUTCOME_MONEY_PROHIBITED")
        occurrence = EvidenceId(
            f"SYN-EVIDENCE-M7-SC-OUTCOME-{_token(order_id, request_key)}"
        )
        manager_outcome = ManagerOutcome(
            occurrence_id=occurrence,
            outcome=accepted_outcome,
            decided_at=timestamp,
            actor=actor,
            recorded_at=timestamp,
            approved_amount=amount,
            controlled_reason=None,
            active_note=None,
        )
        try:
            result = SalesCreditPersistenceService(self.database).record_manager_outcome(
                order_id=accepted_order,
                outcome=manager_outcome,
                request_key=request_key,
            )
        except SalesCreditPersistenceConflict as exc:
            raise ControlCenterActionError(str(exc), "CONFLICT") from None
        except IdempotencyConflictError as exc:
            raise ControlCenterActionError(exc.code, "CONFLICT") from None
        except SalesCreditRepositoryError as exc:
            raise ControlCenterActionError(str(exc), "UNAVAILABLE") from None
        return _action_result(
            command_id=result.command_id,
            recorded_at=result.recorded_at,
            replayed=result.replayed,
            subject_id=order_id,
        )

    def _selection_source(self, order_id: str) -> DOIEvaluationInput:
        provider = self.scenario_application
        if provider is None:
            raise ControlCenterActionError("DOI_SOURCE_CONTEXT_UNAVAILABLE", "UNAVAILABLE")
        try:
            request = provider.doi_selection_input(order_id)
        except Exception as exc:
            category = str(getattr(exc, "category", "UNAVAILABLE"))
            code = str(getattr(exc, "code", "DOI_SOURCE_CONTEXT_UNAVAILABLE"))
            raise ControlCenterActionError(code, category) from None
        if type(request) is not DOIEvaluationInput:
            raise ControlCenterActionError("DOI_SOURCE_CONTEXT_INVALID", "UNAVAILABLE")
        return request

    @staticmethod
    def _context_kind(opportunity_type: OpportunityType) -> ActionContextKind:
        if opportunity_type is OpportunityType.FULFILLMENT_SPLIT:
            return ActionContextKind.FULFILLMENT_SPLIT_REVIEW
        if opportunity_type is OpportunityType.DS_SEPARATION:
            return ActionContextKind.DS_SEPARATION_REVIEW
        if opportunity_type in {
            OpportunityType.EXACT_MFG_ALTERNATE,
            OpportunityType.MFG_CROSS_REFERENCE,
            OpportunityType.MFG_SUPERSESSION,
            OpportunityType.FUNCTIONAL_ALTERNATE,
        }:
            return ActionContextKind.SUBSTITUTION
        raise ControlCenterActionError("DOI_SELECTION_CONTEXT_UNAVAILABLE", "UNAVAILABLE")

    @staticmethod
    def _opportunity_signature(opportunity: DOIOpportunity) -> bytes:
        value = opportunity.to_dict()
        value.pop("opportunity_id")
        return canonical_json_bytes(value, expected_members=set(value))

    def record_doi_overlap_selection(
        self,
        case_id: str,
        *,
        evaluation_id: str,
        actor_id: str,
        selected_opportunity_id: str,
        option_opportunity_ids: tuple[str, ...],
        request_key: str,
        confirmed: bool,
        occurred_at: str,
    ) -> dict[str, object]:
        if confirmed is not True:
            raise ControlCenterActionError("CONFIRMATION_REQUIRED")
        try:
            accepted_case_id = EvidenceId(case_id)
            accepted_evaluation_id = EvaluationId(evaluation_id)
            actor = RepId(actor_id)
            occurred = CanonicalTimestamp(occurred_at)
            NaturalKey("control_center.doi_selection", (request_key,))
            selected_id = EvidenceId(selected_opportunity_id)
            option_ids = tuple(EvidenceId(value) for value in option_opportunity_ids)
        except (TypeError, ValueError):
            raise ControlCenterActionError("DOI_SELECTION_INPUT_INVALID") from None
        option_values = tuple(item.value for item in option_ids)
        if (
            type(option_opportunity_ids) is not tuple
            or len(option_ids) < 2
            or option_values != tuple(sorted(option_values))
            or len(option_values) != len(set(option_values))
            or selected_id not in option_ids
        ):
            raise ControlCenterActionError("DOI_SELECTION_OPTIONS_INVALID")

        with self.database.read() as connection:
            row = connection.execute(
                "SELECT order_id FROM doi_cases WHERE case_id=?",
                (case_id,),
            ).fetchone()
            if row is None:
                raise ControlCenterActionError("DOI_CASE_NOT_FOUND", "NOT_FOUND")
            order_id = str(row[0])
            repository = DOIRepository(connection)
            retained_case = repository.get_case(order_id)
            if retained_case is None or retained_case.current_evaluation_id is None:
                raise ControlCenterActionError("DOI_CASE_NOT_FOUND", "NOT_FOUND")
            retained_evaluation = repository.get_evaluation(evaluation_id)
            if retained_evaluation is None:
                raise ControlCenterActionError("DOI_EVALUATION_NOT_FOUND", "NOT_FOUND")
            retained_snapshot = repository.get_snapshot(
                retained_evaluation.snapshot_id.to_json_value()
            )
            if retained_snapshot is None:
                raise ControlCenterActionError("DOI_SNAPSHOT_NOT_FOUND", "NOT_FOUND")
            source_row = connection.execute(
                "SELECT record_payload FROM doi_case_artifacts "
                "WHERE case_id=? AND artifact_kind='CASE_SOURCE_BINDING' "
                "ORDER BY artifact_pk DESC LIMIT 1",
                (case_id,),
            ).fetchone()
            if source_row is not None:
                source_binding = decode_payload(source_row[0], DOICaseSourceBinding)
            else:
                source_refs = retained_snapshot.completeness_proof.source_refs
                if len(source_refs) != 1:
                    raise ControlCenterActionError(
                        "DOI_CASE_SOURCE_INVALID",
                        "UNAVAILABLE",
                    )
                source = source_refs[0]
                suffix = _token(case_id, source.source_ref_id.value)
                admission = DOICaseAdmissionProof(
                    proof_id=EvidenceId(
                        f"SYN-EVIDENCE-M7-DOI-ADMISSION-PROOF-{suffix}"
                    ),
                    case_id=accepted_case_id,
                    order_id=retained_case.order_id,
                    source=source,
                    completeness_proof=retained_snapshot.completeness_proof,
                    admitted_at=retained_snapshot.source_observed_at,
                )
                source_binding = DOICaseSourceBinding(
                    binding_id=EvidenceId(
                        f"SYN-EVIDENCE-M7-DOI-CASE-SOURCE-{suffix}"
                    ),
                    case_id=accepted_case_id,
                    order_id=retained_case.order_id,
                    source=source,
                    admission_proof=admission,
                )

        if (
            retained_case.case_id != accepted_case_id
            or retained_evaluation.evaluation_id != accepted_evaluation_id
            or retained_evaluation.order_id != retained_case.order_id
            or retained_evaluation.scenario_selection_state
            is not ScenarioSelectionState.REQUIRED
        ):
            raise ControlCenterActionError("DOI_SELECTION_NOT_REQUIRED", "CONFLICT")
        retained_options = tuple(
            sorted(
                (item.opportunity_id for item in retained_evaluation.opportunities),
                key=lambda item: item.value,
            )
        )
        if option_ids != retained_options:
            raise ControlCenterActionError("DOI_SELECTION_OPTIONS_STALE", "CONFLICT")

        base_request = self._selection_source(order_id)
        if (
            base_request.snapshot.hash_binding() != retained_snapshot.hash_binding()
            or base_request.snapshot.snapshot_id != retained_evaluation.snapshot_id
        ):
            raise ControlCenterActionError("DOI_SOURCE_CONTEXT_STALE", "CONFLICT")

        material_value = {
            "actor_id": actor_id,
            "case_id": case_id,
            "confirmed": True,
            "current_evaluation_id": evaluation_id,
            "occurred_at": occurred.value,
            "option_opportunity_ids": list(option_values),
            "schema_version": DOI_SELECTION_COMMAND_SCHEMA_VERSION,
            "selected_opportunity_id": selected_opportunity_id,
        }
        command_bytes = canonical_json_bytes(
            material_value,
            expected_members=set(material_value),
        )
        token = hashlib.sha256(command_bytes).hexdigest().upper()[:32]
        new_evaluation_id = EvaluationId(f"SYN-EVALUATION-M7-DOI-SELECTION-{token}")

        prospective_request = replace(
            base_request,
            evaluation_id=new_evaluation_id,
            evaluated_at=occurred,
            scenario_selection=None,
            human_facts=(),
        )
        prospective_evaluation = evaluate_doi(prospective_request)
        prospective_output = prospective_evaluation.output_dict()
        retained_output = retained_evaluation.output_dict()
        for member in ("explanation", "opportunities"):
            prospective_output.pop(member)
            retained_output.pop(member)
        if prospective_output != retained_output:
            raise ControlCenterActionError("DOI_SOURCE_CONTEXT_STALE", "CONFLICT")
        retained_by_signature = {
            self._opportunity_signature(item): item
            for item in retained_evaluation.opportunities
        }
        prospective_by_signature = {
            self._opportunity_signature(item): item
            for item in prospective_evaluation.opportunities
        }
        if (
            len(retained_by_signature) != len(retained_evaluation.opportunities)
            or len(prospective_by_signature) != len(prospective_evaluation.opportunities)
            or frozenset(retained_by_signature) != frozenset(prospective_by_signature)
        ):
            raise ControlCenterActionError("DOI_SELECTION_OPTIONS_STALE", "CONFLICT")
        selected_signature = next(
            self._opportunity_signature(item)
            for item in retained_evaluation.opportunities
            if item.opportunity_id == selected_id
        )
        selected_prospective_id = prospective_by_signature[
            selected_signature
        ].opportunity_id
        prospective_options = tuple(
            sorted(
                (item.opportunity_id for item in prospective_evaluation.opportunities),
                key=lambda item: item.value,
            )
        )

        context_owner = next(
            (
                item
                for item in prospective_evaluation.opportunities
                if item.opportunity_type
                in {
                    OpportunityType.FULFILLMENT_SPLIT,
                    OpportunityType.DS_SEPARATION,
                    OpportunityType.EXACT_MFG_ALTERNATE,
                    OpportunityType.MFG_CROSS_REFERENCE,
                    OpportunityType.MFG_SUPERSESSION,
                    OpportunityType.FUNCTIONAL_ALTERNATE,
                }
            ),
            None,
        )
        if context_owner is None:
            raise ControlCenterActionError("DOI_SELECTION_CONTEXT_UNAVAILABLE", "UNAVAILABLE")

        interaction_id = InteractionId(f"SYN-INTERACTION-M7-DOI-SELECTION-{token}")
        interaction_source = SourceRef.create(
            source_ref_id=EvidenceId(
                f"SYN-EVIDENCE-M7-DOI-SELECTION-SOURCE-{token}"
            ),
            source_kind=SourceKind.SYNTHETIC_INTERACTION_FIXTURE,
            object_namespace=SourceObjectNamespace.SYNTHETIC_INTERACTION,
            object_id=interaction_id,
        )
        prospective_case = replace(
            retained_case,
            current_evaluation_id=new_evaluation_id,
        )
        authorization = verify_action_context_opening_authority(
            authorization_id=EvidenceId(
                f"SYN-EVIDENCE-M7-DOI-SELECTION-OPEN-AUTH-{token}"
            ),
            attempt_intent_id=interaction_id,
            case=prospective_case,
            case_source_binding=source_binding,
            evaluation=prospective_evaluation,
            opportunity=context_owner,
            context_kind=self._context_kind(context_owner.opportunity_type),
            actor=actor,
            granted_at=occurred,
            authority_source=interaction_source,
        )
        context_id = EvidenceId(f"SYN-EVIDENCE-M7-DOI-SELECTION-CONTEXT-{token}")
        context_event_id = EvidenceId(
            f"SYN-EVIDENCE-M7-DOI-SELECTION-CONTEXT-EVENT-{token}"
        )
        context_guard = DOIOccurrenceGuard(
            guard_id=context_event_id,
            owner_id=context_id,
            occurrence_id=interaction_id,
            source=interaction_source,
        )
        context_event = DOIActionContextEvent.opened(
            event_id=context_event_id,
            action_context_id=context_id,
            opening_authorization=authorization,
            created_at=occurred,
            guard=context_guard,
        )
        context = DOIActionContext.from_event(context_event)
        human_authority = verify_synthetic_human_authority(
            grant_id=EvidenceId(f"SYN-EVIDENCE-M7-DOI-SELECTION-GRANT-{token}"),
            actor=actor,
            action_context=context,
            granted_at=occurred,
            authority_source=interaction_source,
        )
        fact = StructuredHumanFact.create(
            fact_id=EvidenceId(f"SYN-EVIDENCE-M7-DOI-SELECTION-FACT-{token}"),
            action_context=context,
            evaluation_id=new_evaluation_id,
            usage_kind=HumanFactUsageKind.SCENARIO_SELECTION,
            result_code=HumanFactResultCode.SCENARIO_SELECTED,
            authority_grant=human_authority,
            occurred_at=occurred,
            source=interaction_source,
        )
        fact_stream_id = EvidenceId(
            f"SYN-EVIDENCE-M7-DOI-SELECTION-FACT-STREAM-{token}"
        )
        fact_event_id = EvidenceId(
            f"SYN-EVIDENCE-M7-DOI-SELECTION-FACT-EVENT-{token}"
        )
        fact_guard = DOIOccurrenceGuard(
            guard_id=fact_event_id,
            owner_id=fact_stream_id,
            occurrence_id=interaction_id,
            source=interaction_source,
        )
        fact_event = DOIHumanFactEvent(
            event_id=fact_event_id,
            stream_id=fact_stream_id,
            event_type=HumanFactEventType.RECORDED,
            fact=fact,
            corrects_event_id=None,
            recorded_at=occurred,
            sequence=1,
            predecessor_binding=None,
            guard=fact_guard,
        )
        reduced_fact = reduce_human_fact(
            DOIHumanFactHistory(stream_id=fact_stream_id),
            fact_event,
        )
        if reduced_fact.replayed or reduced_fact.history.projection is None:
            raise ControlCenterActionError("DOI_SELECTION_FACT_INVALID", "UNAVAILABLE")
        selection = ScenarioSelection(
            selection_id=EvidenceId(f"SYN-EVIDENCE-M7-DOI-SELECTION-{token}"),
            selected_opportunity_id=selected_prospective_id,
            option_opportunity_ids=prospective_options,
            human_fact_binding=fact.hash_binding(),
        )
        selected_request = replace(
            prospective_request,
            scenario_selection=selection,
            human_facts=(fact,),
        )
        selected_evaluation = evaluate_doi(selected_request)
        if selected_evaluation.scenario_selection_state is not ScenarioSelectionState.SELECTED:
            raise ControlCenterActionError("DOI_SELECTION_NOT_APPLIED", "UNAVAILABLE")

        command_id = f"SYN-EVIDENCE-M7-DOI-COMMAND-{token}"
        result_value = {
            "case_id": case_id,
            "evaluation_id": selected_evaluation.evaluation_id.value,
            "human_fact_id": fact.fact_id.value,
            "scenario_selection_id": selection.selection_id.value,
            "schema_version": HUMAN_ACTION_RESULT_SCHEMA_VERSION,
        }
        result_bytes = canonical_json_bytes(result_value, expected_members=set(result_value))
        try:
            with self.database.write() as connection:
                repository = DOIRepository(connection)
                idempotency = SQLiteIdempotencyRepository(
                    connection,
                    command_id_factory=lambda: command_id,
                    clock=self.database.clock,
                )

                def allocate(
                    _accepted_command_id: str,
                    recorded_at: CanonicalTimestamp,
                ) -> tuple[str, bytes]:
                    current = repository.get_case(order_id)
                    if (
                        current is None
                        or current.current_evaluation_id
                        != accepted_evaluation_id
                    ):
                        raise DOIPersistenceConflict("DOI_SELECTION_PROJECTION_CHANGED")
                    repository.append_owner_event(
                        stream_family="ACTION_CONTEXT",
                        stream_id=context_id.value,
                        current_state=context.state.value,
                        event_id=context_event.event_id.value,
                        event=context_event,
                        occurred_at=occurred,
                        case_id=case_id,
                    )
                    repository.append_owner_event(
                        stream_family="HUMAN_FACT",
                        stream_id=fact_stream_id.value,
                        current_state=fact.result_code.value,
                        event_id=fact_event.event_id.value,
                        event=fact_event,
                        occurred_at=occurred,
                        case_id=case_id,
                    )
                    repository.persist_evaluation(
                        case_id=accepted_case_id,
                        snapshot=prospective_request.snapshot,
                        evaluation=selected_evaluation,
                        created_at=recorded_at,
                    )
                    return HUMAN_ACTION_RESULT_SCHEMA_VERSION, result_bytes

                result = idempotency.resolve_or_record(
                    natural_key=NaturalKey(
                        "control_center.doi_selection",
                        (request_key,),
                    ),
                    command_domain=DOI_SELECTION_COMMAND_SCHEMA_VERSION,
                    command_bytes=command_bytes,
                    owner_domain="DOI",
                    owner_id=case_id,
                    result_allocator=allocate,
                )
        except (IdempotencyConflictError, DigestCollisionError, DOIPersistenceConflict) as exc:
            raise ControlCenterActionError(
                str(getattr(exc, "code", "REQUEST_CONFLICT")),
                "CONFLICT",
            ) from None
        except DOIPersistenceError as exc:
            raise ControlCenterActionError(exc.code, "UNAVAILABLE") from None
        return _action_result(
            command_id=result.command_id,
            recorded_at=result.recorded_at,
            replayed=result.replayed,
            subject_id=case_id,
            evaluation_id=selected_evaluation.evaluation_id.value,
        )

    def create_verified_backup(
        self,
        *,
        request_key: str,
        confirmed: bool,
    ) -> dict[str, object]:
        if confirmed is not True:
            raise ControlCenterActionError("CONFIRMATION_REQUIRED")
        try:
            NaturalKey("control_center.backup", (request_key,))
        except (TypeError, ValueError):
            raise ControlCenterActionError("BACKUP_REQUEST_KEY_INVALID") from None
        token = _token("backup", request_key)
        backup_directory = self.database.path.parent.parent / "backups"
        try:
            backup_directory.mkdir(exist_ok=True)
        except OSError:
            raise ControlCenterActionError("BACKUP_DIRECTORY_UNAVAILABLE", "UNAVAILABLE") from None
        destination = backup_directory / f"m7-{token.lower()}.sqlite3"
        try:
            if destination.exists():
                receipt = verify_backup(destination, clock=self.database.clock)
                replayed = True
            else:
                receipt = create_backup(
                    self.database,
                    destination,
                    clock=self.database.clock,
                    overwrite=False,
                )
                verified = verify_backup(destination, clock=self.database.clock)
                if verified != receipt:
                    raise BackupError("BACKUP_VERIFY_MISMATCH")
                replayed = False
        except BackupError as exc:
            raise ControlCenterActionError(exc.code, "UNAVAILABLE") from None
        return {
            "backup_id": receipt.backup_id,
            "backup_sha256": receipt.backup_sha256,
            "completed_at": receipt.created_at.value,
            "location_class": "OWNED_LOCAL_BACKUP_DIRECTORY",
            "replayed": replayed,
            "schema_version": BACKUP_ACTION_RESULT_SCHEMA_VERSION,
            "status": "EXACT_REPLAY" if replayed else "RECORDED",
            "verified_schema_version": receipt.schema_version,
        }


__all__ = [
    "BACKUP_ACTION_RESULT_SCHEMA_VERSION",
    "ControlCenterActionError",
    "ControlCenterActions",
    "DOI_SELECTION_COMMAND_SCHEMA_VERSION",
    "HUMAN_ACTION_RESULT_SCHEMA_VERSION",
    "ScenarioSelectionSource",
]
