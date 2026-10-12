# ADR 0048: Separate source copy approval from observed duplicate evidence

Status: accepted for the disabled single-owner coordinator.

## Problem

The coordinator loaded a source approval bundle before performing its live recipient and
duplicate GET checks. The bundle validator required the duplicate check to be complete,
so an honest unresolved duplicate review could never reach the check that would resolve it.
Conditional approval of one exact unsent draft does not justify inventing a prior finding.

## Decision

Only the coordinator's bundle adapter may retain `duplicate_status: unresolved` when
`DUPLICATE_RECONCILIATION_REQUIRED` is the sole remaining hold. An explanatory pending note
may remain in the source review. Every factual, identity, cart, link, copy and known-duplicate
hold still blocks preparation. The global CSV review and durable approval contracts remain
unchanged, and continue to reject an unresolved duplicate review.

The private source bundle remains immutable and hash-bound. After a complete, fresh,
exact-bundle recipient/duplicate preflight, the adapter derives a separate execution review.
Only the observed duplicate finding is added; no factual review is inferred. The finding
states `NO_MATCH_IN_ACCESSIBLE_MAILBOX_SNAPSHOT` and explicitly denies proof of global draft
absence. The stable execution review binds the source file hash, source approval binding,
approval reference, mailbox and verified native customer. Observation time and counts are
recorded separately in the original provenance audit; they do not change the copy approval
binding when a later fresh check observes the same approved identity.

The normal approval binding is computed for that execution review and the unchanged row,
recipient, subject, plaintext, rendered body and version. Source and execution bindings
are recorded separately in the private ledger audit before normal service approval. New
rows still use ordinary import, edit, approve and durable transfer commands. An existing
row must match the execution review and binding, and retain the matching source/execution
identity with a valid original observation audit. Conflicts are held without editing or
overwriting the row.

The sealed proof is checked against the original source bundle before preparation,
before deferred approval and before the one transfer attempt. A stale, forged or mismatched
proof cannot complete the pending check. Unknown outcomes remain non-retryable. No schema
migration, automatic credential renewal, customer sending or order mutation is introduced.

## URL representation boundary

HTML attribute entity decoding occurs exactly once at HTML readback. A literal `&amp;`
inside the plaintext/Markdown URL is part of that URL; rendering correctly escapes it
again. Silently decoding the source target would change approved copy and its binding.
Such invalid source cart/CTA targets remain held. Resolve their representation against
the authoritative approval input or obtain approval for an actual copy change.

## Consequences and validation

Content approval can be prepared honestly before the coordinator's duplicate GET check,
but cannot authorize creation before that check succeeds. Persisted provenance distinguishes
supplied approval from machine-observed facts. A changed source or native customer conflicts
with the existing entry. A later fresh observation of the same source/customer can recover
an existing uncertain result without changing the approval or repeating the POST.

Synthetic adapter tests cover pending preparation, exact-copy preservation, real sealed
proof, factual/cart/link holds, stale or forged proof, ledger/provenance conflicts and
uncertain-write replay protection. HTML entity regressions distinguish valid encoded HTML
attributes from invalid literal source targets. No live access is part of validation.
