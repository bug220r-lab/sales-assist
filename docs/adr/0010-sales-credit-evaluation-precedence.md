# ADR 0010: Sales Credit evaluation precedence and dimensions

- Status: accepted for Milestone 2
- Scope: pure system classification only

## Decision

The evaluator follows the binding order: snapshot validity, candidate order timing,
cancellation/replacement, material change and placed value, raw order-level rep, required evidence,
then ambiguity routing. `INVALID` stops every automatic favorable conclusion. `PARTIAL` blocks only
dimensions whose required facts are incomplete. Candidate timing is derived against the attached
interaction records: pre-interaction and after-D+14 orders cannot receive a favorable result, and
same-day imprecision uses `TIMING_UNCERTAIN_HUMAN_REVIEW`.

Attribution and order value are independent result dimensions. Target-rep attribution remains a
known fact when placed value is unavailable or material change requires review, but the top-level
workflow is `ORDER_CHANGED_HUMAN_REVIEW`. A line-level rep never substitutes for the raw order-level
rep. Current total never substitutes for original placed value, and the evaluator never estimates.

For the M2 Sales Credit source-of-truth policy, the source-provided order-header placed total is
authoritative for the placed-value decision. A line's exact `line_value` is the source-provided
extended line observation. The M2 contract contains no unit-price field, so it never treats that
value as a unit price, multiplies it by quantity, or reconstructs the order header by summing lines.
Shipping, discounts, tax, partial extraction, and other header/line scope differences therefore do
not create a hidden equality assumption. Missing header placed value still takes the governed
unavailable/human-review route. Available-to-ship, opportunity-potential, and realized-intervention
value policies remain outside M2 and must be defined by their owning later rule packs.

Cancellation contributes zero active value and opens the governed replacement window, but it does
not suppress a mandatory placed-value or material-change review. A
replacement needs customer continuity and exact canonical ES or MFG/OE product continuity.
Non-exact substitute continuity routes to human review; one exact match establishes relevance but
does not decide credit scope.

Evidence establishes attribution only when pre-order timing, target-rep participation, and
two-way interaction or connected-call facts are independently sufficient. Inbound-only,
outbound-only, post-order, same-day uncertain, contradictory, and unknown cases use their closed
review routes. No evidence branch creates a manager outcome.

The configured known-other-representative vocabulary is a fixed part of the versioned rule pack,
not a caller-selectable set. Every evaluation contains closed supplied facts, validations,
rules evaluated/fired, independent
dimensions, workflow state, Sales Credit reasons, human-review flag, and rule-pack version.

## Consequences

An automatic favorable attribution can coexist with a value-review workflow without information
loss. Manager decisions remain later explicit inputs and never rewrite the system evaluation.
