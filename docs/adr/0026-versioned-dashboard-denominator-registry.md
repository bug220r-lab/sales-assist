# ADR 0026: Versioned dashboard denominator registry

- Status: Accepted
- Date: 2026-09-01
- Decision scope: Milestone 7 telemetry and value presentation

## Context

Milestone 7 combines request telemetry, current projections, evaluation outcomes, human review,
latency, backups, and exact Money. Those values have different populations. A visually plausible
rate can still be false if replays, conflicts, maintenance operations, historical events, overlap,
or mixed currencies enter the wrong denominator.

## Decision

A versioned machine-readable registry is the sole dashboard definition source for metric names,
numerators, denominators, time windows, inclusions, exclusions, units, empty-denominator behavior,
and drill-down route. Rendering consumes computed metric records paired with those definitions;
templates do not redefine a denominator.

Terminal business-request telemetry is distinct from maintenance telemetry. Exact replays are
included in request totals only where the registry says so and are always broken out. Replays and
conflicts never count as unique evaluations. Human-review rate uses new unique evaluations whose
current result requires review. Current-case and active-opportunity metrics use current projections,
not event totals.

Rates with an empty denominator display `N/A`, never `0%`. Every rate shows numerator,
denominator, exclusions, and selected window. Latency declares its terminal-business-request
sample and exposes median and P95; throughput declares its wall-clock unit. Opportunity count is
explicitly allowed to exceed case count.

Money is never combined across currencies. Potential value includes only exact eligible potential;
unavailable values and unresolved overlap are excluded and counted separately. Realized value
includes only current exact verified intervention contribution, with corrections and reversals
applied exactly once. Aggregate views expose no identity.

## Consequences

- UI cards, accessible tables, API data, and documentation share one exact metric definition.
- Denominator, replay, conflict, empty, overlap, and mixed-currency edge cases are executable tests.
- A metric definition change requires a registry version change and traceability update.

## Rejected alternatives

- Template-local formulas or undocumented rates.
- Treating an empty population as zero percent.
- Mixing currencies or converting without a governed rate.
- Treating unresolved overlap, unavailable value, or recommendations as realized value.
