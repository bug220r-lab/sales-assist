
# DOI Lifecycle Contract

## Case lifecycle

- NONEXISTENT → ACTIVE only from a valid admitted synthetic order.
- ACTIVE → CLOSED_HARD for shipped or fully canceled.
- ACTIVE → CLOSED_REVERSIBLE for transferred rep, verified DEDUPE, or authorized human
  out-of-scope closure.
- CLOSED_REVERSIBLE → ACTIVE only through a complete explicit prior-closure/retention binding.
- CLOSED_HARD never reopens.
- Purge success is absence; no identity tombstone survives.

## Evaluation lifecycle

A successful complete snapshot may append an evaluation with exact bindings to:

- snapshot;
- rules bundle;
- reason registry;
- business calendar;
- relationship revisions;
- action-context observations;
- structured human facts.

A changed accepted input appends a new evaluation; prior evaluations are never overwritten.
Rules unavailable never cause a substitute-version evaluation.

## Attention

Attention is a cause-keyed set reduced from immutable SET/CLEAR events. CLEAR references the
exact active SET and supplies a separate complete resolver group. Unrelated causes coexist.

## Relationship and observation histories

Alternate relationships, observations, contacts, DEDUPE, WWC, resulting links, interventions,
and value state are represented through immutable event/revision streams with exact predecessor,
sequence, natural-key, and content-hash guards.

## Invalid transitions

Every unlisted edge or false guard fails before append and preserves the last valid projection.
