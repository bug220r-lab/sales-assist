"""Socket-neutral synthetic scenario application service.

Unevaluated source fixtures live only in a bounded process-local registry.  Once the
caller evaluates an instance, the unchanged Milestone 4 services own durable replay,
conflict, case, run, evaluation, and telemetry state.
"""

from __future__ import annotations

import hashlib
import sqlite3
import time
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Final, TypeAlias, TypeVar, cast

from synthetic_sales_assist import __version__
from synthetic_sales_assist.demos import (
    DEMO_CATALOG_VERSION,
    DemoError,
    demo_catalog,
    validate_request_key,
)
from synthetic_sales_assist.doi.demo import (
    DOI_APPLICATION_FIXTURES,
    DOIDemoFixture,
    build_doi_demo_fixture,
)
from synthetic_sales_assist.doi.models import (
    DOIEvaluation,
    DOIEvaluationInput,
    DOILineItemSnapshot,
)
from synthetic_sales_assist.domain.canonical import canonical_json_bytes, domain_hash
from synthetic_sales_assist.domain.idempotency import IdempotencyConflictError
from synthetic_sales_assist.domain.identities import EvaluationId, InteractionId, OrderId, RunId
from synthetic_sales_assist.domain.numeric import Money, Quantity
from synthetic_sales_assist.domain.observed import ObservedTaggedValue
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp
from synthetic_sales_assist.durable_demo_backend import DurableDemoAuditBackend
from synthetic_sales_assist.persistence.database import DatabaseError, SQLiteDatabase
from synthetic_sales_assist.persistence.doi_repository import (
    DOIPersistenceConflict,
    DOIPersistenceError,
    DOIRepository,
)
from synthetic_sales_assist.persistence.doi_services import DOIPersistenceService
from synthetic_sales_assist.persistence.paths import resolve_data_paths
from synthetic_sales_assist.persistence.projections import verify_sales_credit_projections
from synthetic_sales_assist.persistence.records import DurableCommandResult
from synthetic_sales_assist.persistence.sales_credit_repository import (
    SalesCreditPersistenceConflict,
    SalesCreditRepositoryError,
)
from synthetic_sales_assist.persistence.sales_credit_services import (
    SalesCreditPersistenceService,
)
from synthetic_sales_assist.persistence.schema import verify_database
from synthetic_sales_assist.persistence.telemetry import (
    ProcessingResultClass,
    ProcessingTelemetry,
    RulePack,
    TelemetryError,
    aggregate_processing_telemetry,
    record_processing_telemetry,
)
from synthetic_sales_assist.sales_credit.accumulator import CaseMutation
from synthetic_sales_assist.sales_credit.evaluator import (
    KNOWN_OTHER_REP_CATALOG,
    evaluate_sales_credit,
)
from synthetic_sales_assist.sales_credit.fixtures import milestone5_case_fixture
from synthetic_sales_assist.sales_credit.models import SalesCreditEvaluation

from .durable_registry import (
    DurableAttemptRecord,
    DurableEvaluationBinding,
    DurableEvaluationResolution,
    DurableRegistryError,
    DurableScenarioRecord,
    DurableScenarioRegistry,
)
from .health import verify_application_safety_counters
from .manifest import ordered_line_manifest_digest
from .views import (
    APPLICATION_BUILD_VERSION,
    ApplicationError,
    AttemptReceiptView,
    CompletenessView,
    EvaluationResultView,
    ExplanationView,
    FactView,
    HistoryArtifactView,
    HistoryEventView,
    HistoryView,
    InteractionView,
    LineView,
    MetricsSummaryView,
    MoneyView,
    OpportunityView,
    OrderDetailView,
    OrderSummaryView,
    ProcessingStageView,
    ReceiptSummaryView,
    RunView,
    ScenarioDescriptorView,
    SystemStatusView,
)


APPLICATION_SCENARIO_CATALOG_VERSION: Final = (
    "synthetic-sales-assist-application-scenarios/v1"
)
DEFAULT_REGISTRY_LIMIT: Final = 256
MAX_REGISTRY_LIMIT: Final = 256
MAX_HISTORY_ITEMS: Final = 256
_FULFILLMENT_SPLIT_MODES: Final = (
    "complete",
    "missing-required-section",
    "identity-mismatch",
    "duplicate-line",
    "declared-rendered-mismatch",
    "stale-source-changed",
    "dom-payload-mismatch",
    "malformed-value",
    "backend-evaluation-failure",
)
_EVALUABLE_MODES: Final = frozenset(
    {"complete", "large", "zero-relevant-lines", "observed-unknown"}
)


@dataclass(frozen=True, slots=True)
class _MalformedFixture:
    order_id: str
    mode: str

    @property
    def source_binding(self) -> str:
        material = canonical_json_bytes(
            {"mode": self.mode, "order_id": self.order_id},
            expected_members={"mode", "order_id"},
        )
        return domain_hash("m5-malformed-source/v1", material).sha256


SourceFixture: TypeAlias = CaseMutation | DOIDemoFixture | _MalformedFixture
_ObservedT = TypeVar("_ObservedT")


@dataclass(frozen=True, slots=True)
class _Instance:
    descriptor: ScenarioDescriptorView
    mode: str
    created_at: CanonicalTimestamp
    updated_at: CanonicalTimestamp
    source: SourceFixture
    latest_evaluation: EvaluationResultView | None = None
    auxiliary_event_id: str | None = None


_COMPLEXITY = {
    "sales-credit-target-rep": "BASIC",
    "sales-credit-human-review": "EDGE_CASE",
    "doi-fulfillment-split": "STANDARD",
    "doi-full-ds": "STANDARD",
    "doi-manual-review": "EDGE_CASE",
    "doi-overlap": "EDGE_CASE",
    "malformed-input": "MALFORMED",
}


def _scenario_inventory() -> tuple[ScenarioDescriptorView, ...]:
    required = tuple(
        ScenarioDescriptorView(
            alias=item.alias,
            rule_pack=item.rule_pack,
            description=item.description,
            expected_result=item.expected_result,
            collected_scenario=item.collected_scenario,
            complexity=_COMPLEXITY[item.alias],
            allowed_modes=(
                ("complete", "incomplete", "malformed")
                if item.alias == "malformed-input"
                else _FULFILLMENT_SPLIT_MODES
                if item.alias == "doi-fulfillment-split"
                else ("complete",)
            ),
        )
        for item in demo_catalog()
    )
    extras = (
        ScenarioDescriptorView(
            alias="sales-credit-cancellation-replacement",
            rule_pack="SALES_CREDIT",
            description=(
                "A canceled fictional order remains in the governed replacement window."
            ),
            expected_result="CANCELED_REPLACEMENT_WINDOW_ACTIVE",
            collected_scenario="CANCELLATION_REPLACEMENT_WINDOW",
            complexity="EDGE_CASE",
            allowed_modes=("complete",),
        ),
        *(
            ScenarioDescriptorView(
                alias=item.alias,
                rule_pack="DOI",
                description=item.description,
                expected_result={
                    "doi-long-order": "DOI_OPPORTUNITY",
                    "doi-partial-quantity": "DOI_OPPORTUNITY",
                    "doi-unknown-containment": "DOI_OPPORTUNITY",
                    "doi-dedupe-review": "DOI_MONITOR",
                    "doi-zero-lines": "DOI_MONITOR",
                }[item.alias],
                collected_scenario=item.scenario_key,
                complexity=(
                    "LARGE"
                    if item.alias == "doi-long-order"
                    else "ZERO_LINE"
                    if item.alias == "doi-zero-lines"
                    else "EDGE_CASE"
                ),
                allowed_modes={
                    "doi-long-order": ("complete", "large"),
                    "doi-partial-quantity": ("complete",),
                    "doi-unknown-containment": ("complete", "observed-unknown"),
                    "doi-dedupe-review": ("complete",),
                    "doi-zero-lines": ("complete", "zero-relevant-lines"),
                }[item.alias],
            )
            for item in DOI_APPLICATION_FIXTURES
        ),
    )
    inventory = tuple(sorted((*required, *extras), key=lambda item: item.alias))
    if len({item.alias for item in inventory}) != len(inventory):
        raise RuntimeError("APPLICATION_SCENARIO_CATALOG_DUPLICATE")
    return inventory


_SCENARIOS: Final = _scenario_inventory()
_SCENARIO_BY_ALIAS: Final = {item.alias: item for item in _SCENARIOS}
_CONFLICT_ERRORS: Final = (
    IdempotencyConflictError,
    SalesCreditPersistenceConflict,
    DOIPersistenceConflict,
)
_DATABASE_ERRORS: Final = (
    DatabaseError,
    SalesCreditRepositoryError,
    DOIPersistenceError,
    TelemetryError,
    sqlite3.DatabaseError,
)


def _timestamp(value: datetime) -> CanonicalTimestamp:
    if type(value) is not datetime or value.tzinfo is None:
        raise ApplicationError("APPLICATION_CLOCK_INVALID", "UNAVAILABLE")
    rendered = value.astimezone(timezone.utc).isoformat(timespec="microseconds")
    return CanonicalTimestamp(rendered.replace("+00:00", "Z"))


def _money(value: Money) -> MoneyView:
    return MoneyView(
        amount=f"{value.amount:.{value.scale}f}",
        currency_code=value.currency_code,
        currency_registry_version=value.registry_version,
        currency_scale=value.scale,
    )


def _fact_scalar(value: object) -> str | int | MoneyView | None:
    if value is None:
        return None
    if type(value) is Money:
        return _money(value)
    if type(value) is Quantity:
        return value.to_json_value()
    if type(value) is CanonicalTimestamp:
        return value.value
    if type(value) in {str, int}:
        return value  # type: ignore[return-value]
    enum_value = getattr(value, "value", None)
    if type(enum_value) in {str, int}:
        return enum_value  # type: ignore[return-value]
    serializer = getattr(value, "to_json_value", None)
    if callable(serializer):
        rendered = serializer()
        if type(rendered) in {str, int}:
            return rendered  # type: ignore[return-value]
    raise ApplicationError("APPLICATION_FACT_VIEW_UNAVAILABLE", "UNAVAILABLE")


def _observed(value: ObservedTaggedValue[_ObservedT]) -> FactView:
    reason = getattr(value, "reason_code", None)
    return FactView(value.tag.value, _fact_scalar(getattr(value, "value", None)), reason)


def _known(value: object) -> FactView:
    return FactView("KNOWN", _fact_scalar(value), None)


def _not_applicable() -> FactView:
    return FactView("NOT_APPLICABLE", None, None)


def _source_binding(source: SourceFixture) -> str:
    if type(source) is CaseMutation:
        return source.hash_binding().sha256
    if type(source) is DOIDemoFixture:
        return source.request.hash_binding().sha256
    return source.source_binding


def _order_id(source: SourceFixture) -> str:
    if type(source) is CaseMutation:
        return source.order_id.value
    if type(source) is DOIDemoFixture:
        return source.snapshot.order_id.to_json_value()
    return source.order_id


def _evaluation_operation_id(binding_command_id: str) -> str:
    digest = hashlib.sha256(
        b"m5-evaluation-operation/v1\n" + binding_command_id.encode("ascii")
    ).hexdigest()
    return f"SYN-EVIDENCE-M5-OPERATION-{digest.upper()[:32]}"


class ScenarioApplication:
    """Bounded, thread-safe application boundary for synthetic local adapters."""

    def __init__(
        self,
        database: SQLiteDatabase,
        *,
        registry_limit: int = DEFAULT_REGISTRY_LIMIT,
    ) -> None:
        if type(database) is not SQLiteDatabase:
            raise TypeError("DATABASE_INVALID")
        if (
            type(registry_limit) is not int
            or not 1 <= registry_limit <= MAX_REGISTRY_LIMIT
        ):
            raise ValueError("APPLICATION_REGISTRY_LIMIT_INVALID")
        self.database = database
        self.registry_limit = registry_limit
        self.sales_credit = SalesCreditPersistenceService(database)
        self.doi = DOIPersistenceService(database)
        self.malformed_backend = DurableDemoAuditBackend(database)
        self._durable_registry = DurableScenarioRegistry(
            database,
            limit=registry_limit,
        )
        self._lock = RLock()
        self._instances: dict[str, _Instance] = {}
        self._interaction_orders: dict[str, str] = {}
        self._run_orders: dict[str, str] = {}

    @classmethod
    def open(
        cls,
        data_dir: Path | None = None,
        *,
        registry_limit: int = DEFAULT_REGISTRY_LIMIT,
    ) -> ScenarioApplication:
        paths = resolve_data_paths(data_dir)
        paths.ensure_directories()
        database = SQLiteDatabase(paths.database)
        database.initialize()
        application = cls(database, registry_limit=registry_limit)
        application._restore_instances()
        return application

    def list_scenarios(self) -> tuple[ScenarioDescriptorView, ...]:
        return _SCENARIOS

    def _request_key(self, value: str | None) -> str | None:
        try:
            return validate_request_key(value)
        except DemoError:
            raise ApplicationError("REQUEST_KEY_INVALID", "INVALID") from None

    def _descriptor(self, alias: object) -> ScenarioDescriptorView:
        if type(alias) is not str:
            raise ApplicationError("SCENARIO_ALIAS_INVALID", "INVALID")
        descriptor = _SCENARIO_BY_ALIAS.get(alias)
        if descriptor is None:
            raise ApplicationError("SCENARIO_ALIAS_UNKNOWN", "NOT_FOUND")
        return descriptor

    @staticmethod
    def _build_source(
        descriptor: ScenarioDescriptorView,
        mode: str,
        instance_key: str,
    ) -> SourceFixture:
        if descriptor.rule_pack == "SALES_CREDIT":
            return milestone5_case_fixture(descriptor.alias, instance_key)
        if descriptor.alias == "malformed-input":
            return _MalformedFixture(
                order_id=f"SYN-ORDER-M5-MALFORMED-{instance_key}",
                mode=mode,
            )
        return build_doi_demo_fixture(descriptor.alias, instance_key=instance_key)

    def _instance_from_record(self, record: DurableScenarioRecord) -> _Instance:
        descriptor = self._descriptor(record.alias)
        if (
            record.catalog_version != APPLICATION_SCENARIO_CATALOG_VERSION
            or record.mode not in descriptor.allowed_modes
            or record.rule_pack != descriptor.rule_pack
        ):
            raise ApplicationError("APPLICATION_DURABLE_CATALOG_INVALID", "UNAVAILABLE")
        source = self._build_source(descriptor, record.mode, record.instance_key)
        if (
            _order_id(source) != record.order_id
            or _source_binding(source) != record.source_binding
        ):
            raise ApplicationError("APPLICATION_DURABLE_CATALOG_INVALID", "UNAVAILABLE")
        instance = _Instance(
            descriptor=descriptor,
            mode=record.mode,
            created_at=record.created_at,
            updated_at=record.created_at,
            source=source,
        )
        return self._refresh_instance(instance)[0]

    def _install_instance(self, instance: _Instance) -> None:
        order = _order_id(instance.source)
        if order in self._instances:
            raise ApplicationError("APPLICATION_INSTANCE_ID_COLLISION", "CONFLICT")
        self._instances[order] = instance
        source = instance.source
        if type(source) is CaseMutation:
            for interaction in source.interactions:
                self._interaction_orders[interaction.interaction_id.value] = order
            if source.discovery_run is not None:
                self._run_orders[source.discovery_run.run_id.value] = order
        elif type(source) is DOIDemoFixture:
            self._run_orders[source.run_start.run.run_id.value] = order

    def _restore_instances(self) -> None:
        try:
            records = self._durable_registry.list_instances()
            for record in records:
                self._install_instance(self._instance_from_record(record))
            self._reconcile_evaluation_bindings()
        except DurableRegistryError as exc:
            code = (
                "APPLICATION_REGISTRY_CAPACITY_REACHED"
                if exc.code == "DURABLE_REGISTRY_CAPACITY_REACHED"
                else "APPLICATION_DURABLE_CATALOG_INVALID"
            )
            raise ApplicationError(code, "UNAVAILABLE") from None

    def _telemetry_bound_view(
        self,
        instance: _Instance,
        view: EvaluationResultView,
        telemetry: ProcessingTelemetry,
    ) -> EvaluationResultView:
        source = instance.source
        malformed = type(source) is _MalformedFixture
        if malformed:
            stages = (
                ProcessingStageView(
                    "FAIL_CLOSED_VALIDATION",
                    telemetry.total_ns,
                    "SUCCEEDED",
                ),
            )
        else:
            stages = (
                ProcessingStageView("RULE_EVALUATION", telemetry.rule_ns, "SUCCEEDED"),
                ProcessingStageView("PERSISTENCE", telemetry.database_ns, "SUCCEEDED"),
                ProcessingStageView("TOTAL", telemetry.total_ns, "SUCCEEDED"),
            )
        accepted = replace(
            view,
            processing_stages=stages,
            replayed=telemetry.replay,
            processing_duration_ns=telemetry.total_ns,
        )
        expected_result = (
            ProcessingResultClass.FAILED_CLOSED
            if malformed
            else ProcessingResultClass.HUMAN_REVIEW
            if accepted.human_review_required
            else ProcessingResultClass.SUCCESS
        )
        expected_error = "INVALID_ORDER_NUMBER" if malformed else None
        expected_catalog = (
            DEMO_CATALOG_VERSION
            if malformed
            else APPLICATION_SCENARIO_CATALOG_VERSION
        )
        expected_pack = RulePack(instance.descriptor.rule_pack)
        expected_stages = stages
        if (
            telemetry.demo_alias != instance.descriptor.alias
            or telemetry.rule_pack is not expected_pack
            or telemetry.result_class is not expected_result
            or telemetry.human_review != accepted.human_review_required
            or telemetry.fail_closed is not malformed
            or telemetry.conflict
            or telemetry.database_error
            or telemetry.rule_version != accepted.rule_pack_version
            or telemetry.schema_version != "4"
            or telemetry.catalog_version != expected_catalog
            or telemetry.error_code != expected_error
            or telemetry.normalization_ns != 0
            or accepted.processing_stages != expected_stages
            or accepted.processing_duration_ns != telemetry.total_ns
        ):
            raise ApplicationError(
                "APPLICATION_EVALUATION_TELEMETRY_INVALID",
                "UNAVAILABLE",
            )
        if not malformed and (
            telemetry.extraction_ns != 0 or telemetry.validation_ns != 0
        ):
            raise ApplicationError(
                "APPLICATION_EVALUATION_TELEMETRY_INVALID",
                "UNAVAILABLE",
            )
        if malformed and (
            telemetry.extraction_ns != 0
            or telemetry.normalization_ns != 0
            or telemetry.rule_ns != 0
        ):
            raise ApplicationError(
                "APPLICATION_EVALUATION_TELEMETRY_INVALID",
                "UNAVAILABLE",
            )
        return accepted

    def _validated_evaluation_resolution(
        self,
        instance: _Instance,
        binding: DurableEvaluationBinding,
    ) -> DurableEvaluationResolution | None:
        resolution = self._durable_registry.evaluation_resolution(binding.command_id)
        if resolution is None:
            return None
        if (
            resolution.order_id != binding.order_id
            or resolution.telemetry_operation_id
            != _evaluation_operation_id(binding.command_id)
        ):
            raise ApplicationError(
                "APPLICATION_EVALUATION_RECOVERY_INVALID",
                "UNAVAILABLE",
            )
        attempt = self._durable_registry.attempt(
            resolution.attempt_id,
            order_id=binding.order_id,
        )
        if (
            attempt is None
            or attempt.order_id != resolution.order_id
            or attempt.outcome != resolution.outcome
            or attempt.telemetry_operation_id != resolution.telemetry_operation_id
        ):
            raise ApplicationError(
                "APPLICATION_EVALUATION_RECOVERY_INVALID",
                "UNAVAILABLE",
            )
        telemetry = self._durable_registry.processing_telemetry(
            resolution.telemetry_operation_id
        )
        if telemetry is None:
            raise ApplicationError(
                "APPLICATION_EVALUATION_TELEMETRY_INVALID",
                "UNAVAILABLE",
            )
        if resolution.outcome == "SUCCEEDED":
            if (
                attempt.evaluation is None
                or attempt.error_code is not None
                or attempt.evaluation.replayed
            ):
                raise ApplicationError(
                    "APPLICATION_EVALUATION_RECOVERY_INVALID",
                    "UNAVAILABLE",
                )
            accepted = self._telemetry_bound_view(
                instance,
                attempt.evaluation,
                telemetry,
            )
            if accepted != attempt.evaluation:
                raise ApplicationError(
                    "APPLICATION_EVALUATION_TELEMETRY_INVALID",
                    "UNAVAILABLE",
                )
        elif (
            attempt.evaluation is not None
            or attempt.auxiliary_event_id is not None
            or attempt.error_code != "IDEMPOTENCY_KEY_MATERIAL_CONFLICT"
            or telemetry.demo_alias != instance.descriptor.alias
            or telemetry.rule_pack is not RulePack(instance.descriptor.rule_pack)
            or telemetry.result_class is not ProcessingResultClass.CONFLICT
            or not telemetry.conflict
            or telemetry.human_review
            or telemetry.fail_closed
            or telemetry.database_error
            or telemetry.replay
            or telemetry.error_code != "IDEMPOTENCY_KEY_MATERIAL_CONFLICT"
            or telemetry.rule_version != "m5/conflict"
            or telemetry.catalog_version != APPLICATION_SCENARIO_CATALOG_VERSION
            or telemetry.schema_version != "4"
        ):
            raise ApplicationError(
                "APPLICATION_EVALUATION_RECOVERY_INVALID",
                "UNAVAILABLE",
            )
        return resolution

    def _recover_evaluation_binding(
        self,
        instance: _Instance,
        binding: DurableEvaluationBinding,
    ) -> None:
        started_at = _timestamp(self.database.clock())
        started = time.perf_counter_ns()
        operation_id = _evaluation_operation_id(binding.command_id)
        try:
            result, event_id, accepted_operation_id = self._evaluate_instance(
                instance,
                binding.request_key,
                started_at,
                operation_id=operation_id,
                application_replay=False,
            )
        except _CONFLICT_ERRORS:
            accepted_operation_id = self._record_closed_outcome(
                instance,
                started_at=started_at,
                started=started,
                result_class=ProcessingResultClass.CONFLICT,
                rule_version="m5/conflict",
                error_code="IDEMPOTENCY_KEY_MATERIAL_CONFLICT",
                operation_id=operation_id,
            )
            self._append_attempt(
                instance,
                outcome="CONFLICT",
                telemetry_operation_id=accepted_operation_id,
                error_code="IDEMPOTENCY_KEY_MATERIAL_CONFLICT",
                evaluation_binding_command_id=binding.command_id,
            )
            return
        except _DATABASE_ERRORS:
            raise ApplicationError(
                "APPLICATION_EVALUATION_RECOVERY_FAILED",
                "UNAVAILABLE",
            ) from None
        self._append_attempt(
            instance,
            outcome="SUCCEEDED",
            telemetry_operation_id=accepted_operation_id,
            evaluation=result,
            auxiliary_event_id=event_id,
            evaluation_binding_command_id=binding.command_id,
        )

    def _reconcile_evaluation_bindings(self) -> None:
        bindings = self._durable_registry.evaluation_bindings(
            limit=self.registry_limit * MAX_HISTORY_ITEMS,
        )
        for binding in bindings:
            instance = self._instances.get(binding.order_id)
            if (
                instance is None
                or binding.source_binding != _source_binding(instance.source)
            ):
                raise ApplicationError(
                    "APPLICATION_EVALUATION_RECOVERY_INVALID",
                    "UNAVAILABLE",
                )
            resolution = self._validated_evaluation_resolution(instance, binding)
            if resolution is None:
                self._recover_evaluation_binding(instance, binding)
        for order_id, instance in tuple(self._instances.items()):
            self._instances[order_id] = self._refresh_instance(instance)[0]

    def _refresh_instance(
        self,
        instance: _Instance,
    ) -> tuple[_Instance, tuple[DurableAttemptRecord, ...]]:
        order = _order_id(instance.source)
        try:
            attempts = self._durable_registry.attempts(
                order,
                limit=MAX_HISTORY_ITEMS,
            )
        except DurableRegistryError:
            raise ApplicationError(
                "APPLICATION_DURABLE_HISTORY_INVALID",
                "UNAVAILABLE",
            ) from None
        latest = next(
            (item.evaluation for item in reversed(attempts) if item.evaluation is not None),
            None,
        )
        auxiliary = next(
            (
                item.auxiliary_event_id
                for item in reversed(attempts)
                if item.auxiliary_event_id is not None
            ),
            None,
        )
        if latest is not None and (
            latest.order_id != order
            or latest.scenario_alias != instance.descriptor.alias
            or latest.rule_pack != instance.descriptor.rule_pack
        ):
            raise ApplicationError(
                "APPLICATION_DURABLE_HISTORY_INVALID",
                "UNAVAILABLE",
            )
        refreshed = replace(
            instance,
            latest_evaluation=latest,
            auxiliary_event_id=auxiliary,
            updated_at=(
                instance.created_at if not attempts else attempts[-1].recorded_at
            ),
        )
        return refreshed, attempts

    def _append_attempt(
        self,
        instance: _Instance,
        *,
        outcome: str,
        telemetry_operation_id: str,
        evaluation: EvaluationResultView | None = None,
        auxiliary_event_id: str | None = None,
        error_code: str | None = None,
        evaluation_binding_command_id: str | None = None,
    ) -> CanonicalTimestamp:
        try:
            return self._durable_registry.append_attempt(
                order_id=_order_id(instance.source),
                outcome=outcome,
                telemetry_operation_id=telemetry_operation_id,
                evaluation=evaluation,
                auxiliary_event_id=auxiliary_event_id,
                error_code=error_code,
                evaluation_binding_command_id=evaluation_binding_command_id,
            )
        except DurableRegistryError:
            raise ApplicationError(
                "APPLICATION_DURABLE_HISTORY_INVALID",
                "UNAVAILABLE",
            ) from None

    def instantiate(
        self,
        alias: str,
        request_key: str | None = None,
        mode: str = "complete",
    ) -> OrderDetailView:
        descriptor = self._descriptor(alias)
        key = self._request_key(request_key)
        if type(mode) is not str or mode not in descriptor.allowed_modes:
            raise ApplicationError("SCENARIO_MODE_INVALID", "INVALID")
        with self._lock:
            natural_component = key or f"anonymous-{uuid.uuid4().hex}"
            instance_key = hashlib.sha256(
                f"{alias}\n{mode}\n{natural_component}".encode("ascii")
            ).hexdigest().upper()[:24]
            source = self._build_source(descriptor, mode, instance_key)
            try:
                record = self._durable_registry.resolve_instance(
                    natural_component=natural_component,
                    alias=alias,
                    catalog_version=APPLICATION_SCENARIO_CATALOG_VERSION,
                    instance_key=instance_key,
                    mode=mode,
                    order_id=_order_id(source),
                    rule_pack=descriptor.rule_pack,
                    source_binding=_source_binding(source),
                )
            except IdempotencyConflictError:
                raise ApplicationError(
                    "IDEMPOTENCY_KEY_MATERIAL_CONFLICT",
                    "CONFLICT",
                ) from None
            except DurableRegistryError as exc:
                code = (
                    "APPLICATION_REGISTRY_CAPACITY_REACHED"
                    if exc.code == "DURABLE_REGISTRY_CAPACITY_REACHED"
                    else "APPLICATION_DURABLE_CATALOG_INVALID"
                )
                raise ApplicationError(code, "UNAVAILABLE") from None
            order = record.order_id
            retained = self._instances.get(order)
            if retained is not None:
                refreshed, _attempts = self._refresh_instance(retained)
                self._instances[order] = refreshed
                return self._detail(refreshed)
            instance = self._instance_from_record(record)
            self._install_instance(instance)
            return self._detail(instance)

    def list_orders(self) -> tuple[OrderSummaryView, ...]:
        with self._lock:
            summaries: list[OrderSummaryView] = []
            for order in sorted(self._instances):
                instance, _attempts = self._refresh_instance(self._instances[order])
                self._instances[order] = instance
                summaries.append(self._detail(instance).summary)
            return tuple(summaries)

    def _validated_order(self, value: object) -> str:
        if type(value) is not str:
            raise ApplicationError("ORDER_ID_INVALID", "INVALID")
        try:
            return OrderId(value).value
        except ValueError:
            raise ApplicationError("ORDER_ID_INVALID", "INVALID") from None

    def get_order(self, order_id: str) -> OrderDetailView:
        order = self._validated_order(order_id)
        with self._lock:
            instance = self._instances.get(order)
            if instance is None:
                raise ApplicationError("ORDER_NOT_FOUND", "NOT_FOUND")
            instance, _attempts = self._refresh_instance(instance)
            self._instances[order] = instance
            return self._detail(instance)

    def _detail(self, instance: _Instance) -> OrderDetailView:
        source = instance.source
        if type(source) is CaseMutation:
            return self._sales_credit_detail(instance, source)
        if type(source) is DOIDemoFixture:
            return self._doi_detail(instance, source)
        state = "INCOMPLETE" if source.mode == "incomplete" else "MALFORMED"
        return OrderDetailView(
            order_id=source.order_id,
            scenario_alias=instance.descriptor.alias,
            mode=instance.mode,
            rule_pack=instance.descriptor.rule_pack,
            source_status=state,
            order_status="SOURCE_REJECTED",
            created_at=instance.created_at.value,
            updated_at=instance.updated_at.value,
            lines=(),
            interaction_ids=(),
            completeness=CompletenessView(
                state=state,
                requested_order_id=source.order_id,
                observed_order_id=None,
                declared_relevant_line_count=None,
                rendered_relevant_line_count=0,
                ordered_line_manifest_digest=None,
                fixture_version="m5-malformed-fixture/v1",
                source_schema_version="synthetic-malformed-input/v1",
                source_observed_at=None,
            ),
            latest_evaluation=instance.latest_evaluation,
        )

    def _sales_credit_detail(
        self,
        instance: _Instance,
        source: CaseMutation,
    ) -> OrderDetailView:
        snapshot = source.snapshots[-1]
        lines = tuple(
            LineView(
                line_id=line.line_id.value,
                line_index=index,
                product_id=line.sku_id.value,
                quantity=_known(line.quantity),
                line_value=_known(line.line_value),
                availability=(
                    _not_applicable()
                    if line.observed_availability is None
                    else _known(line.observed_availability)
                ),
                eta=(
                    _not_applicable()
                    if line.observed_eta is None
                    else _known(line.observed_eta)
                ),
                drop_ship_state=_not_applicable(),
                activity=_not_applicable(),
            )
            for index, line in enumerate(snapshot.lines, start=1)
        )
        status = {
            "VALID": "COMPLETE",
            "PARTIAL": "INCOMPLETE",
            "INVALID": "MALFORMED",
        }[snapshot.extraction_status.value]
        return OrderDetailView(
            order_id=source.order_id.value,
            scenario_alias=instance.descriptor.alias,
            mode=instance.mode,
            rule_pack=instance.descriptor.rule_pack,
            source_status=status,
            order_status=snapshot.lifecycle_status.value,
            created_at=instance.created_at.value,
            updated_at=instance.updated_at.value,
            lines=lines,
            interaction_ids=tuple(item.interaction_id.value for item in source.interactions),
            completeness=CompletenessView(
                state=status,
                requested_order_id=source.order_id.value,
                observed_order_id=(
                    None if snapshot.order_id is None else snapshot.order_id.value
                ),
                declared_relevant_line_count=len(snapshot.lines),
                rendered_relevant_line_count=len(lines),
                ordered_line_manifest_digest=ordered_line_manifest_digest(lines),
                fixture_version="sales-credit-m5-fixture/v1",
                source_schema_version=snapshot.schema_version,
                source_observed_at=snapshot.captured_at.value,
            ),
            latest_evaluation=instance.latest_evaluation,
        )

    def _doi_detail(
        self,
        instance: _Instance,
        source: DOIDemoFixture,
    ) -> OrderDetailView:
        snapshot = source.snapshot
        lines = tuple(self._doi_line(index, line) for index, line in enumerate(snapshot.lines, 1))
        order_state = _observed(snapshot.order_state)
        proof = snapshot.completeness_proof
        state = "COMPLETE"
        observed_order_id: str | None = proof.observed_order_id.value
        declared_count: int | None = proof.declared_relevant_line_count.value
        if instance.mode == "duplicate-line" and lines:
            lines = (*lines, replace(lines[-1], line_index=len(lines) + 1))
            state = "INCOMPLETE"
        elif instance.mode == "declared-rendered-mismatch":
            declared_count = len(lines) + 1
            state = "INCOMPLETE"
        elif instance.mode == "identity-mismatch":
            mismatch_suffix = hashlib.sha256(
                snapshot.order_id.to_json_value().encode("ascii")
            ).hexdigest().upper()[:16]
            observed_order_id = f"SYN-ORDER-M5-MISMATCH-{mismatch_suffix}"
            state = "INCOMPLETE"
        elif instance.mode in {
            "missing-required-section",
            "stale-source-changed",
            "dom-payload-mismatch",
        }:
            state = "INCOMPLETE"
        elif instance.mode == "malformed-value":
            state = "MALFORMED"
            if lines:
                lines = (
                    replace(lines[0], quantity=FactView("MALFORMED", None, None)),
                    *lines[1:],
                )
        return OrderDetailView(
            order_id=snapshot.order_id.to_json_value(),
            scenario_alias=instance.descriptor.alias,
            mode=instance.mode,
            rule_pack=instance.descriptor.rule_pack,
            source_status=state,
            order_status=str(order_state.value),
            created_at=instance.created_at.value,
            updated_at=instance.updated_at.value,
            lines=lines,
            interaction_ids=(),
            completeness=CompletenessView(
                state=state,
                requested_order_id=proof.requested_order_id.value,
                observed_order_id=observed_order_id,
                declared_relevant_line_count=declared_count,
                rendered_relevant_line_count=len(lines),
                ordered_line_manifest_digest=(
                    None if state == "MALFORMED" else ordered_line_manifest_digest(lines)
                ),
                fixture_version=proof.fixture.version,
                source_schema_version=proof.schema.version,
                source_observed_at=proof.order_source_observed_at.value,
            ),
            latest_evaluation=instance.latest_evaluation,
        )

    @staticmethod
    def _doi_line(index: int, line: DOILineItemSnapshot) -> LineView:
        product = _observed(line.es_number)
        if type(product.value) is not str:
            product = _observed(line.mfg_number)
        if type(product.value) is not str:
            raise ApplicationError("APPLICATION_PRODUCT_VIEW_UNAVAILABLE", "UNAVAILABLE")
        return LineView(
            line_id=line.line_snapshot_id.to_json_value(),
            line_index=index,
            product_id=product.value,
            quantity=_observed(line.active_quantity),
            line_value=_observed(line.active_line_value),
            availability=_observed(line.availability),
            eta=_observed(line.eta),
            drop_ship_state=_observed(line.drop_ship_state),
            activity=_observed(line.activity),
        )

    def evaluate(
        self,
        order_id: str,
        request_key: str | None = None,
    ) -> EvaluationResultView:
        attempt_started_at = _timestamp(self.database.clock())
        attempt_started = time.perf_counter_ns()
        order = self._validated_order(order_id)
        supplied_key = self._request_key(request_key)
        key = supplied_key or (
            f"m5-evaluate-{hashlib.sha256(order.encode('ascii')).hexdigest()[:24]}"
        )
        with self._lock:
            instance = self._instances.get(order)
            if instance is None:
                raise ApplicationError("ORDER_NOT_FOUND", "NOT_FOUND")
            incomplete_malformed_fixture = (
                instance.descriptor.alias == "malformed-input"
                and instance.mode == "incomplete"
            )
            if incomplete_malformed_fixture or (
                instance.descriptor.alias != "malformed-input"
                and instance.mode not in _EVALUABLE_MODES
            ):
                code = (
                    "BACKEND_EVALUATION_FAILURE"
                    if instance.mode == "backend-evaluation-failure"
                    else "SOURCE_REPRESENTATION_NOT_EVALUABLE"
                )
                operation_id = self._record_closed_outcome(
                    instance,
                    started_at=attempt_started_at,
                    started=attempt_started,
                    result_class=ProcessingResultClass.FAILED_CLOSED,
                    rule_version="m5/fail-closed",
                    error_code=code,
                )
                recorded_at = self._append_attempt(
                    instance,
                    outcome="FAILED_CLOSED",
                    telemetry_operation_id=operation_id,
                    error_code=code,
                )
                self._instances[order] = replace(instance, updated_at=recorded_at)
                raise ApplicationError(code, "UNAVAILABLE")
            source_hash = _source_binding(instance.source)
            try:
                retained_binding = self._durable_registry.bind_evaluation(
                    request_key=key,
                    order_id=order,
                    source_binding=source_hash,
                )
            except IdempotencyConflictError:
                operation_id = self._record_closed_outcome(
                    instance,
                    started_at=attempt_started_at,
                    started=attempt_started,
                    result_class=ProcessingResultClass.CONFLICT,
                    rule_version="m5/conflict",
                    error_code="IDEMPOTENCY_KEY_MATERIAL_CONFLICT",
                )
                recorded_at = self._append_attempt(
                    instance,
                    outcome="CONFLICT",
                    telemetry_operation_id=operation_id,
                    error_code="IDEMPOTENCY_KEY_MATERIAL_CONFLICT",
                )
                self._instances[order] = replace(instance, updated_at=recorded_at)
                raise ApplicationError(
                    "IDEMPOTENCY_KEY_MATERIAL_CONFLICT",
                    "CONFLICT",
                ) from None
            except DurableRegistryError:
                raise ApplicationError(
                    "APPLICATION_DURABLE_HISTORY_INVALID",
                    "UNAVAILABLE",
                ) from None
            binding = DurableEvaluationBinding(
                command_id=retained_binding.command_id,
                order_id=order,
                request_key=key,
                source_binding=source_hash,
                recorded_at=retained_binding.recorded_at,
            )
            try:
                resolution = self._validated_evaluation_resolution(instance, binding)
            except DurableRegistryError:
                raise ApplicationError(
                    "APPLICATION_DURABLE_HISTORY_INVALID",
                    "UNAVAILABLE",
                ) from None
            primary_completion = resolution is None
            application_replay = not primary_completion
            completion_operation_id = (
                _evaluation_operation_id(binding.command_id)
                if primary_completion
                else None
            )
            try:
                result, event_id, operation_id = self._evaluate_instance(
                    instance,
                    key,
                    attempt_started_at,
                    operation_id=completion_operation_id,
                    application_replay=application_replay,
                )
            except _CONFLICT_ERRORS:
                operation_id = self._record_closed_outcome(
                    instance,
                    started_at=attempt_started_at,
                    started=attempt_started,
                    result_class=ProcessingResultClass.CONFLICT,
                    rule_version="m5/conflict",
                    error_code="IDEMPOTENCY_KEY_MATERIAL_CONFLICT",
                    operation_id=completion_operation_id,
                )
                recorded_at = self._append_attempt(
                    instance,
                    outcome="CONFLICT",
                    telemetry_operation_id=operation_id,
                    error_code="IDEMPOTENCY_KEY_MATERIAL_CONFLICT",
                    evaluation_binding_command_id=(
                        binding.command_id if primary_completion else None
                    ),
                )
                self._instances[order] = replace(instance, updated_at=recorded_at)
                raise ApplicationError(
                    "IDEMPOTENCY_KEY_MATERIAL_CONFLICT",
                    "CONFLICT",
                ) from None
            except _DATABASE_ERRORS:
                operation_id: str | None = None
                try:
                    operation_id = self._record_closed_outcome(
                        instance,
                        started_at=attempt_started_at,
                        started=attempt_started,
                        result_class=ProcessingResultClass.ERROR,
                        rule_version="m5/database-error",
                        error_code="APPLICATION_DATABASE_ERROR",
                        database_error=True,
                    )
                except (DatabaseError, RuntimeError, sqlite3.DatabaseError):
                    pass
                if operation_id is not None:
                    try:
                        recorded_at = self._append_attempt(
                            instance,
                            outcome="ERROR",
                            telemetry_operation_id=operation_id,
                            error_code="APPLICATION_DATABASE_ERROR",
                        )
                        self._instances[order] = replace(
                            instance,
                            updated_at=recorded_at,
                        )
                    except ApplicationError:
                        pass
                raise ApplicationError("APPLICATION_DATABASE_ERROR", "UNAVAILABLE") from None
            recorded_at = self._append_attempt(
                instance,
                outcome="SUCCEEDED",
                telemetry_operation_id=operation_id,
                evaluation=result,
                auxiliary_event_id=event_id,
                evaluation_binding_command_id=(
                    binding.command_id if primary_completion else None
                ),
            )
            updated = replace(
                instance,
                latest_evaluation=result,
                updated_at=recorded_at,
                auxiliary_event_id=event_id,
            )
            self._instances[order] = updated
            return result

    def _evaluate_instance(
        self,
        instance: _Instance,
        request_key: str,
        attempt_started_at: CanonicalTimestamp,
        *,
        operation_id: str | None = None,
        application_replay: bool | None = None,
    ) -> tuple[EvaluationResultView, str | None, str]:
        source = instance.source
        if type(source) is _MalformedFixture:
            result = self.malformed_backend.run_demo(
                "malformed-input",
                request_key,
                telemetry_operation_id=operation_id,
                replay_override=application_replay,
            )
            if operation_id is None:
                try:
                    operation_id = self._durable_registry.latest_telemetry_operation(
                        alias="malformed-input",
                        not_before=attempt_started_at,
                    )
                except DurableRegistryError:
                    raise ApplicationError(
                        "APPLICATION_DURABLE_HISTORY_INVALID",
                        "UNAVAILABLE",
                    ) from None
            if operation_id is None:
                raise ApplicationError(
                    "APPLICATION_DURABLE_HISTORY_INVALID",
                    "UNAVAILABLE",
                )
            return (
                EvaluationResultView(
                    order_id=source.order_id,
                    scenario_alias=instance.descriptor.alias,
                    rule_pack="DOI",
                    top_level_result=result.top_level_result,
                    workflow_state=result.workflow_state,
                    reasons=result.reasons,
                    fired_rules=(),
                    opportunities=(),
                    aggregate_potential_status="UNAVAILABLE",
                    aggregate_potential_value=None,
                    value_status="UNAVAILABLE",
                    value=None,
                    human_review_required=result.human_review_required,
                    handling_flags=(),
                    closure_state=None,
                    explanation=ExplanationView(
                        supplied_facts=(),
                        normalized_facts=(),
                        unavailable_facts=("MALFORMED_SOURCE_INPUT",),
                        rules_evaluated=(),
                        precedence_decision="INPUT_REJECTED",
                        reason_ownership=(),
                    ),
                    processing_stages=(
                        ProcessingStageView(
                            "FAIL_CLOSED_VALIDATION",
                            result.processing_duration_ns,
                            "SUCCEEDED",
                        ),
                    ),
                    replayed=result.exact_replay,
                    conflict=False,
                    command_id=None,
                    case_id=None,
                    run_id=None,
                    snapshot_id=None,
                    evaluation_id=None,
                    rule_pack_version="doi-malformed-input/v1",
                    processing_duration_ns=result.processing_duration_ns,
                ),
                result.synthetic_ids[0],
                operation_id,
            )
        started_at = _timestamp(self.database.clock())
        started = time.perf_counter_ns()
        rule_started = time.perf_counter_ns()
        if type(source) is CaseMutation:
            evaluation = self._evaluate_sales_credit(source)
            rule_ns = time.perf_counter_ns() - rule_started
            mutation = replace(source, evaluation=evaluation)
            database_started = time.perf_counter_ns()
            persisted = self.sales_credit.persist_case_mutation(
                mutation,
                request_key=request_key,
            )
            database_ns = time.perf_counter_ns() - database_started
            duration = time.perf_counter_ns() - started
            view = self._sales_credit_result(
                instance,
                mutation,
                persisted,
                duration,
                rule_ns,
                database_ns,
            )
            rule_version = evaluation.rule_pack_version
            pack = RulePack.SALES_CREDIT
        else:
            execution = source.evaluate()
            rule_ns = time.perf_counter_ns() - rule_started
            database_started = time.perf_counter_ns()
            persisted = self.doi.persist_demo(execution, request_key=request_key)
            database_ns = time.perf_counter_ns() - database_started
            duration = time.perf_counter_ns() - started
            view = self._doi_result(
                instance,
                execution.evaluation,
                persisted,
                duration,
                rule_ns,
                database_ns,
            )
            rule_version = execution.evaluation.rule_pack.version
            pack = RulePack.DOI
        if application_replay is not None:
            view = replace(view, replayed=application_replay)
        ended_at = _timestamp(self.database.clock())
        if operation_id is not None:
            try:
                retained_telemetry = self._durable_registry.processing_telemetry(
                    operation_id
                )
            except DurableRegistryError:
                raise ApplicationError(
                    "APPLICATION_EVALUATION_TELEMETRY_INVALID",
                    "UNAVAILABLE",
                ) from None
            if retained_telemetry is not None:
                accepted = self._telemetry_bound_view(
                    instance,
                    view,
                    retained_telemetry,
                )
                if (
                    application_replay is not None
                    and accepted.replayed is not application_replay
                ):
                    raise ApplicationError(
                        "APPLICATION_EVALUATION_TELEMETRY_INVALID",
                        "UNAVAILABLE",
                    )
                return accepted, None, operation_id
        operation_id = self._record_telemetry(
            alias=instance.descriptor.alias,
            rule_pack=pack,
            started_at=started_at,
            ended_at=ended_at,
            rule_ns=rule_ns,
            database_ns=database_ns,
            total_ns=duration,
            human_review=view.human_review_required,
            replay=view.replayed,
            rule_version=rule_version,
            operation_id=operation_id,
        )
        return view, None, operation_id

    @staticmethod
    def _evaluate_sales_credit(source: CaseMutation) -> SalesCreditEvaluation:
        snapshot = source.snapshots[-1]
        order_suffix = source.order_id.value.rsplit("-", 1)[-1]
        return evaluate_sales_credit(
            evaluation_id=EvaluationId(f"SYN-EVALUATION-M5-SC-{order_suffix}"),
            expected_order_id=source.order_id,
            snapshot=snapshot,
            evaluated_at=source.occurred_at,
            known_other_reps=KNOWN_OTHER_REP_CATALOG,
            interactions=source.interactions,
            evidence_events=source.evidence,
            replacement_run=source.replacement_run,
            replacement_candidates=source.replacement_candidates,
        )

    @staticmethod
    def _sales_credit_result(
        instance: _Instance,
        mutation: CaseMutation,
        persisted: DurableCommandResult,
        duration: int,
        rule_ns: int,
        database_ns: int,
    ) -> EvaluationResultView:
        evaluation = mutation.evaluation
        if evaluation is None:
            raise ApplicationError("APPLICATION_EVALUATION_MISSING", "UNAVAILABLE")
        return EvaluationResultView(
            order_id=mutation.order_id.value,
            scenario_alias=instance.descriptor.alias,
            rule_pack="SALES_CREDIT",
            top_level_result=evaluation.workflow_state.value,
            workflow_state=evaluation.workflow_state.value,
            reasons=tuple(item.value for item in evaluation.reasons),
            fired_rules=tuple(item.value for item in evaluation.rules_fired),
            opportunities=(),
            aggregate_potential_status=evaluation.value.status.value,
            aggregate_potential_value=(
                None
                if evaluation.value.placed_value is None
                else _money(evaluation.value.placed_value)
            ),
            value_status=evaluation.value.status.value,
            value=(
                _money(evaluation.value.active_value)
                if evaluation.value.active_value is not None
                else _money(evaluation.value.placed_value)
                if evaluation.value.placed_value is not None
                else None
            ),
            human_review_required=evaluation.human_review_required,
            handling_flags=tuple(item.value for item in evaluation.persistence_effects),
            closure_state=mutation.snapshots[-1].lifecycle_status.value,
            explanation=ExplanationView(
                supplied_facts=tuple(item.value for item in evaluation.supplied_facts),
                normalized_facts=tuple(item.value for item in evaluation.validations),
                unavailable_facts=(),
                rules_evaluated=tuple(item.value for item in evaluation.rules_evaluated),
                precedence_decision=evaluation.workflow_state.value,
                reason_ownership=(),
            ),
            processing_stages=(
                ProcessingStageView("RULE_EVALUATION", rule_ns, "SUCCEEDED"),
                ProcessingStageView("PERSISTENCE", database_ns, "SUCCEEDED"),
                ProcessingStageView("TOTAL", duration, "SUCCEEDED"),
            ),
            replayed=persisted.replayed,
            conflict=False,
            command_id=persisted.command_id,
            case_id=mutation.order_id.value,
            run_id=(
                None if mutation.discovery_run is None else mutation.discovery_run.run_id.value
            ),
            snapshot_id=evaluation.snapshot_id.value,
            evaluation_id=evaluation.evaluation_id.value,
            rule_pack_version=evaluation.rule_pack_version,
            processing_duration_ns=duration,
        )

    def _doi_result(
        self,
        instance: _Instance,
        evaluation: DOIEvaluation,
        persisted: DurableCommandResult,
        duration: int,
        rule_ns: int,
        database_ns: int,
    ) -> EvaluationResultView:
        case = self.doi.get_case(evaluation.order_id.to_json_value())
        if case is None:
            raise ApplicationError("APPLICATION_DOI_CASE_MISSING", "UNAVAILABLE")
        opportunities = tuple(
            OpportunityView(
                opportunity_type=item.opportunity_type.value,
                line_ids=tuple(
                    sorted(line.to_json_value() for line in item.scope.line_ids)
                ),
                potential_value=(
                    None if item.potential_value is None else _money(item.potential_value)
                ),
            )
            for item in evaluation.opportunities
        )
        return EvaluationResultView(
            order_id=evaluation.order_id.to_json_value(),
            scenario_alias=instance.descriptor.alias,
            rule_pack="DOI",
            top_level_result=evaluation.state.value,
            workflow_state=case.lifecycle_state.value,
            reasons=tuple(item.code for item in evaluation.reasons.reasons),
            fired_rules=evaluation.explanation.rules_fired,
            opportunities=opportunities,
            aggregate_potential_status=evaluation.aggregate_potential_state.value,
            aggregate_potential_value=(
                None
                if evaluation.aggregate_potential is None
                else _money(evaluation.aggregate_potential)
            ),
            value_status=evaluation.aggregate_potential_state.value,
            value=(
                None
                if evaluation.aggregate_potential is None
                else _money(evaluation.aggregate_potential)
            ),
            human_review_required=bool(evaluation.human_review_requirements),
            handling_flags=tuple(item.value for item in evaluation.handling_flags),
            closure_state=evaluation.explanation.closure_state,
            explanation=ExplanationView(
                supplied_facts=evaluation.explanation.supplied_facts,
                normalized_facts=evaluation.explanation.normalized_facts,
                unavailable_facts=evaluation.explanation.unavailable_facts,
                rules_evaluated=evaluation.explanation.rules_evaluated,
                precedence_decision=evaluation.explanation.precedence_decision,
                reason_ownership=evaluation.explanation.reason_ownership,
            ),
            processing_stages=(
                ProcessingStageView("RULE_EVALUATION", rule_ns, "SUCCEEDED"),
                ProcessingStageView("PERSISTENCE", database_ns, "SUCCEEDED"),
                ProcessingStageView("TOTAL", duration, "SUCCEEDED"),
            ),
            replayed=persisted.replayed,
            conflict=False,
            command_id=persisted.command_id,
            case_id=case.case_id.value,
            run_id=evaluation.run_id.to_json_value(),
            snapshot_id=evaluation.snapshot_id.to_json_value(),
            evaluation_id=evaluation.evaluation_id.value,
            rule_pack_version=evaluation.rule_pack.version,
            processing_duration_ns=duration,
        )

    def _record_telemetry(
        self,
        *,
        alias: str,
        rule_pack: RulePack,
        started_at: CanonicalTimestamp,
        ended_at: CanonicalTimestamp,
        rule_ns: int,
        database_ns: int,
        total_ns: int,
        human_review: bool,
        replay: bool,
        rule_version: str,
        result_class: ProcessingResultClass | None = None,
        database_error: bool = False,
        error_code: str | None = None,
        operation_id: str | None = None,
    ) -> str:
        outcome = result_class or (
            ProcessingResultClass.HUMAN_REVIEW
            if human_review
            else ProcessingResultClass.SUCCESS
        )
        accepted_operation_id = operation_id or (
            f"SYN-EVIDENCE-M5-OPERATION-{uuid.uuid4().hex.upper()}"
        )
        telemetry = ProcessingTelemetry(
            operation_id=accepted_operation_id,
            rule_pack=rule_pack,
            demo_alias=alias,
            started_at=started_at,
            ended_at=ended_at,
            extraction_ns=0,
            validation_ns=0,
            normalization_ns=0,
            rule_ns=rule_ns,
            database_ns=database_ns,
            total_ns=total_ns,
            result_class=outcome,
            human_review=human_review,
            fail_closed=outcome is ProcessingResultClass.FAILED_CLOSED,
            replay=replay,
            conflict=outcome is ProcessingResultClass.CONFLICT,
            database_error=database_error,
            rule_version=rule_version,
            schema_version="4",
            catalog_version=APPLICATION_SCENARIO_CATALOG_VERSION,
            error_code=error_code,
        )
        with self.database.write() as connection:
            record_processing_telemetry(connection, telemetry)
        return accepted_operation_id

    def _record_closed_outcome(
        self,
        instance: _Instance,
        *,
        started_at: CanonicalTimestamp,
        started: int,
        result_class: ProcessingResultClass,
        rule_version: str,
        error_code: str,
        database_error: bool = False,
        operation_id: str | None = None,
    ) -> str:
        if operation_id is not None:
            try:
                retained = self._durable_registry.processing_telemetry(operation_id)
            except DurableRegistryError:
                raise ApplicationError(
                    "APPLICATION_EVALUATION_TELEMETRY_INVALID",
                    "UNAVAILABLE",
                ) from None
            if retained is not None:
                expected_fail_closed = (
                    result_class is ProcessingResultClass.FAILED_CLOSED
                )
                expected_conflict = result_class is ProcessingResultClass.CONFLICT
                if (
                    retained.demo_alias != instance.descriptor.alias
                    or retained.rule_pack is not RulePack(instance.descriptor.rule_pack)
                    or retained.result_class is not result_class
                    or retained.human_review
                    or retained.fail_closed != expected_fail_closed
                    or retained.replay
                    or retained.conflict != expected_conflict
                    or retained.database_error != database_error
                    or retained.rule_version != rule_version
                    or retained.schema_version != "4"
                    or retained.catalog_version != APPLICATION_SCENARIO_CATALOG_VERSION
                    or retained.error_code != error_code
                    or retained.extraction_ns != 0
                    or retained.validation_ns != 0
                    or retained.normalization_ns != 0
                    or retained.rule_ns != 0
                    or retained.database_ns != 0
                ):
                    raise ApplicationError(
                        "APPLICATION_EVALUATION_TELEMETRY_INVALID",
                        "UNAVAILABLE",
                    )
                return operation_id
        ended_at = _timestamp(self.database.clock())
        return self._record_telemetry(
            alias=instance.descriptor.alias,
            rule_pack=RulePack(instance.descriptor.rule_pack),
            started_at=started_at,
            ended_at=ended_at,
            rule_ns=0,
            database_ns=0,
            total_ns=time.perf_counter_ns() - started,
            human_review=False,
            replay=False,
            rule_version=rule_version,
            result_class=result_class,
            database_error=database_error,
            error_code=error_code,
            operation_id=operation_id,
        )

    def _sales_credit_history_groups(
        self,
        latest: EvaluationResultView,
        occurred_at: str,
    ) -> tuple[
        tuple[HistoryArtifactView, ...],
        tuple[HistoryArtifactView, ...],
        tuple[HistoryArtifactView, ...],
        tuple[HistoryArtifactView, ...],
    ]:
        """Build a closed read projection through typed M4 service reads."""
        artifacts = (
            HistoryArtifactView(
                artifact_type="EVALUATION",
                artifact_id=latest.evaluation_id,
                state=latest.top_level_result,
                occurred_at=occurred_at,
                reasons=latest.reasons,
                transition_id=None,
            ),
        )
        attention = (
            ()
            if not latest.human_review_required
            else (
                HistoryArtifactView(
                    artifact_type="HUMAN_REVIEW_REQUIREMENT",
                    artifact_id=latest.evaluation_id,
                    state="REQUIRED",
                    occurred_at=occurred_at,
                    reasons=latest.reasons,
                    transition_id=None,
                ),
            )
        )
        values = (
            HistoryArtifactView(
                artifact_type="ORDER_VALUE",
                artifact_id=latest.evaluation_id,
                state=latest.value_status,
                occurred_at=occurred_at,
                reasons=(),
                transition_id=None,
                value=latest.value,
            ),
        )
        if latest.case_id is None:
            return artifacts, attention, values, ()
        try:
            outcomes = self.sales_credit.manager_outcomes(
                OrderId(latest.case_id),
                limit=MAX_HISTORY_ITEMS,
            )
        except _DATABASE_ERRORS:
            raise ApplicationError(
                "APPLICATION_PERSISTED_HISTORY_INVALID",
                "UNAVAILABLE",
            ) from None
        manager = tuple(
            HistoryArtifactView(
                artifact_type="MANAGER_OUTCOME",
                artifact_id=item.occurrence_id.value,
                state=item.outcome.value,
                occurred_at=item.decided_at.value,
                reasons=(),
                transition_id=None,
                value=(
                    None if item.approved_amount is None else _money(item.approved_amount)
                ),
            )
            for item in outcomes
        )
        return artifacts, attention, values, manager

    def _doi_history_groups(
        self,
        latest: EvaluationResultView,
        occurred_at: str,
    ) -> tuple[
        tuple[HistoryArtifactView, ...],
        tuple[HistoryArtifactView, ...],
        tuple[HistoryArtifactView, ...],
        tuple[HistoryArtifactView, ...],
    ]:
        """Build closed history exclusively through typed M4 service reads."""
        if latest.evaluation_id is None or latest.case_id is None:
            raise ApplicationError("APPLICATION_DOI_HISTORY_MISSING", "UNAVAILABLE")
        try:
            evaluation = self.doi.get_evaluation(latest.evaluation_id)
            if evaluation is None:
                raise ApplicationError("APPLICATION_DOI_HISTORY_MISSING", "UNAVAILABLE")
            transition = evaluation.transition.transition_id
            reasons = tuple(item.code for item in evaluation.reasons.reasons)
            evaluation_timestamp = self.doi.evaluation_recorded_at(
                case_id=latest.case_id,
                evaluation_id=latest.evaluation_id,
            )
            owner_events = self.doi.case_owner_events(
                case_id=latest.case_id,
                limit=MAX_HISTORY_ITEMS,
            )
            intervention_records = self.doi.case_interventions(
                case_id=latest.case_id,
                limit=MAX_HISTORY_ITEMS,
            )
        except _DATABASE_ERRORS:
            raise ApplicationError(
                "APPLICATION_PERSISTED_HISTORY_INVALID",
                "UNAVAILABLE",
            ) from None
        evaluation_at = (
            occurred_at
            if evaluation_timestamp is None
            else evaluation_timestamp.value
        )
        artifacts: list[HistoryArtifactView] = [
            HistoryArtifactView(
                artifact_type="EVALUATION",
                artifact_id=latest.evaluation_id,
                state=evaluation.state.value,
                occurred_at=evaluation_at,
                reasons=reasons,
                transition_id=transition,
            )
        ]
        attention = [
            HistoryArtifactView(
                artifact_type="HUMAN_REVIEW_REQUIREMENT",
                artifact_id=latest.evaluation_id,
                state=requirement.value,
                occurred_at=evaluation_at,
                reasons=reasons,
                transition_id=transition,
            )
            for requirement in evaluation.human_review_requirements
        ]
        for event in owner_events:
            item = HistoryArtifactView(
                artifact_type=f"{event.stream_family}_OWNER_EVENT",
                artifact_id=event.event_id,
                state=event.projection_state,
                occurred_at=event.occurred_at.value,
                reasons=(),
                transition_id=event.transition_id,
            )
            if event.stream_family == "ATTENTION":
                attention.append(item)
            else:
                artifacts.append(item)
        values = [
            HistoryArtifactView(
                artifact_type="AGGREGATE_POTENTIAL",
                artifact_id=latest.evaluation_id,
                state=evaluation.aggregate_potential_state.value,
                occurred_at=evaluation_at,
                reasons=reasons,
                transition_id=transition,
                value=(
                    None
                    if evaluation.aggregate_potential is None
                    else _money(evaluation.aggregate_potential)
                ),
            )
        ]
        values.extend(
            HistoryArtifactView(
                artifact_type="OPPORTUNITY_VALUE",
                artifact_id=opportunity.opportunity_id.value,
                state=opportunity.potential_value_state.value,
                occurred_at=evaluation_at,
                reasons=(),
                transition_id=transition,
                value=(
                    None
                    if opportunity.potential_value is None
                    else _money(opportunity.potential_value)
                ),
            )
            for opportunity in evaluation.opportunities
        )
        interventions = tuple(
            HistoryArtifactView(
                artifact_type="INTERVENTION",
                artifact_id=record.intervention.intervention_id.value,
                state=record.intervention.status.value,
                occurred_at=(
                    record.created_at.value
                    if record.intervention.action_occurred_at is None
                    else record.intervention.action_occurred_at.value
                ),
                reasons=(),
                transition_id=None,
            )
            for record in intervention_records
        )
        for record in intervention_records:
            for event in record.intervention.value_events:
                values.append(
                    HistoryArtifactView(
                        artifact_type="VERIFIED_VALUE_EVENT",
                        artifact_id=event.event_id.value,
                        state=event.event_type.value,
                        occurred_at=event.occurred_at.value,
                        reasons=(),
                        transition_id=None,
                        value=_money(event.amount),
                    )
                )
        if any(
            len(items) > MAX_HISTORY_ITEMS
            for items in (artifacts, attention, interventions, values)
        ):
            raise ApplicationError("APPLICATION_HISTORY_LIMIT_EXCEEDED", "UNAVAILABLE")
        return tuple(artifacts), tuple(attention), interventions, tuple(values)

    def get_history(self, order_id: str) -> HistoryView:
        order = self._validated_order(order_id)
        with self._lock:
            instance = self._instances.get(order)
            if instance is None:
                raise ApplicationError("ORDER_NOT_FOUND", "NOT_FOUND")
            instance, attempts = self._refresh_instance(instance)
            self._instances[order] = instance
            source = instance.source
            events: tuple[HistoryEventView, ...]
            if type(source) is CaseMutation:
                stored = self.sales_credit.case_history(source.order_id)
                if len(stored) > MAX_HISTORY_ITEMS:
                    raise ApplicationError(
                        "APPLICATION_HISTORY_LIMIT_EXCEEDED",
                        "UNAVAILABLE",
                    )
                events = tuple(
                    HistoryEventView(
                        sequence=item.sequence,
                        event_id=item.event_id.value,
                        event_kind=item.event_kind,
                        state=item.workflow_state.value,
                        occurred_at=item.occurred_at.value,
                        evaluation_id=(
                            None
                            if item.current_evaluation_id is None
                            else item.current_evaluation_id.value
                        ),
                    )
                    for item in stored
                )
            elif type(source) is DOIDemoFixture:
                stored = self.doi.run_history(source.run_start.run.run_id.value)
                if len(stored) > MAX_HISTORY_ITEMS:
                    raise ApplicationError(
                        "APPLICATION_HISTORY_LIMIT_EXCEEDED",
                        "UNAVAILABLE",
                    )
                events = tuple(
                    HistoryEventView(
                        sequence=item.sequence.value,
                        event_id=None,
                        event_kind=item.event_kind.value,
                        state=item.status.value,
                        occurred_at=item.occurred_at.value,
                        evaluation_id=None,
                    )
                    for item in stored
                )
                if instance.latest_evaluation is not None:
                    latest = instance.latest_evaluation
                    events = (
                        *events,
                        HistoryEventView(
                            sequence=len(events) + 1,
                            event_id=None,
                            event_kind="EVALUATION_PERSISTED",
                            state=latest.top_level_result,
                            occurred_at=instance.updated_at.value,
                            evaluation_id=latest.evaluation_id,
                        ),
                    )
            elif instance.latest_evaluation is None:
                events = ()
            else:
                latest = instance.latest_evaluation
                events = (
                    HistoryEventView(
                        sequence=1,
                        event_id=instance.auxiliary_event_id,
                        event_kind="INPUT_REJECTED",
                        state=latest.top_level_result,
                        occurred_at=instance.updated_at.value,
                        evaluation_id=None,
                    ),
                )
            artifacts: list[HistoryArtifactView] = []
            if type(source) is CaseMutation:
                snapshot = source.snapshots[-1]
                artifacts.append(
                    HistoryArtifactView(
                        artifact_type="IMMUTABLE_SNAPSHOT",
                        artifact_id=snapshot.snapshot_id.value,
                        state=snapshot.extraction_status.value,
                        occurred_at=snapshot.captured_at.value,
                        reasons=(),
                        transition_id=None,
                    )
                )
            elif type(source) is DOIDemoFixture:
                artifacts.append(
                    HistoryArtifactView(
                        artifact_type="IMMUTABLE_SNAPSHOT",
                        artifact_id=source.snapshot.snapshot_id.to_json_value(),
                        state="COMPLETE",
                        occurred_at=source.snapshot.source_observed_at.value,
                        reasons=(),
                        transition_id=None,
                    )
                )
            elif instance.auxiliary_event_id is not None:
                artifacts.append(
                    HistoryArtifactView(
                        artifact_type="STRUCTURED_FAILURE",
                        artifact_id=instance.auxiliary_event_id,
                        state="REJECTED",
                        occurred_at=instance.updated_at.value,
                        reasons=("INVALID_ORDER_NUMBER",),
                        transition_id=None,
                    )
                )
            latest = instance.latest_evaluation
            attention_causes: tuple[HistoryArtifactView, ...] = ()
            intervention_events: tuple[HistoryArtifactView, ...] = ()
            value_events: tuple[HistoryArtifactView, ...] = ()
            manager_outcomes: tuple[HistoryArtifactView, ...] = ()
            if latest is not None:
                if type(source) is CaseMutation:
                    grouped = self._sales_credit_history_groups(
                        latest,
                        instance.updated_at.value,
                    )
                    extra_artifacts, attention_causes, value_events, manager_outcomes = (
                        grouped
                    )
                    artifacts.extend(extra_artifacts)
                elif type(source) is DOIDemoFixture:
                    grouped = self._doi_history_groups(
                        latest,
                        instance.updated_at.value,
                    )
                    extra_artifacts, attention_causes, intervention_events, value_events = (
                        grouped
                    )
                    artifacts.extend(extra_artifacts)
                elif instance.auxiliary_event_id is None:
                    artifacts.append(
                        HistoryArtifactView(
                            artifact_type="STRUCTURED_FAILURE",
                            artifact_id=None,
                            state=latest.top_level_result,
                            occurred_at=instance.updated_at.value,
                            reasons=latest.reasons,
                            transition_id=None,
                        )
                    )
            if len(events) > MAX_HISTORY_ITEMS or len(artifacts) > MAX_HISTORY_ITEMS:
                raise ApplicationError(
                    "APPLICATION_HISTORY_LIMIT_EXCEEDED",
                    "UNAVAILABLE",
                )
            command_ids = tuple(
                item.evaluation.command_id
                for item in attempts
                if item.evaluation is not None
                and item.evaluation.command_id is not None
            )
            try:
                receipt_times = self._durable_registry.receipt_recorded_at(command_ids)
                telemetry_ids = tuple(item.telemetry_operation_id for item in attempts)
                existing_telemetry = self._durable_registry.existing_telemetry(
                    telemetry_ids
                )
            except DurableRegistryError:
                raise ApplicationError(
                    "APPLICATION_DURABLE_HISTORY_INVALID",
                    "UNAVAILABLE",
                ) from None
            if existing_telemetry != frozenset(telemetry_ids):
                raise ApplicationError(
                    "APPLICATION_DURABLE_HISTORY_INVALID",
                    "UNAVAILABLE",
                )
            receipts = tuple(
                ReceiptSummaryView(
                    command_id=cast(str, item.evaluation.command_id),
                    replayed=item.evaluation.replayed,
                    recorded_at=receipt_times[cast(str, item.evaluation.command_id)],
                )
                for item in attempts
                if item.evaluation is not None
                and item.evaluation.command_id is not None
            )
            attempt_receipts = tuple(
                AttemptReceiptView(
                    attempt_id=item.attempt_id,
                    command_id=(
                        None if item.evaluation is None else item.evaluation.command_id
                    ),
                    outcome=item.outcome,
                    replayed=item.replayed,
                    conflict=item.conflict,
                    error_code=item.error_code,
                    telemetry_operation_id=item.telemetry_operation_id,
                    recorded_at=item.recorded_at.value,
                )
                for item in attempts
            )
            return HistoryView(
                order_id=order,
                events=events,
                artifacts=tuple(artifacts),
                receipts=receipts,
                attempt_receipts=attempt_receipts,
                attention_causes=attention_causes,
                intervention_events=intervention_events,
                value_events=value_events,
                manager_outcomes=manager_outcomes,
                telemetry_event_count=len(existing_telemetry),
                exact_replay_count=sum(item.replayed for item in attempts),
                conflict_count=sum(item.conflict for item in attempts),
            )

    def get_interaction(self, interaction_id: str) -> InteractionView:
        if type(interaction_id) is not str:
            raise ApplicationError("INTERACTION_ID_INVALID", "INVALID")
        try:
            accepted = InteractionId(interaction_id).value
        except ValueError:
            raise ApplicationError("INTERACTION_ID_INVALID", "INVALID") from None
        with self._lock:
            order = self._interaction_orders.get(accepted)
            if order is None:
                raise ApplicationError("INTERACTION_NOT_FOUND", "NOT_FOUND")
            instance = self._instances[order]
            source = instance.source
            if type(source) is not CaseMutation:
                raise ApplicationError("INTERACTION_NOT_FOUND", "NOT_FOUND")
            interaction = next(
                item for item in source.interactions if item.interaction_id.value == accepted
            )
            participation = (
                "UNKNOWN"
                if instance.descriptor.alias == "sales-credit-human-review"
                else "KNOWN_PRESENT"
            )
            return InteractionView(
                interaction_id=accepted,
                direction="INBOUND",
                timestamp=interaction.recorded_at.value,
                timestamp_precision=interaction.timestamp_precision.value,
                target_rep_participation=participation,
                identifier_kind="EMAIL",
                evidence_classification="SYNTHETIC_SOURCE_INTERACTION",
                order_id=order,
            )

    def get_run(self, run_id: str) -> RunView:
        if type(run_id) is not str:
            raise ApplicationError("RUN_ID_INVALID", "INVALID")
        try:
            accepted = RunId(run_id).value
        except ValueError:
            raise ApplicationError("RUN_ID_INVALID", "INVALID") from None
        with self._lock:
            order = self._run_orders.get(accepted)
            if order is None:
                raise ApplicationError("RUN_NOT_FOUND", "NOT_FOUND")
            instance = self._instances[order]
            source = instance.source
            if type(source) is CaseMutation:
                run = source.discovery_run
                if run is None:
                    raise ApplicationError("RUN_NOT_FOUND", "NOT_FOUND")
                return RunView(
                    run_id=run.run_id.value,
                    rule_pack="SALES_CREDIT",
                    order_id=order,
                    run_type=run.trigger.value,
                    status="COMPLETED",
                    started_at=run.started_at.value,
                    completed_at=run.completed_at.value,
                    event_count=1,
                )
            if type(source) is not DOIDemoFixture:
                raise ApplicationError("RUN_NOT_FOUND", "NOT_FOUND")
            run = source.run_start.run
            history_count = len(self.doi.run_history(run.run_id.value))
            return RunView(
                run_id=run.run_id.value,
                rule_pack="DOI",
                order_id=order,
                run_type=run.run_type.value,
                status=run.status.value,
                started_at=run.started_at.value,
                completed_at=None if run.completed_at is None else run.completed_at.value,
                event_count=history_count,
            )

    def doi_selection_input(self, order_id: str) -> DOIEvaluationInput:
        """Return the retained/restored synthetic DOI input to the internal M7 adapter."""

        order = self._validated_order(order_id)
        with self._lock:
            source = self._instances[order].source
            if type(source) is not DOIDemoFixture:
                raise ApplicationError("DOI_SELECTION_SOURCE_UNAVAILABLE", "UNAVAILABLE")
            return source.request

    def metrics_summary(self) -> MetricsSummaryView:
        with self.database.read() as connection:
            summary = aggregate_processing_telemetry(connection)
        return MetricsSummaryView(
            total_processed=summary.total_processed,
            success_count=summary.success_count,
            success_rate_numerator=summary.success_rate.numerator,
            success_rate_denominator=summary.success_rate.denominator,
            failed_closed_count=summary.failed_closed_count,
            human_review_count=summary.human_review_count,
            exact_replay_count=summary.exact_replay_count,
            conflict_count=summary.conflict_count,
            database_error_count=summary.database_error_count,
            median_latency_ns=summary.median_latency_ns,
            p95_latency_ns=summary.p95_latency_ns,
            throughput_per_second=summary.throughput_per_second,
            safety_counters=summary.safety_counters,
        )

    def system_status(self, deep: bool = False) -> SystemStatusView:
        if type(deep) is not bool:
            raise ApplicationError("SYSTEM_STATUS_DEPTH_INVALID", "INVALID")
        with self.database.read() as connection:
            verification = verify_database(connection, deep=deep)
            sales_credit = verify_sales_credit_projections(connection)
            doi = DOIRepository(connection).verify_projections()
            safety = verify_application_safety_counters(connection)
        projections_ok = sales_credit.valid and doi.ok
        counters_ok = safety.valid
        healthy = verification.healthy and projections_ok and counters_ok
        with self._lock:
            count = len(self._instances)
            evaluated = sum(
                item.latest_evaluation is not None for item in self._instances.values()
            )
        return SystemStatusView(
            app_version=__version__,
            build_version=APPLICATION_BUILD_VERSION,
            database_status="PASS" if healthy else "FAIL",
            database_schema_version=verification.schema_version,
            expected_schema_version=verification.expected_schema_version,
            quick_check=verification.quick_check,
            integrity_check=verification.integrity_check or "not_run",
            migration_status=(
                "CURRENT"
                if verification.schema_version == verification.expected_schema_version
                else "UNSUPPORTED"
            ),
            projection_status="PASS" if projections_ok else "FAIL",
            safety_counters=safety.counters,
            registry_capacity=self.registry_limit,
            registry_count=count,
            evaluated_count=evaluated,
        )


__all__ = [
    "APPLICATION_SCENARIO_CATALOG_VERSION",
    "DEFAULT_REGISTRY_LIMIT",
    "MAX_REGISTRY_LIMIT",
    "ScenarioApplication",
]
