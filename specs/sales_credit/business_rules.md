
# Sales Credit Business Rules

## Review windows

- The review window begins on the interaction local date and includes fourteen full calendar
  days after that date.
- Only orders placed on or after the interaction can qualify.
- Same-day evidence without reliable time ordering is human review; date-only evidence never
  proves pre-order contact.
- A no-order interaction may be rechecked automatically at most once per local calendar day
  while its window remains active.
- Explicit force recheck bypasses the throttle only for selected cases and is logged.

## Discovery and matching

- Search every valid synthetic email and phone identifier.
- When both exist, both searches are mandatory.
- Combine complete native result sets and deduplicate by Order Number.
- Evaluate every candidate independently; finding one order never ends discovery.
- A different displayed fictional customer name does not invalidate a match when a searched
  identifier establishes continuity.
- Incomplete enumeration prevents a no-order conclusion.

## Decision precedence

1. Validate the snapshot. INVALID stops automatic processing; PARTIAL blocks only dependent
   decisions.
2. Capture every matching order.
3. Evaluate cancellation and replacement-window behavior.
4. Evaluate material commercial changes and placed-order value.
5. Classify attribution from the raw order-level rep value.
6. When evidence is needed, classify exact pre-order contact evidence and timing.
7. Route every ambiguity to a named human-review state.

## Rep classification

| Raw value | Result | Effect |
|---|---|---|
| `target_rep` or `target_rep_web` | `CREDIT_CONFIRMED_TARGET_REP` | No further attribution investigation; value review may still apply |
| `unassigned_web` | `EVIDENCE_NEEDED` | Evaluate pre-order evidence |
| Any other known rep | `OTHER_REP_HUMAN_REVIEW` | Preserve raw value and evidence |
| Missing or unrecognized | `MANUAL_REVIEW_REQUIRED` | Never remap silently |

## Contact evidence

| Evidence | Classification |
|---|---|
| Verified two-way pre-order interaction or connected pre-order call | `VERIFIED_PREORDER_EVIDENCE` |
| Inbound-only contact with no target-rep response | `INBOUND_EVIDENCE_HUMAN_REVIEW` |
| Outbound-only contact with no customer response | `OUTBOUND_EVIDENCE_HUMAN_REVIEW` |
| Missed or unanswered inbound call before purchase | `INBOUND_EVIDENCE_HUMAN_REVIEW` |
| Post-order contact only | Does not establish attribution |
| Same-day evidence with uncertain ordering | `TIMING_UNCERTAIN_HUMAN_REVIEW` |

## Cancellation and replacement

- A canceled matching order remains in the audit trail but contributes no active Sales Credit
  value.
- Cancellation opens a replacement window through fourteen full calendar days after the
  cancellation date, even when that extends beyond the interaction window.
- A replacement requires customer continuity plus product continuity.
- Exact canonical ES or exact canonical MFG/OE establishes deterministic product continuity.
- Similar, equivalent, superseding, bundled, or substitute products require human review.
- One exact product match makes the replacement relevant, but the human outcome determines
  applicable credit scope.
- No relevant product continuity means the new order is not a continuation.

## Placed order value and material changes

Use the order value when originally placed. Current total is an observation, not a substitute.

Material changes include product additions/removals, quantity changes, substitutions, partial
cancellations, shipping changes, discounts, price adjustments, refunds, and returns that alter
commercial value.

Routine warehouse, inventory, shipment-tracking, and administrative events are not material
solely because lifecycle status changed.

Material change or inability to establish placed value routes to
`ORDER_CHANGED_HUMAN_REVIEW`. Never estimate the placed value.

## Case identity

One Order Number produces one logical active case. All qualifying interactions and snapshots
attach to that case. Totals, human outcomes, and audit records are not duplicated.

## Human outcome

Human outcomes are:

- APPROVED
- DENIED
- PARTIAL
- OTHER_REP
- NOT_PURSUED

The outcome is recorded separately from the system classification. The engine never predicts or
exercises managerial authority.
