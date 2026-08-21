# Milestone 3 opportunity and precedence matrix

## Top-level precedence

| Priority | Result | Governing condition |
|---:|---|---|
| 1 | `DOI_EXCLUDED` | Verified hard/reversible closure, full direct ship, or payment-only exclusion. Only governed closure starts retention. |
| 2 | `DOI_OPPORTUNITY` | At least one independently safe, exactly scoped opportunity survives. Unrelated UNKNOWN/review flags remain visible. |
| 3 | `DOI_MANUAL_REVIEW` | No safe higher result exists and uncertainty or non-routine review blocks monitor. |
| 4 | `DOI_MONITOR` | Active valid case, no current opportunity, and no blocking review. |

## Opportunity routes

| Transition | Opportunity basis | Required result behavior |
|---|---|---|
| `TR-033` | Mixed direct ship | Preserve DS separation and continue safe non-DS analysis. |
| `TR-034` | Fulfillment split | Bind exact in-stock/full and delayed scope; ETA affects ranking only. |
| `TR-035` | Exact SKU or verified alternate | Preserve relationship, observation, Action Context, and review bindings. |

Partial quantity remains a separately scoped human decision. Payment and geography can add
handling without deleting a product opportunity. Full direct ship requires a nonempty complete
relevant-line universe. All-in-stock/full never implies release and routes to progress review.

## Unknown containment

An UNKNOWN field contributes its exact registered reason. It cannot prove a positive result. If an
opportunity has a complete basis that excludes the unknown fact, the opportunity remains and the
reason travels on its actual `TR-033`, `TR-034`, or `TR-035` route. This includes independently
contained availability, direct-ship, continuity, and ETA uncertainty; field UNKNOWN reasons that
already have supplied positive-route ownership retain it. `TR-037` is used only when no safe
opportunity, exclusion, closure, or monitor conclusion is provable.

## Overlap and aggregate value

Valid overlapping or mutually exclusive opportunities remain distinct. `RC-087` is emitted on the
actual positive route. Before an explicit scenario selection, aggregate potential is unavailable
and no values are summed. Mutually exclusive grouping requires exact hash-bound evidence from an
authorized structured human fact; a caller-supplied grouping identifier is never trusted. A
selection binds the exact opportunity set and selected member, after which aggregate potential
may be exact if all required money facts share one currency binding.
