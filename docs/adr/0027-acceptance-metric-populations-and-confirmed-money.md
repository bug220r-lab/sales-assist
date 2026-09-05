# ADR 0027: acceptance repairs to metric populations and confirmed Money

Status: accepted internal implementation decision, 2026-09-05.

A stale browser form can submit a new outcome after the case has closed. The repository
correctly rejects it with MANAGER_OUTCOME_CASE_INVALID. Its exception carries the code as
the exception message, unlike the idempotency exception's code attribute. The adapter now
preserves that closed conflict code instead of raising AttributeError and returning 500.
The HTTP regression proves 409, exact replay, and unchanged classification for all five
manager outcomes. This is error translation only; closed-case mutation remains prohibited.

Agent-executed baseline acceptance reproduced stale PARTIAL Money in an APPROVED form
and a dashboard failure after a valid DOI overlap selection. Separate source review found
two additional mismatches with the existing denominator registry. Business definitions,
source facts, canonical action material, database schema, and domain validators are unchanged.

The manager form clears and hides Money outside PARTIAL, marks both Money fields required
for PARTIAL, and sends explicit null Money members for other outcomes. Changing material
clears the confirmation checkbox. Its confirmation includes actor, outcome, and exact minor
units/currency. The server continues rejecting prohibited, missing, or inexact Money.

Human-review numerator reads each durable DOI output's human-review requirements, including
opportunities requiring commercial or scenario decisions. Manager-outcome numerator applies
the same selected half-open window to recorded outcome history and eligible evaluation history.

Processing telemetry requests and distinct durable evaluations are different populations
under ADR 0026. A human DOI selection can append an evaluation outside processing telemetry.
The renderer must accept that retained state; it cannot impose evaluations <= requests.
Same-population bounds, rate and distribution reconciliation, and safety checks remain enforced.
No synthetic telemetry is manufactured to repair old databases. No migration is needed.

Executable regressions: `tests/test_m8_acceptance_repairs.py` executes shipped JavaScript
request construction and actual persistence services. The DOI selection test in
`tests/test_milestone7_end_to_end.py` verifies both HTML/API overview and telemetry after
selection, replay, conflict, and reopening retained state. Existing M7 semantic-negative
rendering tests continue to enforce valid within-population constraints.
