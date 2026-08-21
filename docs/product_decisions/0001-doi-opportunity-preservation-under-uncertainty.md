# DOI opportunity preservation under uncertainty

Status: Approved
Decision ID: `M3_DOI_OPPORTUNITY_PRESERVATION_V1`
Applies to: Milestone 3 DOI rule pack

## Decision

```text
M3_UNCERTAINTY_CONTAINMENT_POLICY =
PRESERVE_INDEPENDENTLY_PROVEN_OPPORTUNITIES

M3_OVERLAP_POLICY =
PRESERVE_SEPARATE_OPPORTUNITIES_AND_WITHHOLD_ONLY_AGGREGATE_POTENTIAL

TR_037_MANUAL_REVIEW_POLICY =
USE_ONLY_WHEN_NO_SAFE_OPPORTUNITY_OR_OTHER_HIGHER_PRECEDENCE_RESULT_IS_PROVABLE
```

An UNKNOWN fact blocks only conclusions whose complete basis depends on that fact. When at
least one DOI opportunity is independently proved from complete known facts, the top-level
result remains `DOI_OPPORTUNITY`. Every applicable field-specific UNKNOWN reason and its
human-review or handling requirement remains visible; it does not erase the independently
proved opportunity.

When an UNKNOWN fact affects only one candidate, only that candidate is suppressed or
qualified. Other independently proved opportunities remain.

`TR-037` (`DOI_MANUAL_REVIEW`) is used only when uncertainty prevents every safe opportunity,
exclusion, closure, or monitor conclusion.

Overlapping or mutually exclusive valid opportunities remain distinct. The evaluation emits
`RC-087 POTENTIAL_OVERLAP_UNRESOLVED`, does not add or double-count their values, marks
aggregate potential unavailable, and requires an explicit human scenario selection. The
top-level state remains `DOI_OPPORTUNITY`. A valid explicit selection resolves aggregate
potential without rewriting the retained opportunity records.

## Effective ownership overlay

The supplied transition registry contains exactly three top-level `DOI_OPPORTUNITY` routes:

- `TR-033` — mixed direct ship;
- `TR-034` — fulfillment split;
- `TR-035` — alternate or exact-SKU opportunity.

The implementation-side effective ownership overlay is therefore:

| Reason | Effective legal transition routes | Guard |
|---|---|---|
| `RC-016 UNKNOWN_LINE_AVAILABILITY` | `TR-027`, `TR-028`, `TR-033`, `TR-034`, `TR-035`, `TR-037` | A positive route is legal only when its complete basis is independent of the unknown availability fact; otherwise `TR-037`. |
| `RC-017 UNKNOWN_LINE_DS_STATE` | `TR-027`, `TR-028`, `TR-033`, `TR-034`, `TR-035`, `TR-037` | A positive route is legal only when its complete basis is independent of the unknown direct-ship fact; otherwise `TR-037`. |
| `RC-018 UNVERIFIED_LINE_CONTINUITY` | `TR-027`, `TR-028`, `TR-033`, `TR-034`, `TR-035`, `TR-037` | A positive route is legal only when it does not depend on the unproved continuity conclusion; otherwise `TR-037`. |
| `RC-115 UNKNOWN_LINE_ETA_STATE` | `TR-027`, `TR-028`, `TR-033`, `TR-034`, `TR-035`, `TR-037` | ETA-independent opportunities survive; only ETA-dependent ranking or impact is unavailable. |
| `RC-116 UNKNOWN_ORDER_STATE` | `TR-027`, `TR-028`, `TR-033`, `TR-034`, `TR-035`, `TR-037` | A positive route is legal only when complete line facts prove the opportunity independently of order-state uncertainty; otherwise `TR-037`. |
| `RC-087 POTENTIAL_OVERLAP_UNRESOLVED` | `TR-033`, `TR-034`, `TR-035` | At least two valid opportunities overlap or are mutually exclusive; aggregate potential remains unavailable pending explicit selection. It never forces `TR-037` by itself. |

Every similarly situated field-specific UNKNOWN reason may accompany the actual positive route
only when that route has a complete independent basis. Otherwise its existing manual-review
route applies. No UNKNOWN value is used as positive proof.

This overlay changes no identifier inventory: the supplied registries remain exactly 138 reason
codes, 138 ownership rows, and 115 transitions. It adds no reason or transition and does not
modify any file under `specs/`, `reference/`, `BUNDLE_MANIFEST.json`, or `SHA256SUMS.txt`.

## Required proof

Executable Milestone 3 tests must prove:

- a known split survives unrelated unknown availability;
- a known split survives unrelated unknown direct-ship state;
- an ETA- or continuity-independent opportunity uses its actual positive route;
- an order-state-independent opportunity owns `RC-116` on its actual positive route;
- an unknown fact blocks the only candidate opportunity and routes to `TR-037`;
- overlapping valid opportunities remain separately retained;
- aggregate potential is unavailable before selection and exact after selection;
- `RC-016`, `RC-017`, `RC-087`, and similarly situated UNKNOWN reasons emit only on legal
  effective routes;
- no illegal emission is accepted; and
- the 138/138/115 supplied inventories remain unchanged.
