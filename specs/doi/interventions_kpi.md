
# DOI Interventions, Resulting Orders, and KPI

## Opportunity versus intervention

An opportunity is a deterministic candidate from an evaluation. It does not prove action.

An intervention is created/reused only after an exact verified action occurrence. Action
verification may be system-grounded or authorized human-grounded.

## Value

Potential value, realized value, correction, and reversal are separate histories.

- Estimated/rounded/ranged human amounts are rejected.
- Exact system evidence controls current value when it conflicts with human evidence while detail
  is retained.
- Unverified value contributes zero realized money.
- Partial and full reversals update exact net value without rewriting history.
- Duplicate action/evidence fingerprints are suppressed.

## Resulting orders

Split credit may require an exact resulting-order relationship and exact mapping components.
Automatic link requires deterministic evidence. Human-confirmed link requires structured
evidence. Ambiguous/not-found searches do not create an exact link or realized split credit.

Rep verification is scoped:

- split: resulting-order-level target rep;
- substitution: replacement-line-level target rep;
- parent-order rep cannot substitute for line-level proof.

## KPI

A retained contribution is exactly once per verified intervention and is segmented by currency.
Action date must be exact and business-calendar bound. Mixed currencies are never combined.

At case purge, the current retained contribution is atomically transferred to a nonidentifying
aggregate bucket before case deletion. Any reconciliation mismatch rolls back both operations.
No case/order/link hash or drill-through identity survives in the aggregate.
