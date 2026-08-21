from __future__ import annotations

import dataclasses
import itertools
import unittest
from decimal import Decimal

from synthetic_sales_assist.doi.extraction import (
    CompositeLineContinuityIdentity,
    DOIExtractionError,
    DOIExtractionSurface,
    DOIOrderObservedFacts,
    ExtractionStatus,
    RequiredSectionObservation,
    build_dedupe_finding,
    build_line_snapshot,
    build_wwc_finding,
    extract_order_snapshot,
    extraction_hash_fixture_records,
)
from synthetic_sales_assist.doi.identities import (
    DoiOrderId,
    DoiRunId,
    DoiSnapshotId,
    ExtractionAttemptId,
    LineSnapshotId,
)
from synthetic_sales_assist.doi.models import (
    AttentionCondition,
    ContinuityProofType,
    DedupeState,
    DropShipState,
    GeographyClass,
    LineActivity,
    LineAvailability,
    LineContinuityState,
    OrderState,
    PaymentCondition,
    QuantityAvailability,
    RepRelation,
    SourcePresence,
    WWCAuthorRelation,
    WWCTimingState,
    known_fact,
    not_applicable_fact,
    unknown_fact,
)
from synthetic_sales_assist.domain.identities import (
    EvidenceId,
    InteractionId,
    OrderId,
    RepId,
    RunId,
    SkuId,
    SnapshotId,
)
from synthetic_sales_assist.domain.numeric import (
    CURRENCY_REGISTRY_VERSION,
    Money,
    NonNegativeCount,
    PositiveOrdinal,
    Quantity,
)
from synthetic_sales_assist.domain.observed import FindingPresenceV2
from synthetic_sales_assist.domain.records import (
    SourceKind,
    SourceObjectNamespace,
    SourceRef,
    WholeOrderCompletenessProof,
)
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp


def _money(value: str = "10.00") -> Money:
    return Money(Decimal(value), "USD", CURRENCY_REGISTRY_VERSION, 2)


def _source(order_id: str = "SYN-ORDER-1") -> SourceRef:
    return SourceRef.create(
        source_ref_id=EvidenceId("SYN-EVIDENCE-DOI-ORDER-SOURCE-0001"),
        source_kind=SourceKind.SYNTHETIC_ORDER_FIXTURE,
        object_namespace=SourceObjectNamespace.SYNTHETIC_ORDER,
        object_id=OrderId(order_id),
    )


def _wwc(source: SourceRef):
    na = not_applicable_fact()
    return build_wwc_finding(
        finding_id=EvidenceId("SYN-EVIDENCE-DOI-WWC-0001"),
        presence=FindingPresenceV2.NOT_PRESENT,
        author_relation=na,
        timing_state=na,
        marker=na,
        observed_at=na,
        source=source,
    )


def _dedupe(source: SourceRef):
    return build_dedupe_finding(
        finding_id=EvidenceId("SYN-EVIDENCE-DOI-DEDUPE-0001"),
        presence=FindingPresenceV2.NOT_PRESENT,
        observed_at=None,
        state=DedupeState.NOT_PRESENT,
        source=source,
    )


def _line(
    ordinal: int = 1,
    *,
    source: SourceRef | None = None,
    availability=None,
    stable_source_line_id=None,
    composite: CompositeLineContinuityIdentity | None = None,
):
    bound_source = source or _source()
    return build_line_snapshot(
        line_snapshot_id=LineSnapshotId(
            EvidenceId(f"SYN-EVIDENCE-DOI-LINE-{ordinal:04d}")
        ),
        stable_source_line_id=(
            stable_source_line_id
            if stable_source_line_id is not None
            else known_fact(EvidenceId(f"SYN-EVIDENCE-DOI-SOURCE-LINE-{ordinal:04d}"))
        ),
        relevant_merchandise=True,
        activity=known_fact(LineActivity.ACTIVE),
        drop_ship_state=known_fact(DropShipState.NON_DS),
        availability=(
            availability
            if availability is not None
            else known_fact(LineAvailability.IN_STOCK)
        ),
        eta=known_fact(CanonicalTimestamp("2026-08-11T12:00:00Z")),
        ordered_quantity=known_fact(Quantity(2)),
        active_quantity=known_fact(Quantity(2)),
        canceled_quantity=known_fact(Quantity(0)),
        explicitly_available_quantity=known_fact(Quantity(2)),
        quantity_availability=known_fact(QuantityAvailability.FULL),
        es_number=known_fact(SkuId("SYN-SKU-ES-1")),
        mfg_number=known_fact(SkuId("SYN-SKU-MFG-1")),
        unit_value=known_fact(_money()),
        active_line_value=known_fact(_money("20.00")),
        line_sales_rep=known_fact(RepId("SYN-REP-TARGET-0001")),
        source=bound_source,
        composite_continuity=composite,
    )


def _facts(source: SourceRef) -> DOIOrderObservedFacts:
    return DOIOrderObservedFacts(
        order_state=known_fact(OrderState.ACTIVE),
        current_rep_value=known_fact(RepId("SYN-REP-TARGET-0001")),
        current_rep_relation=known_fact(RepRelation.TARGET_REP_OWNED),
        geography_class=known_fact(GeographyClass.DOMESTIC_STANDARD),
        payment_condition=known_fact(PaymentCondition.NONE_OBSERVED),
        order_total=known_fact(_money("20.00")),
        wwc_finding=_wwc(source),
        dedupe_finding=_dedupe(source),
        source_presence=SourcePresence.PRESENT,
    )


def _surface(
    *,
    lines=None,
    source: SourceRef | None = None,
    observed_order_id: DoiOrderId | None = None,
    sections=None,
    facts: DOIOrderObservedFacts | None = None,
    declared_count: object | None = None,
    order_time: object = "2026-08-10T12:00:00Z",
    proof_time: object = "2026-08-10T08:00:00-04:00",
    source_changed: bool = False,
    empty_universe_proved: bool | None = None,
) -> DOIExtractionSurface:
    bound_source = source or _source()
    bound_lines = (_line(source=bound_source),) if lines is None else lines
    bound_sections = (
        tuple(
            RequiredSectionObservation.complete(section, bound_source)
            for section in WholeOrderCompletenessProof.REQUIRED_SECTIONS
        )
        if sections is None
        else sections
    )
    return DOIExtractionSurface(
        attempt_id=ExtractionAttemptId(
            InteractionId("SYN-INTERACTION-DOI-EXTRACT-0001")
        ),
        run_id=DoiRunId(RunId("SYN-RUN-DOI-EXTRACT-0001")),
        snapshot_id=DoiSnapshotId(SnapshotId("SYN-SNAPSHOT-DOI-0001")),
        requested_order_id=DoiOrderId(OrderId("SYN-ORDER-1")),
        observed_order_id=(
            DoiOrderId(OrderId("SYN-ORDER-1"))
            if observed_order_id is None
            else observed_order_id
        ),
        started_at=CanonicalTimestamp("2026-08-10T12:00:00Z"),
        completed_at=CanonicalTimestamp("2026-08-10T12:00:01Z"),
        order_source_observed_at=order_time,
        proof_source_observed_at=proof_time,
        sections=bound_sections,
        declared_relevant_line_count=(
            NonNegativeCount(len(bound_lines))
            if declared_count is None
            else declared_count
        ),
        lines=bound_lines,
        order_facts=_facts(bound_source) if facts is None else facts,
        source_changed=source_changed,
        empty_universe_proved=(
            len(bound_lines) == 0
            if empty_universe_proved is None
            else empty_universe_proved
        ),
    )


class DOIExtractionTests(unittest.TestCase):
    def assert_failure(self, surface: DOIExtractionSurface, specific_reason: str) -> None:
        result = extract_order_snapshot(surface)
        self.assertIs(result.attempt.status, ExtractionStatus.FAILED)
        self.assertIsNone(result.snapshot)
        self.assertEqual(
            {reason.code for reason in result.attempt.reasons.reasons},
            {specific_reason, "RC-014", "RC-015"},
        )
        self.assertEqual(
            result.attention_conditions,
            (AttentionCondition.RECHECK_REQUIRED,),
        )

    def test_complete_snapshot_binds_canonical_source_time_and_manifest(self) -> None:
        result = extract_order_snapshot(_surface())
        self.assertIs(result.attempt.status, ExtractionStatus.SUCCEEDED)
        self.assertEqual(result.attempt.reasons.reasons, ())
        self.assertEqual(result.attention_conditions, ())
        assert result.snapshot is not None
        self.assertEqual(result.snapshot.source_observed_at.value, "2026-08-10T12:00:00Z")
        self.assertEqual(
            result.snapshot.completeness_proof.proof_source_observed_at.value,
            "2026-08-10T12:00:00Z",
        )
        self.assertEqual(len(result.snapshot.lines), 1)
        self.assertEqual(
            result.snapshot.completeness_proof.manifest_binding.domain,
            "shared-snapshot-line-manifest/v1",
        )

    def test_large_and_explicitly_empty_complete_orders_succeed(self) -> None:
        source = _source()
        large = tuple(_line(index, source=source) for index in range(1, 101))
        result = extract_order_snapshot(_surface(lines=large, source=source))
        assert result.snapshot is not None
        self.assertEqual(len(result.snapshot.lines), 100)
        empty = extract_order_snapshot(_surface(lines=(), source=source))
        assert empty.snapshot is not None
        self.assertTrue(empty.snapshot.completeness_proof.empty_universe_proved)

    def test_identity_missing_or_mismatch_is_rc011(self) -> None:
        mismatch = _surface(observed_order_id=DoiOrderId(OrderId("SYN-ORDER-2")))
        self.assert_failure(mismatch, "RC-011")
        self.assert_failure(dataclasses.replace(mismatch, observed_order_id=None), "RC-011")

    def test_missing_or_unreadable_required_input_is_rc013_not_unknown(self) -> None:
        source = _source()
        sections = tuple(
            RequiredSectionObservation.complete(section, source)
            for section in WholeOrderCompletenessProof.REQUIRED_SECTIONS[:-1]
        )
        self.assert_failure(_surface(source=source, sections=sections), "RC-013")
        full_sections = tuple(
            RequiredSectionObservation.complete(section, source)
            for section in WholeOrderCompletenessProof.REQUIRED_SECTIONS
        )
        unreadable = dataclasses.replace(full_sections[1], readable=False)
        self.assert_failure(
            _surface(source=source, sections=(full_sections[0], unreadable, *full_sections[2:])),
            "RC-013",
        )
        self.assert_failure(dataclasses.replace(_surface(), lines=None), "RC-013")
        self.assert_failure(dataclasses.replace(_surface(), order_facts=None), "RC-013")

    def test_whole_order_proof_failures_are_rc012(self) -> None:
        source = _source()
        complete_sections = tuple(
            RequiredSectionObservation.complete(section, source)
            for section in WholeOrderCompletenessProof.REQUIRED_SECTIONS
        )
        cases = (
            _surface(declared_count=NonNegativeCount(2)),
            _surface(lines=(_line(source=source), _line(source=source)), source=source),
            _surface(source_changed=True),
            _surface(order_time="2026-08-10T12:00:00Z", proof_time="2026-08-10T12:00:01Z"),
            _surface(
                source=source,
                sections=(
                    dataclasses.replace(
                        complete_sections[0],
                        paginated_regions_exhausted=False,
                    ),
                    *complete_sections[1:],
                ),
            ),
            _surface(lines=(), empty_universe_proved=False),
        )
        for surface in cases:
            with self.subTest(surface=repr(surface)):
                self.assert_failure(surface, "RC-012")

    def test_unnormalizable_required_source_time_is_extraction_failure(self) -> None:
        self.assert_failure(_surface(order_time="2026-08-10 12:00:00"), "RC-013")
        self.assert_failure(_surface(proof_time="2026-08-10T12:00:00"), "RC-013")

    def test_field_unknown_survives_success_while_missing_line_fails(self) -> None:
        source = _source()
        unknown_line = _line(
            source=source,
            availability=unknown_fact("RC-016", raw_hint="UNRECOGNIZED_AVAILABILITY_TOKEN"),
        )
        result = extract_order_snapshot(_surface(lines=(unknown_line,), source=source))
        self.assertIs(result.attempt.status, ExtractionStatus.SUCCEEDED)
        assert result.snapshot is not None
        self.assertEqual(
            result.snapshot.lines[0].availability.to_mapping()["reason_code"],
            "RC-016",
        )
        self.assert_failure(dataclasses.replace(_surface(), lines=None), "RC-013")

    def test_stable_and_closed_composite_line_continuity_and_no_description_guess(self) -> None:
        stable = _line()
        self.assertIs(
            stable.continuity.proof_type,
            ContinuityProofType.STABLE_SOURCE_LINE_ID,
        )
        source = _source()
        composite = CompositeLineContinuityIdentity(
            order_id=OrderId("SYN-ORDER-1"),
            source_section="LINE_ITEMS",
            source_ordinal=PositiveOrdinal(1),
            es_number=SkuId("SYN-SKU-ES-1"),
            mfg_number=SkuId("SYN-SKU-MFG-1"),
            ordered_quantity=Quantity(2),
        )
        composite_line = _line(
            source=source,
            stable_source_line_id=unknown_fact("RC-124"),
            composite=composite,
        )
        self.assertIs(
            composite_line.continuity.proof_type,
            ContinuityProofType.CLOSED_COMPOSITE,
        )
        unverified = _line(
            source=source,
            stable_source_line_id=unknown_fact("RC-124"),
        )
        self.assertIs(unverified.continuity.state, LineContinuityState.UNVERIFIED)
        with self.assertRaises(TypeError):
            CompositeLineContinuityIdentity(  # type: ignore[call-arg]
                order_id=OrderId("SYN-ORDER-1"),
                source_section="LINE_ITEMS",
                source_ordinal=PositiveOrdinal(1),
                es_number=SkuId("SYN-SKU-ES-1"),
                mfg_number=SkuId("SYN-SKU-MFG-1"),
                ordered_quantity=Quantity(2),
                description="looks similar",
            )

    def test_composite_continuity_must_equal_observed_line_facts(self) -> None:
        composite = CompositeLineContinuityIdentity(
            order_id=OrderId("SYN-ORDER-1"),
            source_section="LINE_ITEMS",
            source_ordinal=PositiveOrdinal(1),
            es_number=SkuId("SYN-SKU-ES-999"),
            mfg_number=SkuId("SYN-SKU-MFG-1"),
            ordered_quantity=Quantity(2),
        )
        with self.assertRaises(DOIExtractionError):
            _line(
                stable_source_line_id=unknown_fact("RC-124"),
                composite=composite,
            )

    def test_dedupe_present_requires_constructible_canonical_observed_time(self) -> None:
        source = _source()
        with self.assertRaises(DOIExtractionError) as caught:
            build_dedupe_finding(
                finding_id=EvidenceId("SYN-EVIDENCE-DOI-DEDUPE-0002"),
                presence=FindingPresenceV2.PRESENT,
                observed_at="not-a-time",
                state=DedupeState.CANDIDATE,
                source=source,
            )
        self.assertEqual(caught.exception.code, "dedupe_present_timestamp")
        accepted = build_dedupe_finding(
            finding_id=EvidenceId("SYN-EVIDENCE-DOI-DEDUPE-0002"),
            presence=FindingPresenceV2.PRESENT,
            observed_at="2026-08-10T08:00:00-04:00",
            state=DedupeState.SOURCE_PRESENT,
            source=source,
        )
        assert accepted.observed_at is not None
        self.assertEqual(accepted.observed_at.value, "2026-08-10T12:00:00Z")
        with self.assertRaises(DOIExtractionError):
            build_dedupe_finding(
                finding_id=EvidenceId("SYN-EVIDENCE-DOI-DEDUPE-0003"),
                presence=FindingPresenceV2.PRESENT,
                observed_at="2026-08-10T12:00:00Z",
                state=DedupeState.CONFIRMED,
                source=source,
            )

    def test_all_wwc_present_known_unknown_nested_partitions_are_constructible(self) -> None:
        source = _source()
        known_unknown_pairs = (
            (
                known_fact(WWCAuthorRelation.TARGET_REP),
                unknown_fact("RC-055"),
            ),
            (known_fact(WWCTimingState.ACTIVE), unknown_fact("RC-056")),
            (known_fact("WWC_MARKER"), unknown_fact("RC-122")),
            (
                known_fact(CanonicalTimestamp("2026-08-10T12:00:00Z")),
                unknown_fact("RC-056"),
            ),
        )
        findings = []
        for index, partition in enumerate(itertools.product((0, 1), repeat=4), start=1):
            values = tuple(
                known_unknown_pairs[field][choice]
                for field, choice in enumerate(partition)
            )
            findings.append(
                build_wwc_finding(
                    finding_id=EvidenceId(f"SYN-EVIDENCE-DOI-WWC-{index:04d}"),
                    presence=FindingPresenceV2.PRESENT,
                    author_relation=values[0],
                    timing_state=values[1],
                    marker=values[2],
                    observed_at=values[3],
                    source=source,
                )
            )
        self.assertEqual(len(findings), 16)
        with self.assertRaises(DOIExtractionError):
            build_wwc_finding(
                finding_id=EvidenceId("SYN-EVIDENCE-DOI-WWC-ILLEGAL"),
                presence=FindingPresenceV2.PRESENT,
                author_relation=not_applicable_fact(),
                timing_state=known_fact(WWCTimingState.ACTIVE),
                marker=known_fact("WWC_MARKER"),
                observed_at=known_fact(CanonicalTimestamp("2026-08-10T12:00:00Z")),
                source=source,
            )

    def test_extraction_hash_known_answers_are_fixed(self) -> None:
        actual: dict[str, tuple[str, str]] = {}
        for name, domain, canonical, digest in extraction_hash_fixture_records():
            self.assertTrue(canonical.startswith(b"{"))
            actual[name] = (domain, digest)
        self.assertEqual(
            actual,
            {
                "CompositeLineContinuityIdentity": (
                    "doi-line-continuity-composite/v1",
                    "fe6c25ba3e1e497ff90c5f52682554fb4fb7a9486c7275f708d866443cd8cba1",
                ),
                "DOIExtractionAttempt": (
                    "doi-extraction-attempt/v1",
                    "d3b0e825fc98d6f9161f625f51e183ad5ae5896ec959e65dcbe305a91f1dd066",
                ),
            },
        )

    def test_adapter_errors_do_not_chain_rejected_source_exceptions(self) -> None:
        source = _source()
        with self.assertRaises(DOIExtractionError) as dedupe_caught:
            build_dedupe_finding(
                finding_id=EvidenceId("SYN-EVIDENCE-DOI-DEDUPE-ERROR"),
                presence=FindingPresenceV2.PRESENT,
                observed_at="SYNTHETIC_PRIVATE_CANARY",
                state=DedupeState.CANDIDATE,
                source=source,
            )
        self.assertIsNone(dedupe_caught.exception.__cause__)
        self.assertIsNone(dedupe_caught.exception.__context__)
        self.assertNotIn("CANARY", str(dedupe_caught.exception))

        with self.assertRaises(DOIExtractionError) as wwc_caught:
            build_wwc_finding(
                finding_id=EvidenceId("SYN-EVIDENCE-DOI-WWC-ERROR"),
                presence=FindingPresenceV2.PRESENT,
                author_relation=known_fact(WWCAuthorRelation.TARGET_REP),
                timing_state=known_fact(WWCTimingState.ACTIVE),
                marker=not_applicable_fact(),
                observed_at=known_fact(CanonicalTimestamp("2026-08-10T12:00:00Z")),
                source=source,
            )
        self.assertIsNone(wwc_caught.exception.__cause__)
        self.assertIsNone(wwc_caught.exception.__context__)


if __name__ == "__main__":
    unittest.main()
