from __future__ import annotations

import dataclasses
import hashlib
import unittest

from synthetic_sales_assist.doi.identities import DoiOrderId, LineSnapshotId
from synthetic_sales_assist.doi.knowledge import (
    DOIAlternateObservation,
    DOIExactSKUObservation,
    ProductKnowledgeError,
    append_relationship_revision,
    candidate_from_relationship,
    compare_knowledge_preimages,
    create_relationship,
    exact_sku_candidate,
    knowledge_hash_contracts,
    knowledge_hash_fixtures,
    knowledge_hash_known_answer,
)
from synthetic_sales_assist.doi.models import (
    ActionContextEventType,
    AlternateAvailability,
    AlternateObservationState,
    AlternateRelationshipState,
    AlternateRelationshipType,
    AlternateRevisionKind,
    AlternateValidityState,
    CompatibilityDecision,
    DOIActionContext,
    DOIActionContextEvent,
    DOIOccurrenceGuard,
    OpportunityType,
    known_fact,
    not_applicable_fact,
    unknown_fact,
)
from synthetic_sales_assist.domain.canonical import canonical_json_bytes, domain_hash
from synthetic_sales_assist.domain.identities import (
    EvidenceId,
    InteractionId,
    OrderId,
    SkuId,
)
from synthetic_sales_assist.domain.numeric import PositiveQuantity
from synthetic_sales_assist.domain.records import (
    SourceKind,
    SourceObjectNamespace,
    SourceRef,
)
from tests.test_doi_models import OBSERVED_AT, open_context, ordinary_snapshot, usd


def product_source(candidate_sku: SkuId, suffix: str = "0001") -> SourceRef:
    return SourceRef.create(
        source_ref_id=EvidenceId(f"SYN-EVIDENCE-DOI-PRODUCT-SOURCE-{suffix}"),
        source_kind=SourceKind.SYNTHETIC_PRODUCT_FIXTURE,
        object_namespace=SourceObjectNamespace.SYNTHETIC_PRODUCT,
        object_id=candidate_sku,
    )


def action_context(suffix: str = "0001") -> DOIActionContext:
    return open_context(ordinary_snapshot(), f"PRODUCT-{suffix}")[0]


def relationship(
    relationship_type: AlternateRelationshipType = AlternateRelationshipType.EXACT_MFG,
):
    ordered = SkuId("SYN-SKU-DOI-ORDERED-0001")
    candidate = SkuId("SYN-SKU-DOI-CANDIDATE-0001")
    same_mfg = SkuId("SYN-SKU-DOI-MFG-CANONICAL-0001")
    functional = relationship_type is AlternateRelationshipType.FUNCTIONAL
    return create_relationship(
        relationship_id=EvidenceId("SYN-EVIDENCE-DOI-RELATIONSHIP-0001"),
        revision_id=EvidenceId("SYN-EVIDENCE-DOI-RELATIONSHIP-REVISION-0001"),
        relationship_type=relationship_type,
        ordered_sku=ordered,
        candidate_sku=candidate,
        ordered_mfg=same_mfg,
        candidate_mfg=(
            same_mfg
            if relationship_type is AlternateRelationshipType.EXACT_MFG
            else SkuId("SYN-SKU-DOI-MFG-CANDIDATE-0001")
        ),
        compatibility_review_required=functional,
        evidence_source=product_source(candidate),
    )


def observation(relation, *, state=AlternateObservationState.CURRENT):
    context = action_context()
    return DOIAlternateObservation(
        observation_id=EvidenceId("SYN-EVIDENCE-DOI-ALTERNATE-OBSERVATION-0001"),
        action_context_id=context.action_context_id,
        action_context_binding=context.hash_binding(),
        relationship_revision_binding=relation.current_revision.hash_binding(),
        candidate_sku=relation.candidate_sku,
        state=state,
        observed_availability=known_fact(AlternateAvailability.IN_STOCK),
        observed_eta=not_applicable_fact(),
        observed_price=known_fact(usd("15.00")),
        observed_at=OBSERVED_AT,
        source=product_source(relation.candidate_sku),
    )


def exact_observation(
    availability: AlternateAvailability = AlternateAvailability.IN_STOCK,
) -> DOIExactSKUObservation:
    sku = SkuId("SYN-SKU-DOI-ORDERED-0001")
    context = action_context("0002")
    return DOIExactSKUObservation(
        observation_id=EvidenceId("SYN-EVIDENCE-DOI-EXACT-OBSERVATION-0001"),
        action_context_id=context.action_context_id,
        action_context_binding=context.hash_binding(),
        ordered_line_id=LineSnapshotId(
            EvidenceId("SYN-EVIDENCE-DOI-LINE-0001")
        ),
        ordered_sku=sku,
        observed_sku=sku,
        state=AlternateObservationState.CURRENT,
        observed_availability=availability,
        potential_unit_value=usd("10.00"),
        observed_at=OBSERVED_AT,
        source=product_source(sku, "0002"),
    )


class DOIProductKnowledgeTests(unittest.TestCase):
    def test_relationship_hierarchy_stays_distinct_and_product_only(self) -> None:
        expected = {
            AlternateRelationshipType.EXACT_MFG: OpportunityType.EXACT_MFG_ALTERNATE,
            AlternateRelationshipType.MFG_CROSS_REFERENCE: OpportunityType.MFG_CROSS_REFERENCE,
            AlternateRelationshipType.MFG_SUPERSESSION: OpportunityType.MFG_SUPERSESSION,
            AlternateRelationshipType.FUNCTIONAL: OpportunityType.FUNCTIONAL_ALTERNATE,
        }
        for relation_type, opportunity_type in expected.items():
            with self.subTest(relation_type=relation_type.value):
                relation = relationship(relation_type)
                compatibility = (
                    CompatibilityDecision.MORE_EVIDENCE_REQUIRED
                    if relation_type is AlternateRelationshipType.FUNCTIONAL
                    else CompatibilityDecision.NOT_REQUIRED
                )
                candidate = candidate_from_relationship(
                    candidate_id=EvidenceId(
                        f"SYN-EVIDENCE-DOI-CANDIDATE-{len(relation_type.value):04d}"
                    ),
                    relationship=relation,
                    observation=observation(relation),
                    ordered_line_id=LineSnapshotId(
                        EvidenceId("SYN-EVIDENCE-DOI-LINE-0001")
                    ),
                    quantity=PositiveQuantity(2),
                    compatibility_decision=compatibility,
                )
                self.assertEqual(candidate.opportunity_type, opportunity_type)
                expected_validity = (
                    AlternateValidityState.COMPATIBILITY_REVIEW_REQUIRED
                    if relation_type is AlternateRelationshipType.FUNCTIONAL
                    else AlternateValidityState.VERIFIED
                )
                self.assertEqual(candidate.validity, expected_validity)

    def test_revision_history_is_immutable_sequential_and_terminal(self) -> None:
        original = relationship()
        self.assertEqual(
            tuple(
                reason.code
                for reason in original.last_mutation_reasons.reasons
            ),
            ("RC-107",),
        )
        revised = append_relationship_revision(
            original,
            revision_id=EvidenceId("SYN-EVIDENCE-DOI-RELATIONSHIP-REVISION-0002"),
            revision_kind=AlternateRevisionKind.SUPERSEDED,
            state=AlternateRelationshipState.SUPERSEDED,
            compatibility_review_required=False,
            evidence_source=product_source(original.candidate_sku),
        )
        self.assertEqual(len(original.revisions), 1)
        self.assertEqual(len(revised.revisions), 2)
        self.assertEqual(
            tuple(
                reason.code
                for reason in revised.last_mutation_reasons.reasons
            ),
            ("RC-108",),
        )
        self.assertEqual(
            revised.current_revision.predecessor_binding,
            original.current_revision.hash_binding(),
        )
        with self.assertRaises(ProductKnowledgeError) as conflict:
            append_relationship_revision(
                revised,
                revision_id=EvidenceId(
                    "SYN-EVIDENCE-DOI-RELATIONSHIP-REVISION-0003"
                ),
                revision_kind=AlternateRevisionKind.UPDATED,
                state=AlternateRelationshipState.ACTIVE,
                compatibility_review_required=False,
                evidence_source=product_source(revised.candidate_sku),
            )
        self.assertEqual(
            tuple(reason.code for reason in conflict.exception.reasons.reasons),
            ("RC-109",),
        )

    def test_action_context_binding_invalid_emits_rc110(self) -> None:
        relation = relationship()
        valid = observation(relation)
        material = {"action_context_id": "SYN-EVIDENCE-DIFFERENT-CONTEXT"}
        wrong = domain_hash(
            DOIActionContext.HASH_DOMAIN,
            canonical_json_bytes(material, expected_members=set(material)),
        )
        with self.assertRaises(ProductKnowledgeError) as raised:
            dataclasses.replace(valid, action_context_binding=wrong)
        self.assertEqual(
            tuple(reason.code for reason in raised.exception.reasons.reasons),
            ("RC-110",),
        )

    def test_stale_observation_never_binds_as_current(self) -> None:
        relation = relationship()
        stale = observation(relation, state=AlternateObservationState.STALE)
        candidate = candidate_from_relationship(
            candidate_id=EvidenceId("SYN-EVIDENCE-DOI-CANDIDATE-STALE-0001"),
            relationship=relation,
            observation=stale,
            ordered_line_id=LineSnapshotId(EvidenceId("SYN-EVIDENCE-DOI-LINE-0001")),
            quantity=PositiveQuantity(1),
            compatibility_decision=CompatibilityDecision.NOT_REQUIRED,
        )
        self.assertFalse(candidate.current_observation)
        self.assertIsNotNone(candidate.observation_binding)

    def test_exact_sku_requires_typed_current_in_stock_observation(self) -> None:
        accepted = exact_sku_candidate(
            candidate_id=EvidenceId("SYN-EVIDENCE-DOI-EXACT-CANDIDATE-0001"),
            quantity=PositiveQuantity(1),
            observation=exact_observation(),
        )
        self.assertEqual(accepted.observed_availability, AlternateAvailability.IN_STOCK)
        with self.assertRaises(ProductKnowledgeError):
            exact_sku_candidate(
                candidate_id=EvidenceId(
                    "SYN-EVIDENCE-DOI-EXACT-CANDIDATE-0002"
                ),
                quantity=PositiveQuantity(1),
                observation=exact_observation(AlternateAvailability.UNAVAILABLE),
            )

    def test_cross_namespace_customer_or_order_source_is_rejected(self) -> None:
        relation = relationship()
        order = OrderId("SYN-ORDER-DOI-CANARY-0001")
        wrong_source = SourceRef.create(
            source_ref_id=EvidenceId("SYN-EVIDENCE-DOI-WRONG-SOURCE-0001"),
            source_kind=SourceKind.SYNTHETIC_ORDER_FIXTURE,
            object_namespace=SourceObjectNamespace.SYNTHETIC_ORDER,
            object_id=order,
        )
        with self.assertRaises(ProductKnowledgeError) as caught:
            dataclasses.replace(relation.current_revision, evidence_source=wrong_source)
        self.assertIsNone(caught.exception.__cause__)
        self.assertIsNone(caught.exception.__context__)

    def test_product_identity_privacy_canaries_fail_before_alternate_use(self) -> None:
        revision = relationship().current_revision
        canaries = (
            SkuId("SYN-SKU-2025550199"),
            SkuId("SYN-SKU-1HGCM82633A004352"),
            SkuId("SYN-SKU-NAME-JANE-DOE"),
        )
        for index, canary in enumerate(canaries, start=10):
            with self.subTest(index=index):
                with self.assertRaises(ProductKnowledgeError) as caught:
                    dataclasses.replace(
                        revision,
                        candidate_sku=canary,
                        evidence_source=product_source(canary, f"{index:04d}"),
                    )
                self.assertEqual(
                    caught.exception.code,
                    "PRODUCT_IDENTITY_PRIVACY_REJECTED",
                )
                self.assertIsNone(caught.exception.__cause__)
                self.assertIsNone(caught.exception.__context__)

    def test_r01_observation_matrix_is_field_specific(self) -> None:
        relation = relationship()
        observed = dataclasses.replace(
            observation(relation),
            observed_eta=known_fact(OBSERVED_AT),
        )
        cases = (
            ("observed_price", "RC-136"),
            ("observed_availability", "RC-137"),
            ("observed_eta", "RC-138"),
        )
        for field_name, reason in cases:
            with self.subTest(field=field_name, branch="KNOWN"):
                accepted = dataclasses.replace(
                    observed,
                    **{field_name: getattr(observed, field_name)},
                )
                self.assertEqual(getattr(accepted, field_name).tag.value, "KNOWN")
            with self.subTest(field=field_name, branch="UNKNOWN"):
                accepted = dataclasses.replace(
                    observed,
                    **{field_name: unknown_fact(reason)},
                )
                self.assertEqual(getattr(accepted, field_name).reason_code, reason)
            with self.subTest(field=field_name, branch="NOT_APPLICABLE"):
                accepted = dataclasses.replace(
                    observed,
                    **{field_name: not_applicable_fact()},
                )
                self.assertEqual(
                    getattr(accepted, field_name).tag.value,
                    "NOT_APPLICABLE",
                )
            with self.subTest(field=field_name, branch="WRONG_REASON"):
                with self.assertRaises(ProductKnowledgeError):
                    dataclasses.replace(
                        observed,
                        **{field_name: unknown_fact("RC-115")},
                    )
            with self.subTest(field=field_name, branch="ALIAS"):
                with self.assertRaises(ProductKnowledgeError):
                    dataclasses.replace(
                        observed,
                        **{field_name: known_fact("ALIAS")},
                    )

    def test_hash_preimages_are_known_and_collision_safe(self) -> None:
        relation = relationship()
        observed = observation(relation)
        contracts = knowledge_hash_contracts()
        self.assertEqual(len(contracts), 4)
        fixtures = knowledge_hash_fixtures()
        self.assertEqual(
            tuple(row[0] for row in fixtures),
            tuple(sorted(contracts)),
        )
        for _, domain, canonical, digest in fixtures:
            preimage = domain.encode("ascii") + b"\n" + canonical
            self.assertEqual(hashlib.sha256(preimage).hexdigest(), digest)
        for record in (
            relation.current_revision,
            relation,
            observed,
            exact_observation(),
        ):
            with self.subTest(record=type(record).__name__):
                binding = record.hash_binding()
                known_answer = knowledge_hash_known_answer(record)
                self.assertEqual(known_answer.preimage, binding.preimage)
                self.assertEqual(
                    binding.sha256,
                    hashlib.sha256(binding.preimage).hexdigest(),
                )
                self.assertTrue(compare_knowledge_preimages(binding, binding))
        other = relationship(AlternateRelationshipType.MFG_CROSS_REFERENCE)
        self.assertFalse(
            compare_knowledge_preimages(
                relation.hash_binding(),
                other.hash_binding(),
            )
        )
        self.assertEqual(
            relation.current_revision.hash_binding().sha256,
            "703f7f09d996701ced928244e058157cf2a195e9d3b011b717fe4c4bf80f89b8",
        )


if __name__ == "__main__":
    unittest.main()
