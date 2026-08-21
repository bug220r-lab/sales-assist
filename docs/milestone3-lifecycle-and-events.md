# Milestone 3 lifecycle and event reduction

The lifecycle engine recognizes exactly the supplied 115 transition references. Registry rows are
normalized into one immutable definition shape, while the original registry bytes remain
unchanged.

## Command boundary

A typed command contains a registry-issued transition reference, semantic stream and occurrence
identities, exact current state and sequence, predecessor binding, guard evidence, and the legal
reason set. The target state and effect family are registry-derived; callers cannot select them.
Guard truth is derived internally from the transition's closed typed fact schema. Callers cannot
submit a trusted verdict, omit a registered guard member, or add an unregistered member. Purely
factual and authority-sensitive routes both require the owning domain's sealed result. The 31
public owner adapters cover all 115 transitions across run/source/extraction, case/attention,
evaluation, product knowledge, Action Context, contact/WWC/DEDUPE, intervention/value/link/KPI,
closure, and purge owners. An authorized `StructuredHumanFact` for `TR-013`, for example, cannot
be replaced by caller booleans; nor can a generic attention event replace the cause-keyed
case/attention owner for `TR-020` through `TR-026` or `TR-092` through `TR-095`.

The synthetic registry fixture authority is a separate structural-test capability. Production
`reduce_transition` rejects it before append. Only `reduce_fixture_transition` accepts it, for
exhaustive normalization, false-fact, from-state, replay, and exact-effect tests; those tests do
not assert that a synthetic all-positive fact map is owning business proof.

The pure reducer performs:

1. closed schema and reference validation;
2. exact replay lookup before allocation;
3. current-state, sequence, predecessor, and guard validation;
4. reason/effective-owner validation;
5. immutable event construction;
6. deterministic projection rebuilding; and
7. exact registry-required, persistence-neutral effect derivation.

Every rejection leaves the prior stream byte-identical. A reused occurrence with changed material
conflicts, and an equal digest with different canonical bytes is a collision.

An absent stream admits only a registered creation route. It cannot bootstrap itself at an
arbitrary transition's declared from-state. Structural tests bind all 115 rows to their exact
registered required-effect tokens and reject any missing, extra, or semantically mismatched effect.
Separate generated production-path tests execute one typed-owner legal route and one production
invalid-from-state route for each of the 115 transitions. Fixture authority and malformed raw owner
objects are rejected before append.

Action Context observation links require a distinct current observation whose observation time is
strictly later than the context opening time. KPI initialization binds its occurrence to the
retained KPI event when one exists, or to the retained intervention action event for a governed
no-row branch such as direct-ship separation; callers cannot mint a second no-row occurrence.

## Coordinator boundary

The in-memory coordinator stages copies of every touched event stream, projection, receipt, run,
case, KPI contribution, and retention owner under one lock. It swaps only after all reducers and
cross-object invariants pass. Fault injection proves rollback at each stage. This is semantic
transaction simulation for tests, not durable persistence.

Extraction reservation and pre-extraction systemic `RC-084` terminalization share the run-control
boundary. Retry and explicit no-retry finalization share it as well. No timeout, background task,
implicit retry, or automatic finalizer exists.

## Retention

Hard and governed reversible closures bind one New York calendar-90 deadline. A legal reversible
reopen cancels only its exact retained deadline. At purge, current KPI contributions are reconciled
and transferred to identity-free buckets before the complete case graph and owned receipts are
deleted atomically. Failed reconciliation deletes nothing. No tombstone or drill-through survives.
