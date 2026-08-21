from __future__ import annotations

import dataclasses
import unittest

from synthetic_sales_assist.doi.identities import (
    AcceptedCommandId,
    CommandReceiptId,
    DOIIdentityError,
    DoiOrderId,
    DoiRunId,
    DoiSnapshotId,
    ExtractionAttemptId,
    ExtractionOccurrenceId,
    LineSnapshotId,
    RunInvocationId,
    RunWorkItemId,
    SourceBatchId,
    SourceIdentityId,
    SourceImportAttemptId,
    SourceRowRefId,
)
from synthetic_sales_assist.domain.identities import (
    DomainIdentityError,
    EvidenceId,
    InteractionId,
    OrderId,
    RunId,
    SnapshotId,
)


class DOIIdentityTests(unittest.TestCase):
    def test_every_semantic_identity_uses_an_existing_reserved_namespace(self) -> None:
        cases = (
            (SourceIdentityId, EvidenceId("SYN-EVIDENCE-DOI-SOURCE-0001")),
            (SourceBatchId, EvidenceId("SYN-EVIDENCE-DOI-BATCH-0001")),
            (SourceRowRefId, EvidenceId("SYN-EVIDENCE-DOI-ROW-0001")),
            (CommandReceiptId, EvidenceId("SYN-EVIDENCE-DOI-RECEIPT-0001")),
            (LineSnapshotId, EvidenceId("SYN-EVIDENCE-DOI-LINE-0001")),
            (SourceImportAttemptId, InteractionId("SYN-INTERACTION-DOI-ATTEMPT-0001")),
            (RunInvocationId, InteractionId("SYN-INTERACTION-DOI-RUN-0001")),
            (RunWorkItemId, InteractionId("SYN-INTERACTION-DOI-WORK-0001")),
            (ExtractionAttemptId, InteractionId("SYN-INTERACTION-DOI-EXTRACT-0001")),
            (
                ExtractionOccurrenceId,
                InteractionId("SYN-INTERACTION-DOI-OCCURRENCE-0001"),
            ),
            (AcceptedCommandId, InteractionId("SYN-INTERACTION-DOI-COMMAND-0001")),
            (DoiOrderId, OrderId("SYN-ORDER-1")),
            (DoiRunId, RunId("SYN-RUN-DOI-0001")),
            (DoiSnapshotId, SnapshotId("SYN-SNAPSHOT-DOI-0001")),
        )
        for semantic_type, primitive in cases:
            with self.subTest(semantic_type=semantic_type.__name__):
                value = semantic_type(primitive)
                self.assertEqual(value.to_json_value(), primitive.value)
                self.assertNotIn(primitive.value, repr(value))
                with self.assertRaises(dataclasses.FrozenInstanceError):
                    value.value = primitive  # type: ignore[misc]

    def test_semantic_namespace_mismatch_fails_without_reflecting_value(self) -> None:
        marker = "SYN-ORDER-PRIVATE-CANARY"
        with self.assertRaises(DOIIdentityError) as caught:
            SourceBatchId(OrderId(marker))  # type: ignore[arg-type]
        self.assertEqual(caught.exception.code, "semantic_identity_namespace")
        self.assertNotIn(marker, str(caught.exception))

    def test_nonreserved_primitives_fail_before_semantic_construction(self) -> None:
        marker = "ordinary-identifier"
        with self.assertRaises(DomainIdentityError) as caught:
            EvidenceId(marker)
        self.assertNotIn(marker, str(caught.exception))


if __name__ == "__main__":
    unittest.main()
