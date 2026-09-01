# ADR 0024: Local human-action and idempotency boundary

- Status: Accepted
- Date: 2026-09-01
- Decision scope: Milestone 7 synthetic human actions only

## Context

The Control Center must demonstrate one Sales Credit manager outcome and one DOI overlap-scenario
selection, including exact replay and changed-material conflict. It must not add business rules or
turn a classification, opportunity, or evaluation into a human decision. Existing application
services and reducers already own the valid commands, authority checks, events, projections,
idempotency semantics, and receipts.

## Decision

Every rendered action is first bound in the checked-in action-to-service matrix. An HTTP handler
is a thin closed-schema adapter: it validates confirmation, a reserved synthetic subject and actor,
a bounded request key, and the exact command members, then invokes only the mapped application
service/reducer transaction. Unsupported operations are absent or explicitly read-only.

Sales Credit manager outcomes call the committed manager-outcome persistence service. The outcome
enum stays closed; `PARTIAL` requires exact Money and currency under the existing command. The
manager event and receipt are separate from—and cannot mutate—the system classification.

DOI overlap selection is one atomic application transaction over the existing action-context
authority check, synthetic-human authority check, structured-human-fact event/reducer,
`ScenarioSelection`, DOI evaluation, owner event append, durable evaluation persistence, and
existing idempotency repository. The UI cannot split that operation into partially durable calls.
Selecting one scenario does not clear unrelated attention causes or manufacture an intervention,
resulting-order link, or realized value.

Each action requires an explicit user gesture and a visibly selected confirmation. Canonical
command material is bound to the request key. Byte-identical material returns an exact replay
receipt; changed material under that key returns a conflict and changes no projection. Safe error
envelopes expose no stack trace, raw row, absolute path, or unrestricted note.

## Consequences

- UI code remains presentation and transport only.
- System classifications and human decisions remain separate objects and timeline events.
- Demonstrated replay/conflict behavior is the existing durable domain behavior.
- Adding a button requires a real mapped service and executable proof.

## Rejected alternatives

- Implementing transition or classification logic in a route, template, or browser script.
- Approximating an unsupported DOI action with a generic event append.
- Generating human facts, interventions, links, or value during evaluation.
- One-click unconfirmed actions or a request key that is not bound to canonical command material.
