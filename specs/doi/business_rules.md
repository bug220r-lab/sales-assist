
# DOI Business Rules

## Top-level precedence

For a complete valid evaluation:

```text
EXCLUDED > OPPORTUNITY > MANUAL_REVIEW > MONITOR
```

Hard verified closure facts take precedence. Known safe opportunities are preserved when an
unrelated field is UNKNOWN. A fully blocking uncertainty routes to manual review.

## Extraction boundary

- A requested synthetic order identity must be exact.
- The complete relevant line universe must be proved.
- Missing/unreadable required data is extraction failure, not UNKNOWN.
- UNKNOWN is legal only for a successfully observed individual field.
- Failed/incomplete extraction creates no snapshot or evaluation and sets recheck required.

## Direct ship

- At least one relevant active merchandise line and every such line explicitly direct ship:
  `DOI_EXCLUDED` with FULL_DS; this evaluation alone does not start purge.
- Mixed direct-ship and non-direct-ship active lines:
  `DOI_OPPORTUNITY`, emit MIXED_DS and DS_SEPARATION_REQUIRED, and continue non-direct-ship
  analysis.
- Unknown direct-ship state blocks only conclusions depending on that line.

## Fulfillment split

A split candidate exists when at least one active non-direct-ship line is explicitly
IN_STOCK/FULL and at least one active non-direct-ship line is DELAYED. There is no minimum
value or delay duration.

Unknown ETA does not suppress a split that is independently proved from availability, direct-ship
state, quantities, and scope. It makes only ETA-dependent ranking unavailable.

## Partial quantity

When exact `0 < available_quantity < active_quantity`, emit partial-quantity handling and
calculate exact partial value when possible. Never automatically recommend or perform a partial
split.

## Payment

- Payment as the sole blocker and no product opportunity: DOI_EXCLUDED.
- Payment coexisting with a product opportunity: preserve the opportunity and surface the
  payment handling condition before action.

## Order progression and closure

- Complete snapshot proves shipped: hard close and retention schedule.
- Complete snapshot proves fully canceled: hard close and retention schedule.
- Complete snapshot proves rep transferred: reversible close.
- Verified DEDUPE note: reversible close.
- Authorized human out-of-scope: reversible close.
- All active non-direct-ship lines IN_STOCK/FULL on an active unshipped order:
  DOI_MANUAL_REVIEW with ORDER_PROGRESS_REVIEW; do not infer release.
- Source disappearance never closes a case; it requires one read-only recheck.

## Uncertainty

Each unknown field emits its exact field-specific reason. Multiple independent unknowns use set
union. An UNKNOWN value is never proof for a positive conclusion and never erases independent
known facts.

## Opportunity scope and overlap

Every opportunity binds exact immutable line identities and quantities. Unproved scope creates no
opportunity or value. Overlapping/mutually exclusive options remain separate; the overall
potential is UNAVAILABLE until one explicit scenario selection exists.

## Intervention boundary

The engine recommends and records; it never performs an external order action. An intervention
exists only after a verified system or human action event. Potential value and realized value are
separate.
