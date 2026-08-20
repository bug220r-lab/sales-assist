from __future__ import annotations

import dataclasses
import hashlib
import unittest
from pathlib import Path

from synthetic_sales_assist.domain.canonical import canonical_json_bytes, domain_hash
from synthetic_sales_assist.domain.identities import (
    EvaluationId,
    EvidenceId,
    InteractionId,
    OrderId,
    RunId,
    SkuId,
    SnapshotId,
)
from synthetic_sales_assist.domain.numeric import (
    NonNegativeCount,
    PositiveOrdinal,
    Quantity,
)
from synthetic_sales_assist.domain.records import (
    DomainRecordError,
    ErrorCategory,
    ErrorPathMember,
    EvaluationDimensionBinding,
    EvaluationDimensionRole,
    EvaluationEnvelope,
    EvaluationExplanationItem,
    EvidenceRef,
    HumanReviewRequirement,
    ImmutableEventEnvelope,
    LineManifestEntry,
    ProcessingRunIdentity,
    ReasonSet,
    RequiredSectionProof,
    SnapshotEnvelope,
    SourceKind,
    SourceObjectNamespace,
    SourceRef,
    StructuredDomainError,
    StructuredErrorCode,
    VersionBinding,
    WholeOrderCompletenessProof,
)
from synthetic_sales_assist.domain.registries import load_doi_registries
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp


def _role_binding(domain: str, member: str = "synthetic"):
    return domain_hash(
        domain,
        canonical_json_bytes({"member": member}, expected_members={"member"}),
    )


_DIMENSION_CONTRACTS = {
    EvaluationDimensionRole.SUPPLIED_FACTS: (
        "supplied_facts",
        "shared-evaluation-supplied-facts/v1",
        "supplied_fact",
        "shared-evaluation-supplied-fact-item/v1",
        "shared-evaluation-supplied-fact-content/v1",
    ),
    EvaluationDimensionRole.RULES_EVALUATED: (
        "rules_evaluated",
        "shared-evaluation-rules-evaluated/v1",
        "rule_evaluated",
        "shared-evaluation-rule-evaluated-item/v1",
        "shared-evaluation-rule-evaluated-content/v1",
    ),
    EvaluationDimensionRole.RULES_FIRED: (
        "rules_fired",
        "shared-evaluation-rules-fired/v1",
        "rule_fired",
        "shared-evaluation-rule-fired-item/v1",
        "shared-evaluation-rule-fired-content/v1",
    ),
    EvaluationDimensionRole.RESULT: (
        "result",
        "shared-evaluation-result/v1",
        "result_item",
        "shared-evaluation-result-item/v1",
        "shared-evaluation-result-content/v1",
    ),
    EvaluationDimensionRole.PERSISTENCE_EFFECTS: (
        "persistence_effects",
        "shared-evaluation-persistence-effects/v1",
        "persistence_effect",
        "shared-evaluation-persistence-effect-item/v1",
        "shared-evaluation-persistence-effect-content/v1",
    ),
}


def _dimension(
    role: EvaluationDimensionRole,
    member: str | None,
    *,
    item_id: str | None = None,
) -> EvaluationDimensionBinding:
    default_ids = {
        EvaluationDimensionRole.SUPPLIED_FACTS: "SYN-EVIDENCE-EVAL-FACT-0001",
        EvaluationDimensionRole.RULES_EVALUATED: "SYN-EVIDENCE-EVAL-RULE-0001",
        EvaluationDimensionRole.RULES_FIRED: "SYN-EVIDENCE-EVAL-RULE-0001",
        EvaluationDimensionRole.RESULT: "SYN-EVIDENCE-EVAL-RESULT-0001",
        EvaluationDimensionRole.PERSISTENCE_EFFECTS: "SYN-EVIDENCE-EVAL-EFFECT-0001",
    }
    items = ()
    if member is not None:
        items = (
            EvaluationExplanationItem.create_from_content(
                item_id=EvidenceId(item_id or default_ids[role]),
                role=role,
                content_value={"member": member},
                expected_members={"member"},
            ),
        )
    return EvaluationDimensionBinding.create(
        role=role,
        items=items,
    )


class SharedRecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registries = load_doi_registries()

    def _source(self, suffix: str = "0001") -> SourceRef:
        return SourceRef.create(
            source_ref_id=EvidenceId(f"SYN-EVIDENCE-SOURCE-{suffix}"),
            source_kind=SourceKind.SYNTHETIC_ORDER_FIXTURE,
            object_namespace=SourceObjectNamespace.SYNTHETIC_ORDER,
            object_id=OrderId(f"SYN-ORDER-SHARED-{suffix}"),
        )

    def _proof(
        self,
        source: SourceRef,
        *,
        order_id: str = "SYN-ORDER-SHARED-0001",
    ) -> WholeOrderCompletenessProof:
        observed_at = CanonicalTimestamp("2026-08-10T12:34:56.12Z")
        line = LineManifestEntry(
            EvidenceId("SYN-EVIDENCE-LINE-0001"),
            PositiveOrdinal(1),
            source,
            _role_binding(LineManifestEntry.CONTENT_DOMAIN, "line-1"),
        )
        section_proofs = tuple(
            RequiredSectionProof.complete(
                section=section,
                source=source,
                observed_at=observed_at,
            )
            for section in WholeOrderCompletenessProof.REQUIRED_SECTIONS
        )
        return WholeOrderCompletenessProof(
            requested_order_id=OrderId(order_id),
            observed_order_id=OrderId(order_id),
            schema=VersionBinding(
                "whole_order_completeness",
                WholeOrderCompletenessProof.SCHEMA_VERSION,
            ),
            extractor=VersionBinding("extractor", "shared-extractor/v1"),
            fixture=VersionBinding("fixture", "shared-fixture/v1"),
            order_source_observed_at=observed_at,
            proof_source_observed_at=CanonicalTimestamp(
                "2026-08-10T08:34:56.12-04:00"
            ),
            required_sections=WholeOrderCompletenessProof.REQUIRED_SECTIONS,
            section_proofs=section_proofs,
            declared_relevant_line_count=NonNegativeCount(1),
            observed_relevant_line_count=NonNegativeCount(1),
            ordered_line_manifest=(line,),
            duplicate_rule=VersionBinding(
                "duplicate_rule",
                "shared-duplicate-rule/v1",
            ),
            reordering_rule=VersionBinding(
                "reordering_rule",
                "shared-reordering-rule/v1",
            ),
            source_refs=(source,),
            coherence_state="COHERENT",
            change_detection_state="UNCHANGED",
            empty_universe_proved=False,
        )

    def _hash_record_cases(
        self,
    ) -> tuple[tuple[str, type[object], dict[str, object], str, str], ...]:
        source = self._source()
        evidence = EvidenceRef(
            EvidenceId("SYN-EVIDENCE-ITEM-0001"),
            source,
            VersionBinding("evidence", "shared-evidence/v1"),
            _role_binding(EvidenceRef.CONTENT_DOMAIN, "evidence"),
        )
        run = ProcessingRunIdentity(
            RunId("SYN-RUN-SHARED-0001"),
            VersionBinding("run", "shared-run/v1"),
            _role_binding(ProcessingRunIdentity.REQUEST_DOMAIN),
        )
        proof = self._proof(source)
        snapshot = SnapshotEnvelope(
            snapshot_id=SnapshotId("SYN-SNAPSHOT-SHARED-0001"),
            run_id=run.run_id,
            schema=VersionBinding("snapshot", "shared-snapshot/v1"),
            payload=_role_binding(SnapshotEnvelope.PAYLOAD_DOMAIN),
            completeness_proof=proof,
            source_refs=(source,),
        )
        reasons = ReasonSet((self.registries.reason_ref("RC-001"),))
        evaluation = EvaluationEnvelope(
            evaluation_id=EvaluationId("SYN-EVALUATION-SHARED-0001"),
            snapshot_id=snapshot.snapshot_id,
            run_id=run.run_id,
            schema=VersionBinding("evaluation", "shared-evaluation/v1"),
            rule_pack=VersionBinding("rule_pack", "shared-rule-pack/v1"),
            supplied_facts=_dimension(
                EvaluationDimensionRole.SUPPLIED_FACTS,
                "supplied-facts",
            ),
            rules_evaluated=_dimension(
                EvaluationDimensionRole.RULES_EVALUATED,
                "rules-evaluated",
            ),
            rules_fired=_dimension(EvaluationDimensionRole.RULES_FIRED, None),
            reasons=reasons,
            result=_dimension(EvaluationDimensionRole.RESULT, "result"),
            human_review=HumanReviewRequirement(True, reasons),
            persistence_effects=_dimension(
                EvaluationDimensionRole.PERSISTENCE_EFFECTS,
                None,
            ),
        )
        event = ImmutableEventEnvelope(
            InteractionId("SYN-INTERACTION-EVENT-0001"),
            run.run_id,
            CanonicalTimestamp("2026-08-10T12:34:56.12Z"),
            "SHARED_RECORD_ACCEPTED",
            VersionBinding("event", "shared-event/v1"),
            _role_binding(
                ImmutableEventEnvelope.PAYLOAD_DOMAIN,
                snapshot.hash_binding().sha256,
            ),
            (VersionBinding("snapshot", "shared-snapshot/v1"),),
        )
        return (
            (
                "SourceRef",
                SourceRef,
                {
                    "source_ref_id": source.source_ref_id,
                    "source_kind": source.source_kind,
                    "object_namespace": source.object_namespace,
                    "object_id": source.object_id,
                    "schema": source.schema,
                    "content": source.content,
                },
                "source",
                "shared-source/v1",
            ),
            (
                "EvidenceRef",
                EvidenceRef,
                {
                    "evidence_id": evidence.evidence_id,
                    "source": evidence.source,
                    "schema": evidence.schema,
                    "content": evidence.content,
                },
                "evidence",
                "shared-evidence/v1",
            ),
            (
                "ProcessingRunIdentity",
                ProcessingRunIdentity,
                {"run_id": run.run_id, "schema": run.schema, "request": run.request},
                "run",
                "shared-run/v1",
            ),
            (
                "WholeOrderCompletenessProof",
                WholeOrderCompletenessProof,
                {
                    "requested_order_id": proof.requested_order_id,
                    "observed_order_id": proof.observed_order_id,
                    "schema": proof.schema,
                    "extractor": proof.extractor,
                    "fixture": proof.fixture,
                    "order_source_observed_at": proof.order_source_observed_at,
                    "proof_source_observed_at": proof.proof_source_observed_at,
                    "required_sections": proof.required_sections,
                    "section_proofs": proof.section_proofs,
                    "declared_relevant_line_count": proof.declared_relevant_line_count,
                    "observed_relevant_line_count": proof.observed_relevant_line_count,
                    "ordered_line_manifest": proof.ordered_line_manifest,
                    "duplicate_rule": proof.duplicate_rule,
                    "reordering_rule": proof.reordering_rule,
                    "source_refs": proof.source_refs,
                    "coherence_state": proof.coherence_state,
                    "change_detection_state": proof.change_detection_state,
                    "empty_universe_proved": proof.empty_universe_proved,
                },
                "whole_order_completeness",
                WholeOrderCompletenessProof.SCHEMA_VERSION,
            ),
            *tuple(
                (
                    f"EvaluationDimension:{role.value}",
                    EvaluationDimensionBinding,
                    {
                        "role": dimension.role,
                        "schema": dimension.schema,
                        "items": dimension.items,
                        "explicitly_empty": dimension.explicitly_empty,
                    },
                    _DIMENSION_CONTRACTS[role][0],
                    _DIMENSION_CONTRACTS[role][1],
                )
                for role, dimension in (
                    (EvaluationDimensionRole.SUPPLIED_FACTS, evaluation.supplied_facts),
                    (EvaluationDimensionRole.RULES_EVALUATED, evaluation.rules_evaluated),
                    (EvaluationDimensionRole.RULES_FIRED, evaluation.rules_fired),
                    (EvaluationDimensionRole.RESULT, evaluation.result),
                    (
                        EvaluationDimensionRole.PERSISTENCE_EFFECTS,
                        evaluation.persistence_effects,
                    ),
                )
            ),
            (
                "SnapshotEnvelope",
                SnapshotEnvelope,
                {
                    "snapshot_id": snapshot.snapshot_id,
                    "run_id": snapshot.run_id,
                    "schema": snapshot.schema,
                    "payload": snapshot.payload,
                    "completeness_proof": snapshot.completeness_proof,
                    "source_refs": snapshot.source_refs,
                },
                "snapshot",
                "shared-snapshot/v1",
            ),
            (
                "EvaluationEnvelope",
                EvaluationEnvelope,
                {
                    "evaluation_id": evaluation.evaluation_id,
                    "snapshot_id": evaluation.snapshot_id,
                    "run_id": evaluation.run_id,
                    "schema": evaluation.schema,
                    "rule_pack": evaluation.rule_pack,
                    "supplied_facts": evaluation.supplied_facts,
                    "rules_evaluated": evaluation.rules_evaluated,
                    "rules_fired": evaluation.rules_fired,
                    "reasons": evaluation.reasons,
                    "result": evaluation.result,
                    "human_review": evaluation.human_review,
                    "persistence_effects": evaluation.persistence_effects,
                },
                "evaluation",
                "shared-evaluation/v1",
            ),
            (
                "ImmutableEventEnvelope",
                ImmutableEventEnvelope,
                {
                    "event_id": event.event_id,
                    "run_id": event.run_id,
                    "occurred_at": event.occurred_at,
                    "event_kind": event.event_kind,
                    "schema": event.schema,
                    "payload": event.payload,
                    "versions": event.versions,
                },
                "event",
                "shared-event/v1",
            ),
        )

    def test_version_hash_source_and_evidence_bindings_are_explicit(self) -> None:
        source = self._source()
        evidence = EvidenceRef(
            EvidenceId("SYN-EVIDENCE-ITEM-0001"),
            source,
            VersionBinding("evidence", "shared-evidence/v1"),
            _role_binding(EvidenceRef.CONTENT_DOMAIN, "evidence"),
        )

        source_hash = source.hash_binding()
        evidence_hash = evidence.hash_binding()
        self.assertEqual(source_hash.domain, SourceRef.HASH_DOMAIN)
        expected_preimage = (
            source_hash.domain.encode() + b"\n" + source_hash.canonical_bytes
        )
        self.assertEqual(source_hash.preimage, expected_preimage)
        self.assertEqual(
            source_hash.sha256,
            hashlib.sha256(source_hash.preimage).hexdigest(),
        )
        self.assertNotEqual(source_hash.sha256, evidence_hash.sha256)

    def test_snapshot_run_and_event_envelopes_are_stable(self) -> None:
        source = self._source()
        snapshot_schema = VersionBinding("snapshot", "shared-snapshot/v1")
        event_schema = VersionBinding("event", "shared-event/v1")
        payload = _role_binding(SnapshotEnvelope.PAYLOAD_DOMAIN)
        run = ProcessingRunIdentity(
            RunId("SYN-RUN-SHARED-0001"),
            VersionBinding("run", "shared-run/v1"),
            _role_binding(ProcessingRunIdentity.REQUEST_DOMAIN),
        )
        snapshot = SnapshotEnvelope(
            snapshot_id=SnapshotId("SYN-SNAPSHOT-SHARED-0001"),
            run_id=run.run_id,
            schema=snapshot_schema,
            payload=payload,
            completeness_proof=self._proof(source),
            source_refs=(source,),
        )
        event = ImmutableEventEnvelope(
            InteractionId("SYN-INTERACTION-EVENT-0001"),
            run.run_id,
            CanonicalTimestamp("2026-08-10T12:34:56.12Z"),
            "SHARED_RECORD_ACCEPTED",
            event_schema,
            _role_binding(
                ImmutableEventEnvelope.PAYLOAD_DOMAIN,
                snapshot.hash_binding().sha256,
            ),
            (snapshot_schema,),
        )

        self.assertEqual(snapshot.canonical_bytes(), snapshot.canonical_bytes())
        self.assertEqual(event.hash_binding().domain, ImmutableEventEnvelope.HASH_DOMAIN)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            event.event_kind = "CHANGED"  # type: ignore[misc]

    def test_every_envelope_has_a_pinned_hash_preimage_oracle(self) -> None:
        source = self._source()
        evidence = EvidenceRef(
            EvidenceId("SYN-EVIDENCE-ITEM-0001"),
            source,
            VersionBinding("evidence", "shared-evidence/v1"),
            _role_binding(EvidenceRef.CONTENT_DOMAIN, "evidence"),
        )
        run = ProcessingRunIdentity(
            RunId("SYN-RUN-SHARED-0001"),
            VersionBinding("run", "shared-run/v1"),
            _role_binding(ProcessingRunIdentity.REQUEST_DOMAIN),
        )
        proof = self._proof(source)
        snapshot = SnapshotEnvelope(
            snapshot_id=SnapshotId("SYN-SNAPSHOT-SHARED-0001"),
            run_id=run.run_id,
            schema=VersionBinding("snapshot", "shared-snapshot/v1"),
            payload=_role_binding(SnapshotEnvelope.PAYLOAD_DOMAIN),
            completeness_proof=proof,
            source_refs=(source,),
        )
        reasons = ReasonSet((self.registries.reason_ref("RC-001"),))
        supplied_facts = _dimension(
            EvaluationDimensionRole.SUPPLIED_FACTS,
            "supplied-facts",
        )
        rules_evaluated = _dimension(
            EvaluationDimensionRole.RULES_EVALUATED,
            "rules-evaluated",
        )
        rules_fired = _dimension(EvaluationDimensionRole.RULES_FIRED, None)
        result = _dimension(EvaluationDimensionRole.RESULT, "result")
        persistence_effects = _dimension(
            EvaluationDimensionRole.PERSISTENCE_EFFECTS,
            None,
        )
        evaluation = EvaluationEnvelope(
            evaluation_id=EvaluationId("SYN-EVALUATION-SHARED-0001"),
            snapshot_id=snapshot.snapshot_id,
            run_id=run.run_id,
            schema=VersionBinding("evaluation", "shared-evaluation/v1"),
            rule_pack=VersionBinding("rule_pack", "shared-rule-pack/v1"),
            supplied_facts=supplied_facts,
            rules_evaluated=rules_evaluated,
            rules_fired=rules_fired,
            reasons=reasons,
            result=result,
            human_review=HumanReviewRequirement(True, reasons),
            persistence_effects=persistence_effects,
        )
        event = ImmutableEventEnvelope(
            InteractionId("SYN-INTERACTION-EVENT-0001"),
            run.run_id,
            CanonicalTimestamp("2026-08-10T12:34:56.12Z"),
            "SHARED_RECORD_ACCEPTED",
            VersionBinding("event", "shared-event/v1"),
            _role_binding(
                ImmutableEventEnvelope.PAYLOAD_DOMAIN,
                snapshot.hash_binding().sha256,
            ),
            (VersionBinding("snapshot", "shared-snapshot/v1"),),
        )
        bindings = {
            "SourceRef": source.hash_binding(),
            "EvidenceRef": evidence.hash_binding(),
            "ProcessingRunIdentity": run.hash_binding(),
            **{
                f"RequiredSection:{section.section}": section.hash_binding()
                for section in proof.section_proofs
            },
            "LineManifest": proof.manifest_binding,
            "WholeOrderCompletenessProof": proof.hash_binding(),
            "SnapshotEnvelope": snapshot.hash_binding(),
            "EvaluationDimension:SUPPLIED_FACTS": supplied_facts.hash_binding(),
            "EvaluationDimension:RULES_EVALUATED": rules_evaluated.hash_binding(),
            "EvaluationDimension:RULES_FIRED": rules_fired.hash_binding(),
            "EvaluationDimension:RESULT": result.hash_binding(),
            "EvaluationDimension:PERSISTENCE_EFFECTS": (
                persistence_effects.hash_binding()
            ),
            "EvaluationEnvelope": evaluation.hash_binding(),
            "ImmutableEventEnvelope": event.hash_binding(),
        }
        expected = {
            "SourceRef": (
                "d2cdc91b11245c5d174e6ffb1d0e1a4"
                "dca0fcf2c7b482921ceec082a46cae581"
            ),
            "EvidenceRef": (
                "731db1044c2ef9c46451b118c7e9adca"
                "f41e695eef3095f19dc40c46c7c1c97b"
            ),
            "ProcessingRunIdentity": (
                "901d01972b3b537b46c1275c4f1eab82"
                "2ff23e4bd07f54da6f65e257391a4c3b"
            ),
            "RequiredSection:ORDER_IDENTITY": (
                "6356dd0632a30c5d67f38a179b33e3f4"
                "3d20ad2fc78dce6830bbbfc04fc9b20b"
            ),
            "RequiredSection:ORDER_FACTS": (
                "c796fbefad1298f0682b817200d899c41"
                "cb96a74423d02a56011993b3ebd2f5b"
            ),
            "RequiredSection:LINE_ITEMS": (
                "e3a131312b60c9f6449875bedd4f3422"
                "c2c452682f4e696b8dea68dad559099f"
            ),
            "RequiredSection:WWC_FINDING": (
                "ffc3a776d61fa6285a7b744e73d62950"
                "0e5a8ef413ec3c6ced193ec3b72fbac9"
            ),
            "RequiredSection:DEDUPE_FINDING": (
                "b1eab1efd04245d36710f32be485705f"
                "7eefaa10e8e0e199585361038c893b59"
            ),
            "LineManifest": (
                "7b5e8d3729e55492807ec9f7f4b30bf"
                "88539d42a2f322a5ed83f13ca94e9e5d3"
            ),
            "WholeOrderCompletenessProof": (
                "98a0057b5b5035328760d4ea9117ba81"
                "fa0a3ead5ba181d8523abc2b29c2d752"
            ),
            "SnapshotEnvelope": (
                "fe845e57d14230d33a14fe1b07e3ffe"
                "b8cf0c2ac18f18ca2b87ec2be07b62809"
            ),
            "EvaluationDimension:SUPPLIED_FACTS": (
                "ba3f9349f67ae78d935f2b7d4c098b6"
                "0597854a5e1c6d25a2842fc9c06e75285"
            ),
            "EvaluationDimension:RULES_EVALUATED": (
                "720beefe28586d4b33c302623687adc3"
                "a2d934f938844d067142fdf092f88d58"
            ),
            "EvaluationDimension:RULES_FIRED": (
                "5bfe30f3e569cd4b83715f9391e07911"
                "90bd7a73fcc9d18208b59bd6c3e6f936"
            ),
            "EvaluationDimension:RESULT": (
                "1cfd6ad7295ee202bad9557382769bbc"
                "622b7bb76d0beee5df3a71e18fe6b6d9"
            ),
            "EvaluationDimension:PERSISTENCE_EFFECTS": (
                "21e7f150c8c06f266b319044b9bad54e"
                "1ca268ad28192e472d40a9969d27216e"
            ),
            "EvaluationEnvelope": (
                "b29920a75deea81054acc654d63d9224"
                "18c675bde038de36364caf69b0229a23"
            ),
            "ImmutableEventEnvelope": (
                "fa589e3a849cdc55b70f50205bdda6a8"
                "ad7be6860c9b618102d99c673896458d"
            ),
        }
        self.assertEqual(set(bindings), set(expected))
        published = (
            Path(__file__).resolve().parents[1]
            / "docs"
            / "milestone1-hash-preimages.md"
        ).read_text(encoding="utf-8")
        for name, binding in bindings.items():
            with self.subTest(name=name):
                self.assertEqual(binding.sha256, expected[name])
                self.assertEqual(binding.preimage.count(b"\n"), 1)
                self.assertEqual(
                    binding.preimage,
                    binding.domain.encode("ascii") + b"\n" + binding.canonical_bytes,
                )
                self.assertIn(name, published)
                self.assertIn(binding.domain, published)
                self.assertIn(binding.sha256, published)
                self.assertIn(binding.canonical_bytes.decode("utf-8"), published)

    def test_reason_set_review_and_evaluation_are_registry_backed(self) -> None:
        reason = self.registries.reason_ref("RC-001")
        reasons = ReasonSet((reason,))
        review = HumanReviewRequirement(True, reasons)
        evaluation = EvaluationEnvelope(
            evaluation_id=EvaluationId("SYN-EVALUATION-SHARED-0001"),
            snapshot_id=SnapshotId("SYN-SNAPSHOT-SHARED-0001"),
            run_id=RunId("SYN-RUN-SHARED-0001"),
            schema=VersionBinding("evaluation", "shared-evaluation/v1"),
            rule_pack=VersionBinding("rule_pack", "shared-rule-pack/v1"),
            supplied_facts=_dimension(
                EvaluationDimensionRole.SUPPLIED_FACTS,
                "supplied-facts",
            ),
            rules_evaluated=_dimension(
                EvaluationDimensionRole.RULES_EVALUATED,
                "rules-evaluated",
            ),
            rules_fired=_dimension(EvaluationDimensionRole.RULES_FIRED, None),
            reasons=reasons,
            result=_dimension(EvaluationDimensionRole.RESULT, "result"),
            human_review=review,
            persistence_effects=_dimension(
                EvaluationDimensionRole.PERSISTENCE_EFFECTS,
                None,
            ),
        )
        self.assertIn(b'"code":"RC-001"', evaluation.canonical_bytes())
        self.assertIn(
            b'"registry_version":"synthetic-doi-reason-registry/v1.0.1"',
            evaluation.canonical_bytes(),
        )
        self.assertEqual(evaluation.hash_binding().domain, EvaluationEnvelope.HASH_DOMAIN)

    def test_snapshot_and_evaluation_explain_all_required_neutral_dimensions(self) -> None:
        cases = {
            name: constructor(**values)
            for name, constructor, values, _, _ in self._hash_record_cases()
        }
        snapshot = cases["SnapshotEnvelope"]
        evaluation = cases["EvaluationEnvelope"]
        self.assertEqual(
            set(snapshot.to_dict()),  # type: ignore[attr-defined]
            {
                "completeness_proof",
                "payload",
                "run_id",
                "schema",
                "snapshot_id",
                "source_refs",
            },
        )
        self.assertEqual(
            set(evaluation.to_dict()),  # type: ignore[attr-defined]
            {
                "evaluation_id",
                "human_review",
                "persistence_effects",
                "reasons",
                "result",
                "rule_pack",
                "rules_evaluated",
                "rules_fired",
                "run_id",
                "schema",
                "snapshot_id",
                "supplied_facts",
            },
        )

    def test_semantic_hash_roles_are_domain_separated_and_keyword_only(self) -> None:
        cases = {
            name: (constructor, values)
            for name, constructor, values, _, _ in self._hash_record_cases()
        }
        expected_hash_domains = {
            "SourceRef": {"content": SourceRef.CONTENT_DOMAIN},
            "EvidenceRef": {"content": EvidenceRef.CONTENT_DOMAIN},
            "ProcessingRunIdentity": {
                "request": ProcessingRunIdentity.REQUEST_DOMAIN
            },
            "SnapshotEnvelope": {
                "payload": SnapshotEnvelope.PAYLOAD_DOMAIN,
            },
            "ImmutableEventEnvelope": {
                "payload": ImmutableEventEnvelope.PAYLOAD_DOMAIN
            },
        }
        for name, domains in expected_hash_domains.items():
            constructor, values = cases[name]
            for field_name, expected_domain in domains.items():
                with self.subTest(name=name, field=field_name):
                    actual_domain = values[field_name].domain  # type: ignore[attr-defined]
                    self.assertEqual(actual_domain, expected_domain)
                    wrong_role = dict(values)
                    wrong_role[field_name] = _role_binding("shared-payload/v1")
                    with self.assertRaises(DomainRecordError):
                        constructor(**wrong_role)

        snapshot_constructor, snapshot_values = cases["SnapshotEnvelope"]
        proof = snapshot_values["completeness_proof"]
        self.assertEqual(
            proof.hash_binding().domain,  # type: ignore[attr-defined]
            SnapshotEnvelope.COMPLETENESS_PROOF_DOMAIN,
        )
        wrong_snapshot = dict(snapshot_values)
        wrong_snapshot["completeness_proof"] = _role_binding(
            SnapshotEnvelope.COMPLETENESS_PROOF_DOMAIN
        )
        with self.assertRaises(DomainRecordError):
            snapshot_constructor(**wrong_snapshot)

        evaluation_constructor, evaluation_values = cases["EvaluationEnvelope"]
        dimension_roles = {
            "supplied_facts": EvaluationDimensionRole.SUPPLIED_FACTS,
            "rules_evaluated": EvaluationDimensionRole.RULES_EVALUATED,
            "rules_fired": EvaluationDimensionRole.RULES_FIRED,
            "result": EvaluationDimensionRole.RESULT,
            "persistence_effects": EvaluationDimensionRole.PERSISTENCE_EFFECTS,
        }
        for field_name, role in dimension_roles.items():
            dimension = evaluation_values[field_name]
            self.assertEqual(
                dimension.hash_domain,  # type: ignore[attr-defined]
                _DIMENSION_CONTRACTS[role][1],
            )
            alternate = (
                EvaluationDimensionRole.RESULT
                if role is EvaluationDimensionRole.SUPPLIED_FACTS
                else EvaluationDimensionRole.SUPPLIED_FACTS
            )
            wrong_evaluation = dict(evaluation_values)
            wrong_evaluation[field_name] = _dimension(alternate, "alternate")
            with self.assertRaises(DomainRecordError):
                evaluation_constructor(**wrong_evaluation)

        with self.assertRaises(TypeError):
            snapshot_constructor(*snapshot_values.values())
        with self.assertRaises(TypeError):
            evaluation_constructor(*evaluation_values.values())

    def test_completeness_proof_closes_identity_time_counts_manifest_and_state(self) -> None:
        source = self._source()
        proof = self._proof(source)
        self.assertEqual(proof.requested_order_id, proof.observed_order_id)
        self.assertEqual(proof.declared_relevant_line_count, NonNegativeCount(1))
        self.assertEqual(proof.manifest_binding.domain, proof.MANIFEST_DOMAIN)
        self.assertEqual(proof.hash_binding().domain, proof.HASH_DOMAIN)

        invalid_changes = (
            {"observed_order_id": OrderId("SYN-ORDER-SHARED-OTHER")},
            {
                "proof_source_observed_at": CanonicalTimestamp(
                    "2026-08-10T12:34:57.12Z"
                )
            },
            {"observed_relevant_line_count": NonNegativeCount(0)},
            {"declared_relevant_line_count": NonNegativeCount(0)},
            {"required_sections": ()},
            {"required_sections": ("FAKE",)},
            {"required_sections": tuple(reversed(proof.required_sections))},
            {"section_proofs": proof.section_proofs[:1]},
            {"source_refs": ()},
            {"coherence_state": "INCOHERENT"},
            {"change_detection_state": "CHANGED"},
            {"empty_universe_proved": True},
        )
        for changes in invalid_changes:
            with self.subTest(field=next(iter(changes))):
                with self.assertRaises(DomainRecordError):
                    dataclasses.replace(proof, **changes)

        empty_proof = dataclasses.replace(
            proof,
            declared_relevant_line_count=NonNegativeCount(0),
            observed_relevant_line_count=NonNegativeCount(0),
            ordered_line_manifest=(),
            empty_universe_proved=True,
        )
        self.assertTrue(empty_proof.empty_universe_proved)
        self.assertEqual(empty_proof.manifest_binding.preimage.count(b"\n"), 1)

        for flag in (
            "readable",
            "hidden_regions_exhausted",
            "paginated_regions_exhausted",
            "collapsed_regions_exhausted",
        ):
            with self.subTest(section_flag=flag):
                with self.assertRaises(DomainRecordError):
                    invalid_section = dataclasses.replace(
                        proof.section_proofs[0],
                        **{flag: False},
                    )
                    dataclasses.replace(
                        proof,
                        section_proofs=(invalid_section,) + proof.section_proofs[1:],
                    )

        for field_name, binding in (
            (
                "extractor",
                VersionBinding("extractor", "unsupported-extractor/v99"),
            ),
            (
                "fixture",
                VersionBinding("fixture", "unsupported-fixture/v99"),
            ),
            (
                "duplicate_rule",
                VersionBinding("duplicate_rule", "unsupported-duplicate-rule/v99"),
            ),
            (
                "reordering_rule",
                VersionBinding("reordering_rule", "unsupported-reordering-rule/v99"),
            ),
        ):
            with self.subTest(unsupported_version=field_name):
                with self.assertRaises(DomainRecordError):
                    dataclasses.replace(proof, **{field_name: binding})

        conflicting_source = SourceRef.create(
            source_ref_id=source.source_ref_id,
            source_kind=SourceKind.SYNTHETIC_ORDER_FIXTURE,
            object_namespace=SourceObjectNamespace.SYNTHETIC_ORDER,
            object_id=OrderId("SYN-ORDER-SOURCE-CONFLICT-0001"),
        )
        conflicting_line = dataclasses.replace(
            proof.ordered_line_manifest[0],
            source=conflicting_source,
        )
        with self.assertRaises(DomainRecordError):
            dataclasses.replace(
                proof,
                ordered_line_manifest=(conflicting_line,),
            )
        conflicting_section = dataclasses.replace(
            proof.section_proofs[0],
            source=conflicting_source,
        )
        with self.assertRaises(DomainRecordError):
            dataclasses.replace(
                proof,
                section_proofs=(conflicting_section,) + proof.section_proofs[1:],
            )
        interaction_source = SourceRef.create(
            source_ref_id=source.source_ref_id,
            source_kind=SourceKind.SYNTHETIC_INTERACTION_FIXTURE,
            object_namespace=SourceObjectNamespace.SYNTHETIC_INTERACTION,
            object_id=InteractionId("SYN-INTERACTION-SOURCE-0001"),
        )
        interaction_line = dataclasses.replace(
            proof.ordered_line_manifest[0],
            source=interaction_source,
        )
        interaction_sections = tuple(
            dataclasses.replace(section, source=interaction_source)
            for section in proof.section_proofs
        )
        with self.assertRaises(DomainRecordError):
            dataclasses.replace(
                proof,
                source_refs=(interaction_source,),
                ordered_line_manifest=(interaction_line,),
                section_proofs=interaction_sections,
            )
        product_source = SourceRef.create(
            source_ref_id=source.source_ref_id,
            source_kind=SourceKind.SYNTHETIC_PRODUCT_FIXTURE,
            object_namespace=SourceObjectNamespace.SYNTHETIC_PRODUCT,
            object_id=SkuId("SYN-SKU-SOURCE-0001"),
        )
        product_line = dataclasses.replace(
            proof.ordered_line_manifest[0],
            source=product_source,
        )
        product_sections = tuple(
            dataclasses.replace(section, source=product_source)
            for section in proof.section_proofs
        )
        with self.assertRaises(DomainRecordError):
            dataclasses.replace(
                proof,
                source_refs=(product_source,),
                ordered_line_manifest=(product_line,),
                section_proofs=product_sections,
            )
        cross_order_source = SourceRef.create(
            source_ref_id=source.source_ref_id,
            source_kind=SourceKind.SYNTHETIC_ORDER_FIXTURE,
            object_namespace=SourceObjectNamespace.SYNTHETIC_ORDER,
            object_id=OrderId("SYN-ORDER-SHARED-9999"),
        )
        cross_order_line = dataclasses.replace(
            proof.ordered_line_manifest[0],
            source=cross_order_source,
        )
        cross_order_sections = tuple(
            dataclasses.replace(section, source=cross_order_source)
            for section in proof.section_proofs
        )
        with self.assertRaises(DomainRecordError):
            dataclasses.replace(
                proof,
                source_refs=(cross_order_source,),
                ordered_line_manifest=(cross_order_line,),
                section_proofs=cross_order_sections,
            )
        extra_source = self._source("0002")
        with self.assertRaises(DomainRecordError):
            dataclasses.replace(
                proof,
                source_refs=(source, extra_source),
            )

        class StringAlias(str):
            pass

        with self.assertRaises(DomainRecordError):
            dataclasses.replace(proof, coherence_state=StringAlias("COHERENT"))
        with self.assertRaises(DomainRecordError):
            dataclasses.replace(proof, change_detection_state=StringAlias("UNCHANGED"))
        with self.assertRaises(DomainRecordError):
            dataclasses.replace(proof, declared_relevant_line_count=Quantity(1))

        first_line = proof.ordered_line_manifest[0]
        duplicate_ordinal = dataclasses.replace(
            first_line,
            line_id=EvidenceId("SYN-EVIDENCE-LINE-0002"),
        )
        duplicate_line_id = dataclasses.replace(
            first_line,
            ordinal=PositiveOrdinal(2),
        )
        for second_line in (duplicate_ordinal, duplicate_line_id):
            with self.subTest(manifest_conflict=second_line.ordinal.value):
                with self.assertRaises(DomainRecordError):
                    dataclasses.replace(
                        proof,
                        declared_relevant_line_count=NonNegativeCount(2),
                        observed_relevant_line_count=NonNegativeCount(2),
                        ordered_line_manifest=(first_line, second_line),
                    )

        for changes in (
            {
                "schema": VersionBinding(
                    "required_section",
                    "shared-required-section/v2",
                )
            },
            {
                "exhaustion_strategy": VersionBinding(
                    "section_exhaustion",
                    "shared-section-exhaustion/v2",
                )
            },
            {"source": None},
        ):
            with self.subTest(section_contract=next(iter(changes))):
                with self.assertRaises(DomainRecordError):
                    dataclasses.replace(proof.section_proofs[0], **changes)

        mismatched_section_time = dataclasses.replace(
            proof.section_proofs[0],
            observed_at=CanonicalTimestamp("2026-08-10T12:34:57.12Z"),
        )
        with self.assertRaises(DomainRecordError):
            dataclasses.replace(
                proof,
                section_proofs=(mismatched_section_time,) + proof.section_proofs[1:],
            )

    def test_evaluation_dimensions_are_closed_and_explicit_about_empty_sets(self) -> None:
        for role in (
            EvaluationDimensionRole.SUPPLIED_FACTS,
            EvaluationDimensionRole.RULES_EVALUATED,
            EvaluationDimensionRole.RESULT,
        ):
            with self.subTest(role=role.value):
                with self.assertRaises(DomainRecordError):
                    _dimension(role, None)
        for role in (
            EvaluationDimensionRole.RULES_FIRED,
            EvaluationDimensionRole.PERSISTENCE_EFFECTS,
        ):
            with self.subTest(role=role.value):
                dimension = _dimension(role, None)
                self.assertTrue(dimension.explicitly_empty)
                self.assertEqual(dimension.items, ())

        component, version, _, _, _ = _DIMENSION_CONTRACTS[
            EvaluationDimensionRole.SUPPLIED_FACTS
        ]
        with self.assertRaises(DomainRecordError):
            EvaluationDimensionBinding(
                role=EvaluationDimensionRole.SUPPLIED_FACTS,
                schema=VersionBinding(component, version),
                items=(_role_binding("shared-payload/v1"),),  # type: ignore[arg-type]
                explicitly_empty=False,
            )

    def test_evaluation_explanation_items_are_closed_enumerable_and_coherent(self) -> None:
        supplied = _dimension(EvaluationDimensionRole.SUPPLIED_FACTS, "supplied-facts")
        item = supplied.items[0]
        self.assertIs(type(item.item_id), EvidenceId)
        self.assertEqual(item.role, EvaluationDimensionRole.SUPPLIED_FACTS)
        self.assertNotIn(item.item_id.value, repr(item))

        for changes in (
            {"item_id": None},
            {"role": EvaluationDimensionRole.RESULT},
            {"schema": VersionBinding("supplied_fact", "shared-value/v1")},
            {"content": _role_binding("shared-payload/v1")},
        ):
            with self.subTest(item_field=next(iter(changes))):
                with self.assertRaises(DomainRecordError):
                    dataclasses.replace(item, **changes)

        values = {
            "item_id": item.item_id,
            "role": item.role,
            "schema": item.schema,
            "content": item.content,
        }
        for field_name in values:
            missing = dict(values)
            del missing[field_name]
            with self.subTest(item_missing=field_name):
                with self.assertRaises(TypeError):
                    EvaluationExplanationItem(**missing)
        extra = dict(values)
        extra["unexpected_member"] = None
        with self.assertRaises(TypeError):
            EvaluationExplanationItem(**extra)

        base = supplied.items[0]
        maximum_items = tuple(
            dataclasses.replace(
                base,
                item_id=EvidenceId(f"SYN-EVIDENCE-EVAL-FACT-{index:04d}"),
            )
            for index in range(1, 1025)
        )
        accepted = dataclasses.replace(supplied, items=maximum_items)
        self.assertEqual(len(accepted.items), 1024)
        with self.assertRaises(DomainRecordError):
            dataclasses.replace(
                supplied,
                items=maximum_items
                + (
                    dataclasses.replace(
                        base,
                        item_id=EvidenceId("SYN-EVIDENCE-EVAL-FACT-1025"),
                    ),
                ),
            )
        with self.assertRaises(DomainRecordError):
            dataclasses.replace(supplied, items=(base, base))

        cases = {
            name: constructor(**record_values)
            for name, constructor, record_values, _, _ in self._hash_record_cases()
        }
        evaluation = cases["EvaluationEnvelope"]
        fired = _dimension(EvaluationDimensionRole.RULES_FIRED, "rule-fired")
        dataclasses.replace(evaluation, rules_fired=fired)
        unrelated_fired = _dimension(
            EvaluationDimensionRole.RULES_FIRED,
            "rule-fired",
            item_id="SYN-EVIDENCE-EVAL-OTHER-RULE-0001",
        )
        with self.assertRaises(DomainRecordError):
            dataclasses.replace(evaluation, rules_fired=unrelated_fired)
        component, version, _, _, _ = _DIMENSION_CONTRACTS[
            EvaluationDimensionRole.SUPPLIED_FACTS
        ]
        with self.assertRaises(DomainRecordError):
            EvaluationDimensionBinding(
                role=EvaluationDimensionRole.SUPPLIED_FACTS,
                schema=VersionBinding(component, version),
                items=[],  # type: ignore[arg-type]
                explicitly_empty=True,
            )

        result = _dimension(EvaluationDimensionRole.RESULT, "result")
        second_result = dataclasses.replace(
            result.items[0],
            item_id=EvidenceId("SYN-EVIDENCE-EVAL-RESULT-0002"),
        )
        with self.assertRaises(DomainRecordError):
            dataclasses.replace(
                result,
                items=(result.items[0], second_result),
            )

        empty_object = domain_hash(
            _DIMENSION_CONTRACTS[EvaluationDimensionRole.SUPPLIED_FACTS][4],
            canonical_json_bytes({}, expected_members=set()),
        )
        with self.assertRaises(DomainRecordError):
            EvaluationDimensionBinding(
                role=EvaluationDimensionRole.SUPPLIED_FACTS,
                schema=VersionBinding(component, version),
                items=(empty_object,),  # type: ignore[arg-type]
                explicitly_empty=False,
            )

        with self.assertRaises(TypeError):
            EvaluationExplanationItem.create_from_content(
                item_id=EvidenceId("SYN-EVIDENCE-EVAL-FACT-0002"),
                role=EvaluationDimensionRole.SUPPLIED_FACTS,
                content_value={"member": "synthetic"},
            )
        for content_value, expected_members in (
            ("scalar", {"member"}),
            ({}, set()),
            ({"unexpected": "synthetic"}, {"member"}),
        ):
            with self.subTest(content_shape=type(content_value).__name__):
                with self.assertRaises(DomainRecordError):
                    EvaluationExplanationItem.create_from_content(
                        item_id=EvidenceId("SYN-EVIDENCE-EVAL-FACT-0002"),
                        role=EvaluationDimensionRole.SUPPLIED_FACTS,
                        content_value=content_value,
                        expected_members=expected_members,
                    )
        empty_content = domain_hash(
            _DIMENSION_CONTRACTS[EvaluationDimensionRole.SUPPLIED_FACTS][4],
            canonical_json_bytes({}, expected_members=set()),
        )
        with self.assertRaises(DomainRecordError):
            EvaluationExplanationItem.create(
                item_id=EvidenceId("SYN-EVIDENCE-EVAL-FACT-0002"),
                role=EvaluationDimensionRole.SUPPLIED_FACTS,
                content=empty_content,
            )

    def test_each_hash_record_has_closed_null_missing_extra_and_version_coverage(self) -> None:
        for name, constructor, values, component, version in self._hash_record_cases():
            with self.subTest(name=name, case="accepted"):
                accepted = constructor(**values)
                canonical = accepted.canonical_bytes()  # type: ignore[attr-defined]
                self.assertIsInstance(canonical, bytes)
            for field_name in values:
                with self.subTest(name=name, case="null", field=field_name):
                    null_values = dict(values)
                    null_values[field_name] = None
                    with self.assertRaises(DomainRecordError):
                        constructor(**null_values)
                with self.subTest(name=name, case="missing", field=field_name):
                    missing_values = dict(values)
                    del missing_values[field_name]
                    with self.assertRaises(TypeError):
                        constructor(**missing_values)
            with self.subTest(name=name, case="extra"):
                extra_values = dict(values)
                extra_values["unexpected_member"] = None
                with self.assertRaises(TypeError):
                    constructor(**extra_values)
            for schema in (
                VersionBinding("wrong_role", version),
                VersionBinding(component, version.replace("/v1", "/v2")),
            ):
                with self.subTest(name=name, case="version", schema=schema):
                    wrong_version = dict(values)
                    wrong_version["schema"] = schema
                    with self.assertRaises(DomainRecordError):
                        constructor(**wrong_version)

    def test_record_token_boundaries_and_noncanonical_versions_fail_closed(self) -> None:
        self.assertEqual(len(VersionBinding("x" * 64, "shared-value/v1").component), 64)
        with self.assertRaises(DomainRecordError):
            VersionBinding("x" * 65, "shared-value/v1")
        for version in (
            "shared-value/v1/",
            "shared//value/v1",
            "shared..value/v1",
            "shared_-value/v1",
        ):
            with self.subTest(version=version):
                with self.assertRaises(DomainRecordError):
                    VersionBinding("value", version)

        source = self._source()
        with self.assertRaises(DomainRecordError):
            dataclasses.replace(source, source_kind="SYNTHETIC_PRIVATE_CANARY")
        with self.assertRaises(DomainRecordError):
            dataclasses.replace(source, source_kind="SYNTHETIC_ORDER_FIXTURE")
        with self.assertRaises(DomainRecordError):
            dataclasses.replace(
                source,
                object_namespace=SourceObjectNamespace.SYNTHETIC_PRODUCT,
            )

    def test_closed_enum_members_cannot_mutate_hash_bearing_records(self) -> None:
        source = self._source()
        before = source.canonical_bytes()
        for member in (
            ErrorCategory.VALIDATION,
            ErrorPathMember.PAYLOAD,
            EvaluationDimensionRole.SUPPLIED_FACTS,
            SourceKind.SYNTHETIC_ORDER_FIXTURE,
            StructuredErrorCode.VALUE_REJECTED,
        ):
            with self.subTest(enum_type=type(member).__name__):
                with self.assertRaises(AttributeError):
                    member._value_ = "MUTATED"  # type: ignore[misc]
                with self.assertRaises(AttributeError):
                    member.extra = []  # type: ignore[attr-defined]
                with self.assertRaises(TypeError):
                    member.__dict__["_value_"] = "MUTATED"
                raw_state = object.__getattribute__(member, "__dict__")
                original_value = raw_state["_value_"]
                try:
                    raw_state["_value_"] = "MUTATED"
                    self.assertEqual(member.value, str.__str__(member))
                    self.assertEqual(source.canonical_bytes(), before)
                finally:
                    raw_state["_value_"] = original_value
        self.assertEqual(source.canonical_bytes(), before)

    def test_closed_collections_reject_mutable_unsorted_and_duplicate_input(self) -> None:
        first = self._source("0001")
        second = self._source("0002")
        schema = VersionBinding("snapshot", "shared-snapshot/v1")
        payload = _role_binding(SnapshotEnvelope.PAYLOAD_DOMAIN)
        completeness_proof = self._proof(first)
        with self.assertRaises(DomainRecordError):
            SnapshotEnvelope(
                snapshot_id=SnapshotId("SYN-SNAPSHOT-SHARED-0001"),
                run_id=RunId("SYN-RUN-SHARED-0001"),
                schema=schema,
                payload=payload,
                completeness_proof=completeness_proof,
                source_refs=[first],  # type: ignore[arg-type]
            )
        with self.assertRaises(DomainRecordError):
            SnapshotEnvelope(
                snapshot_id=SnapshotId("SYN-SNAPSHOT-SHARED-0001"),
                run_id=RunId("SYN-RUN-SHARED-0001"),
                schema=schema,
                payload=payload,
                completeness_proof=completeness_proof,
                source_refs=(second, first),
            )
        with self.assertRaises(DomainRecordError):
            ReasonSet((self.registries.reason_ref("RC-001"),) * 2)

    def test_envelope_schema_roles_and_versions_are_exact(self) -> None:
        source = self._source()
        payload = _role_binding(SnapshotEnvelope.PAYLOAD_DOMAIN)
        completeness_proof = self._proof(source)
        wrong_bindings = (
            VersionBinding("rule_pack", "shared-snapshot/v1"),
            VersionBinding("snapshot", "shared-snapshot/v2"),
        )
        for binding in wrong_bindings:
            with self.subTest(binding=binding):
                with self.assertRaises(DomainRecordError):
                    SnapshotEnvelope(
                        snapshot_id=SnapshotId("SYN-SNAPSHOT-SHARED-0001"),
                        run_id=RunId("SYN-RUN-SHARED-0001"),
                        schema=binding,
                        payload=payload,
                        completeness_proof=completeness_proof,
                        source_refs=(source,),
                    )
        with self.assertRaises(DomainRecordError):
            EvaluationEnvelope(
                evaluation_id=EvaluationId("SYN-EVALUATION-SHARED-0001"),
                snapshot_id=SnapshotId("SYN-SNAPSHOT-SHARED-0001"),
                run_id=RunId("SYN-RUN-SHARED-0001"),
                schema=VersionBinding("rule_pack", "shared-rule-pack/v1"),
                rule_pack=VersionBinding("evaluation", "shared-evaluation/v1"),
                supplied_facts=_dimension(
                    EvaluationDimensionRole.SUPPLIED_FACTS,
                    "supplied-facts",
                ),
                rules_evaluated=_dimension(
                    EvaluationDimensionRole.RULES_EVALUATED,
                    "rules-evaluated",
                ),
                rules_fired=_dimension(EvaluationDimensionRole.RULES_FIRED, None),
                reasons=ReasonSet(),
                result=_dimension(EvaluationDimensionRole.RESULT, "result"),
                human_review=HumanReviewRequirement(False, ReasonSet()),
                persistence_effects=_dimension(
                    EvaluationDimensionRole.PERSISTENCE_EFFECTS,
                    None,
                ),
            )

    def test_human_review_is_typed_without_encoding_a_business_rule(self) -> None:
        empty = ReasonSet()
        reason = ReasonSet((self.registries.reason_ref("RC-001"),))
        self.assertFalse(HumanReviewRequirement(False, empty).required)
        self.assertFalse(HumanReviewRequirement(False, reason).required)
        self.assertTrue(HumanReviewRequirement(True, empty).required)
        with self.assertRaises(DomainRecordError):
            HumanReviewRequirement(1, empty)  # type: ignore[arg-type]

    def test_structured_errors_and_diagnostics_do_not_retain_rejected_material(self) -> None:
        marker = "fictional" + "@example.test"
        error = StructuredDomainError(
            StructuredErrorCode.VALUE_REJECTED,
            ErrorCategory.PRIVACY,
            (ErrorPathMember.PAYLOAD, 0),
        )
        source = self._source()
        prohibited_content = _role_binding(SourceRef.CONTENT_DOMAIN, marker)
        with self.assertRaises(DomainRecordError):
            dataclasses.replace(source, content=prohibited_content)
        self.assertNotIn(marker, repr(source.content))
        self.assertNotIn(marker, repr(source))
        self.assertNotIn(marker, repr(error))
        self.assertEqual(error.to_dict()["path"], ["payload", 0])
        with self.assertRaises(DomainRecordError) as caught:
            StructuredDomainError(  # type: ignore[arg-type]
                marker,
                path=(ErrorPathMember.PAYLOAD,),
            )
        self.assertNotIn(marker, str(caught.exception))
        token_marker = "synthetic" + "privatecanary"
        with self.assertRaises(DomainRecordError):
            StructuredDomainError(
                StructuredErrorCode.VALUE_REJECTED,
                path=(token_marker,),  # type: ignore[arg-type]
            )


if __name__ == "__main__":
    unittest.main()
