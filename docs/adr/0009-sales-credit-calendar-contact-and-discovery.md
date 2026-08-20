# ADR 0009: Sales Credit calendar, contact, and discovery semantics

- Status: accepted for Milestone 2
- Scope: synthetic contact normalization, local-date windows, and complete order discovery

## Decision

Calendar decisions bind to `America/New_York`. An interaction review window contains the
interaction local date and the next 14 local dates. A cancellation replacement window uses the
same inclusive local-date rule from the cancellation date. Calendar membership is distinct from
instant ordering: an order must not precede its interaction, and same-day facts whose precision
cannot establish ordering route to human review.

Automatic no-order recheck is eligible at most once per New York local date while the review
window remains active. `FORCE_RECHECK` bypasses that throttle only for an explicitly selected
case with a bounded explanation. The pure eligibility result records that bypass; it never reads
a clock or schedules work.

`OrderSearchRun` is the invocation authority for those decisions. For automatic and force
triggers, every interaction in its nonempty immutable scope must already be in
`CHECKED_NO_ORDER_WINDOW_ACTIVE` with non-null prior-check and next-eligible witnesses. The run derives
one eligibility result per interaction, in interaction-ID order, from the run start instant, the
interaction's review-window dates, and its last-check instant. Construction rejects any result
that is ineligible while its window is active, any last-check instant after the run start, and any
force run without its bounded explanation. A run begun after the inclusive window may retain the
closed-window, not-allowed recheck witness solely as authority for the final absence check.
Successful runs retain the derived result tuple as an audit witness; a
selected force witness must record both the explanation and its throttle-bypass status.

Email normalization performs only ASCII-four edge trimming and ASCII lowercase conversion, then
requires the exact `example.test` domain. Phone normalization accepts only the existing fictional
555-0100 through 555-0199 formats. It removes formatting and a supplied country prefix but never
guesses an area code; seven- and ten-digit identities remain distinct.

Every usable email and phone is searched. Complete native result sets are combined and Order
Numbers are deduplicated only after canonical validation. Candidate enumeration never stops after
the first result. Any required incomplete result set prevents a no-order conclusion while
preserving all candidates that were actually returned.

`OrderSearchRun` receives the exact immutable `InteractionRecord` scope, not a caller-authored
identifier plan. It derives the sorted, unique interaction IDs and every normalized usable email
and phone from those records, then requires one native result set for every derived identifier and
no others. The attempted-identifier inventory and combined discovery result are derived fields and
cannot be supplied or replaced by a caller. Every scoped interaction must itself contain at least
one usable identifier; a usable contact on another interaction cannot hide an unsearchable record.

Every search run must start provably after every included interaction, regardless of trigger or
whether the result is favorable, empty, or incomplete. Exact same-day ordering must be strictly
positive; an imprecise same-day interaction cannot establish post-interaction authority. For a
complete empty result union, the search completion instant is converted to its
`America/New_York` local date. The no-order review state remains active through each included
interaction's inclusive D+14 date and closes only when every included interaction window has
elapsed. No caller-provided closed/open assertion participates in that decision. Contact material
exists only on the active interaction records, is excluded from representations, and is removed by
the separate governed closure projection.

A process-local `InMemoryNoOrderStateLedger` is the executable state authority over per-interaction
post-evaluation outcomes. It requires an explicitly injected process-local
`InMemorySearchRunAuthority`;
there is no silently isolated default. The no-order
ledger and case accumulator can therefore claim the same full canonical `OrderSearchRun` bytes under
one RunId boundary without module-global state. Exact material may have multiple explicit owners,
same-RunId changed material conflicts, and a failed enclosing transaction rolls back only the owner
claim it acquired. Under its state lock the no-order ledger returns the prior active transition only
for exact replay and stages interaction-state plus active-receipt changes together. The retained
interaction must exactly equal the run input, so a stale second command cannot reuse an earlier
`last_check_at` to bypass the New York local-day throttle; the same guard decides crossed concurrent
runs. Initial normal review moves an independently negative root from
`AWAITING_SOURCE_REVIEW` to `CHECKED_NO_ORDER_WINDOW_ACTIVE`; an eligible next-day automatic or
selected force recheck remains in that state. Each accepted active check records the run-start
instant as `last_check_at` plus the next New York midnight, including the first post-window midnight
that can authorize a terminal absence check. Trigger legality is checked before candidate outcome,
so a favorable result cannot bypass initial/recheck state authority. An initial normal search must
start strictly after the interaction instant; unreliable same-day precision cannot prove that
ordering and therefore cannot establish a no-order state.

The supported composed reducer locally recomputes every selector-owned candidate/interaction
evaluation from the exact snapshot and interaction. Qualifying pairs form the exact positive case
scope, deterministic before/after-window pairs support that interaction's no-order path, and any
timing-uncertain or otherwise unresolved pair preserves a governed manual state. One preserved pair
keeps its interaction manual even if a different candidate qualifies. Incomplete enumeration
retains returned candidates but applies `MANUAL_REVIEW_REQUIRED`; provenance records that this
specific manual state may recover through a later complete normal run to active or terminal
no-order. Identifierless and other manual causes cannot auto-recover. Mixed positive, manual,
active, and terminal interaction effects therefore commit from one unchanged original run without
inventing subruns.

The ledger has mutually exclusive process-local modes. Standalone compatibility mode preserves the
legacy aggregate complete-empty `apply_run` API and its frozen known-answer fixture, but rejects the
post-evaluation staging API. Coordinated mode rejects direct `apply_run` and accepts only the staged
per-interaction reducer used by `InMemorySalesCreditState`; the two receipt families cannot overlap.
The coordinator seals raw run bytes into a keyed authenticator and only the owner partitions that
actually exist: case-only for all-positive, no-order-only for all-negative, and both for mixed.
Exact sealed replay needs no new owner claim. Full SnapshotId/material parity is retained only for
active or manual negative roots and is removed at positive ownership transfer or terminal closure;
the terminal command's keyed authenticator preserves exact replay/conflict behavior without keeping
the snapshot or its lines through the closure retention window.

A fully evaluated run with no qualifying or unresolved candidate for a root creates its terminal
transition inside the lock when the state-authorized initial or recheck trigger begins after that
root's window. The run itself must start after the inclusive D+14 window; completion crossing
midnight cannot retroactively make a search that began inside the window terminal. The ledger then
builds and verifies the minimized no-order closure projection, removes the scoped
interactions and every overlapping contact-bearing active run receipt, and then retains only the
identity-free closure result. The shared authority erases its canonical contact bytes at this
boundary and retains only opaque run reservations, a per-ledger HMAC-SHA256 canonical authenticator,
and a newly allocated closure receipt ID. The secret HMAC key never leaves the ledger. Exact replay
of the terminal command through `apply_run` resolves to the minimized result, while changed material
under that RunId conflicts; a retired active command cannot be mistaken for a terminal replay. No
raw canonical bytes, interaction IDs, contacts, or unkeyed/reversible contact-derived digest remain.
Closure receipts are keyed by the opaque receipt ID rather than
the identity-free projection bytes, so two legitimate roots with identical minimized aggregates are
both countable and replayable. The receipt and its opaque run reservations are deleted together at
the exact elapsed 90-day boundary; purge is idempotent and leaves no replay material. Terminal
projection construction also consumes a per-transition, per-ledger capability bound to the exact
transition material and pending commit; there is no reusable module-level construction sentinel.
`REPLACEMENT_CHECK` retains an empty recheck-witness tuple and is never accepted by this ledger or
the no-order closure builder as authority for an original-order no-order state.

## Consequences

DST affects offsets but not the 15-date window. Search reduction is deterministic and adapter-free.
Displayed fictional names are not matching keys, and malformed identifiers are never repaired or
substituted. Search construction performs no I/O, clock read, network call, or persistence action.
The ledger is process-local only and creates no Milestone 3 business persistence.
