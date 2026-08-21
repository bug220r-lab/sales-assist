from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from synthetic_sales_assist.doi.identities import (
    LineSnapshotId,
    RunInvocationId,
    SourceIdentityId,
)
from synthetic_sales_assist.doi.knowledge import (
    DOIExactSKUObservation,
    create_relationship,
)
from synthetic_sales_assist.doi.models import (
    AlternateAvailability,
    AlternateObservationState,
    AlternateRelationshipType,
    model_action_context_fixture,
)
from synthetic_sales_assist.doi.source import (
    InMemoryDOIRunControl,
    SyntheticQueueTab,
)
from synthetic_sales_assist.domain.identities import (
    EvidenceId,
    InteractionId,
    RunId,
    SkuId,
)
from synthetic_sales_assist.domain.numeric import (
    CURRENCY_REGISTRY_VERSION,
    Money,
)
from synthetic_sales_assist.domain.records import (
    SourceKind,
    SourceObjectNamespace,
    SourceRef,
)
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp
from synthetic_sales_assist.persistence.database import SQLiteDatabase
from synthetic_sales_assist.persistence.doi_services import DOIPersistenceService
from synthetic_sales_assist.persistence.faults import (
    FaultInjector,
    FaultPoint,
    InjectedPersistenceFault,
)


NOW = CanonicalTimestamp("2026-08-20T14:15:16Z")


class Milestone4DOIServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.database = SQLiteDatabase(Path(self.temporary.name) / "doi.sqlite3")
        self.database.initialize()
        self.service = DOIPersistenceService(self.database)

    def test_source_run_and_attempt_are_atomic_and_replayable(self) -> None:
        control = InMemoryDOIRunControl()
        start = control.begin_review_run(
            run_id=RunId("SYN-RUN-DOI-M4-SOURCE"),
            invocation_id=RunInvocationId(
                InteractionId("SYN-INTERACTION-DOI-M4-SOURCE-RUN")
            ),
            source_identity_id=SourceIdentityId(
                EvidenceId("SYN-EVIDENCE-DOI-M4-SOURCE")
            ),
            locked_tab=SyntheticQueueTab.MONDAY,
            tab_confirmed=True,
            accepted_at=NOW,
        )
        self.assertFalse(self.service.invoke_run(start).replayed)
        assert start.source_attempt is not None
        assert start.source_attempt_event is not None
        first = self.service.import_source_attempt(
            start.source_attempt,
            start.source_attempt_event,
        )
        replay = self.service.import_source_attempt(
            start.source_attempt,
            start.source_attempt_event,
        )
        self.assertFalse(first.replayed)
        self.assertTrue(replay.replayed)
        with self.database.read() as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM doi_source_import_attempts"
                ).fetchone()[0],
                1,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM doi_source_import_attempt_events"
                ).fetchone()[0],
                1,
            )

    def test_product_revision_and_observation_are_immutable(self) -> None:
        ordered = SkuId("SYN-SKU-DOI-M4-PRODUCT-ORDERED")
        candidate = SkuId("SYN-SKU-DOI-M4-PRODUCT-CANDIDATE")
        source = SourceRef.create(
            source_ref_id=EvidenceId("SYN-EVIDENCE-DOI-M4-PRODUCT-SOURCE"),
            source_kind=SourceKind.SYNTHETIC_PRODUCT_FIXTURE,
            object_namespace=SourceObjectNamespace.SYNTHETIC_PRODUCT,
            object_id=candidate,
        )
        relationship = create_relationship(
            relationship_id=EvidenceId("SYN-EVIDENCE-DOI-M4-RELATIONSHIP"),
            revision_id=EvidenceId("SYN-EVIDENCE-DOI-M4-RELATIONSHIP-REVISION"),
            relationship_type=AlternateRelationshipType.EXACT_MFG,
            ordered_sku=ordered,
            candidate_sku=candidate,
            ordered_mfg=SkuId("SYN-SKU-DOI-M4-PRODUCT-MFG"),
            candidate_mfg=SkuId("SYN-SKU-DOI-M4-PRODUCT-MFG"),
            compatibility_review_required=False,
            evidence_source=source,
        )
        with self.assertRaises(InjectedPersistenceFault):
            self.service.append_relationship_revision(
                relationship,
                fault_injector=FaultInjector(
                    frozenset({FaultPoint.BEFORE_COMMIT})
                ),
            )
        with self.database.read() as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM doi_product_relationship_revisions"
                ).fetchone()[0],
                0,
            )
        self.assertFalse(
            self.service.append_relationship_revision(relationship).replayed
        )
        self.assertTrue(
            self.service.append_relationship_revision(relationship).replayed
        )

        context = model_action_context_fixture()
        observation_source = SourceRef.create(
            source_ref_id=EvidenceId(
                "SYN-EVIDENCE-DOI-M4-PRODUCT-OBSERVATION-SOURCE"
            ),
            source_kind=SourceKind.SYNTHETIC_PRODUCT_FIXTURE,
            object_namespace=SourceObjectNamespace.SYNTHETIC_PRODUCT,
            object_id=ordered,
        )
        observation = DOIExactSKUObservation(
            observation_id=EvidenceId("SYN-EVIDENCE-DOI-M4-PRODUCT-OBSERVATION"),
            action_context_id=context.action_context_id,
            action_context_binding=context.hash_binding(),
            ordered_line_id=LineSnapshotId(
                EvidenceId("SYN-EVIDENCE-DOI-M4-PRODUCT-LINE")
            ),
            ordered_sku=ordered,
            observed_sku=ordered,
            state=AlternateObservationState.CURRENT,
            observed_availability=AlternateAvailability.IN_STOCK,
            potential_unit_value=Money.from_minor_units(
                1_000,
                currency_code="USD",
                registry_version=CURRENCY_REGISTRY_VERSION,
                scale=2,
            ),
            observed_at=NOW,
            source=observation_source,
        )
        with self.assertRaises(InjectedPersistenceFault):
            self.service.append_relationship_observation(
                observation,
                fault_injector=FaultInjector(
                    frozenset({FaultPoint.BEFORE_COMMIT})
                ),
            )
        with self.database.read() as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM doi_product_observations"
                ).fetchone()[0],
                0,
            )
        self.assertFalse(
            self.service.append_relationship_observation(observation).replayed
        )
        self.assertTrue(
            self.service.append_relationship_observation(observation).replayed
        )
        with self.assertRaisesRegex(sqlite3.IntegrityError, "DOI_IMMUTABLE_RECORD"):
            with self.database.write() as connection:
                connection.execute(
                    "UPDATE doi_product_relationship_revisions "
                    "SET revision_no=revision_no"
                )
        with self.database.write() as connection:
            connection.execute("DELETE FROM doi_product_relationship_revisions")
        self.assertIn(
            "DOI_PRODUCT_KNOWLEDGE_PROJECTION_MISMATCH",
            self.service.verify_projections().errors,
        )

    def test_required_transactional_operation_surface_is_named(self) -> None:
        required = {
            "invoke_run",
            "import_source_attempt",
            "record_run_work_disposition",
            "finalize_run_processing",
            "accept_retry",
            "explicit_no_retry_finalization",
            "reserve_extraction",
            "complete_extraction",
            "apply_case_owner_decision",
            "append_snapshot_evaluation",
            "apply_lifecycle_transition",
            "set_attention_cause",
            "clear_attention_cause",
            "append_relationship_revision",
            "append_relationship_observation",
            "record_human_fact",
            "record_contact_event",
            "record_wwc_event",
            "record_dedupe_event",
            "record_intervention",
            "verify_intervention_action",
            "append_value_event",
            "search_resulting_order",
            "link_resulting_order",
            "append_kpi_contribution",
            "schedule_retention",
            "finalize_kpi_and_purge_case",
        }
        self.assertTrue(
            all(callable(getattr(self.service, name, None)) for name in required)
        )


if __name__ == "__main__":
    unittest.main()
