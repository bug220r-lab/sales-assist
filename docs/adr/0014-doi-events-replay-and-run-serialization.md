# ADR 0014: DOI events, replay, and run-control serialization

- Status: accepted for Milestone 3
- Scope: pure transition reduction and process-local state coordination

## Decision

The lifecycle surface is a closed typed command union. Each command derives its registered
transition; callers cannot submit an arbitrary `TR-*` conclusion or trusted guard verdict. Guard
truth is evaluated from the transition's exact typed fact schema and a sealed result issued by the
owning domain reducer. All 115 routes derive their authority from typed run, source, extraction,
case, evaluation, product, coordination, action, intervention, value, link, KPI, closure, or purge
owners and bind those records into the guard-authority preimage. A synthetic registry fixture
capability is accepted only by the explicitly named fixture reducer; the production reducer
rejects it before append.

The pure reducer validates the prior state, evidence time, facts, predecessor, and sequence, then
returns one immutable event, a new projection, reasons, and the exact registry-required
persistence-neutral effect instruction. False guards, missing or extra facts, malformed material,
and fixture authority presented to production append nothing.

An absent coordinator stream admits only the closed set of unambiguous registry creation rows.
It cannot be initialized at an arbitrary transition's declared from-state. In particular, a purge
or other destructive-effect transition cannot be the first event on a nonexistent stream.

The process-local coordinator owns one re-entrant lock and commits staged copies of events,
projections, receipts, counters, and retention authorities as one swap. Replay lookup occurs before
allocation. Exact bytes return the prior logical result; the same natural key with changed bytes
conflicts; equal digest with different canonical bytes is a collision. Allocation or injected
effect failure restores byte-identical prior state.

An extraction-occurrence reservation and the pre-extraction `RC-084` systemic terminal branch use
the same run-control lock. If reservation commits first, terminalization is illegal. If systemic
terminalization commits first, reservation is illegal. A failed source attempt leaves the parent
run `IN_PROGRESS` until an explicit next-ordinal retry or an authorized
`FINALIZE_FAILED_SOURCE_IMPORT_NO_RETRY` command wins that same boundary. No timer, expiry,
background worker, or implicit finalizer exists.

Replay receipts are owned by their run/case/attempt graph. They are minimized or deleted with that
graph and cannot become an indefinite identity tombstone.

## Consequences

All 115 registry rows receive collected structural dispatcher coverage, focused false-guard and
from-state rejection, and exact required-effect assertions. That fixture inventory is not treated
as an owning business-proof oracle. A separate generated 230-selector layer executes one real
typed-owner legal route and one production-reducer invalid-from-state route for every transition.
Malformed exact-type owner records fail closed at the public adapter boundary. Durable
transactions, physical locks, SQL repositories, and crash recovery are deferred to Milestone 4
and must reproduce the in-memory semantics.
