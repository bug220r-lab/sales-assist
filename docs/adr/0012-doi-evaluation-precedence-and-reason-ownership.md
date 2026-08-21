# ADR 0012: DOI evaluation precedence and effective reason ownership

- Status: accepted for Milestone 3
- Scope: pure DOI evaluation and implementation-side reason routing

## Decision

The DOI evaluator is a pure function. It receives immutable, normalized facts and returns a
closed result containing the top-level DOI state, the actual registered transition, an exact
registry-backed reason set, separately scoped opportunities, handling/review conditions,
aggregate-potential state, closure proposal, and a closed explanation. It performs no allocation,
clock read, I/O, network operation, persistence, or external mutation.

For a complete evaluation, verified closure and exclusion facts take precedence, followed by
opportunity, manual review, and monitor. A review condition never erases an independently proved
opportunity. UNKNOWN is never positive proof and blocks only the candidate whose complete basis
depends on it.

The approved product decision in
`docs/product_decisions/0001-doi-opportunity-preservation-under-uncertainty.md` is implemented as
an immutable effective-ownership overlay. It adds positive routes `TR-033`, `TR-034`, and `TR-035`
for similarly situated field-specific uncertainty, including `RC-016`, `RC-017`, `RC-018`,
`RC-115`, and `RC-116`, when an independent complete basis survives. It routes `RC-087` through
the actual positive route and withholds only aggregate potential. `TR-037` remains legal for field
uncertainty only when no safe higher-precedence conclusion survives. The supplied 138-reason,
138-ownership-row, and 115-transition registries are not modified.

Every output reason is checked against the effective route before construction. Traceability maps
each supplied row to an independently collected owning-rule or boundary test. Registry planning
oracle strings and generated lifecycle acceptance are reconciled separately and are never treated
as proof that an owning service actually emitted a reason.

## Consequences

Candidate conclusions and aggregate potential are separate dimensions. Human scenario selection
may resolve aggregate value without rewriting the immutable opportunity set. An illegal
reason/transition combination fails closed before an evaluation is returned or appended.
