# ADR 0050: Surface held split-review leads without resolving holds

Status: accepted for isolated source review; not installed or merged.

## Problem

The default CSV worklist required both eligible rep scope and an apparent split status.
An assignment-provenance hold suppressed the entire split projection, hiding distinct
purchased-line ready/waiting observations from that worklist. A short list could therefore
be mistaken for an exhaustive list of orders worth reviewing. Stock counters also require
a separate description: on-hand stock below ordered quantity is not verified allocation.

## Decision

Add a separate, closed advisory discovery projection to the transient CSV review response.
Do not change the existing split classification, rep scope, hold codes, evidence completeness,
quantity verification or decision eligibility. The response schema advances to v6; the
existing split projection remains v1. No durable-store schema or evidence-key change occurs.

A held ready/waiting lead is found using the existing classifier on an immutable diagnostic
copy that omits only `SOURCE_ASSIGNMENT_CONFLICT_OR_UNKNOWN`. All other capture, structural,
global, terminal, stock-conflict, drop-ship, zero-remaining and kit rules still apply. The
original order and its holds remain unchanged. Component rows never count as independent
purchases. A purchased kit parent must satisfy the existing component-coherence checks.

Stock-counter clues are separate from ready/waiting patterns. They compare only bounded,
numeric captured OH and ordered quantity on a non-kit physical purchase. They never supply
remaining quantity, active quantity, allocation or drop-ship evidence. Existing apparent
patterns and held ready/waiting leads take priority so a stock clue does not duplicate them.
Known terminal orders, known drop-ship lines and zero remaining lines cannot become leads.
Untrustworthy capture or structural scope remains suppressed.

The default view includes eligible and held rep scopes, excludes confirmed other-rep
assignments, and shows apparent patterns plus held ready/waiting leads. Separate filters
retain the original eligible-only view and expose stock-counter clues explicitly. Currency
conflicts remain visible holds in the broader view; the eligible-only view keeps its existing
currency exclusion. The original classification and rep/capture holds stay visible beside
each advisory label. No label calls a lead approved, allocated or ready to fulfill.

`Hide reviewed` is still applied after all scope/group filters and is never reset by changing
the view. Discovery does not write review marks, alternate drafts or source captures. Mark
bindings continue to depend on the same raw evidence, so existing matching checks survive
reload and restart without migration. Unknown or unavailable marks retain existing behavior.

## Validation and boundaries

Synthetic tests cover assignment-held patterns, unrelated holds, closed/structural captures,
distinct purchase identities, kit components, stock clues, strict response validation and
saved-state preservation. The shipped JavaScript is exercised without a browser, including
default filtering, held badges, separate stock clues and reviewed exclusion across filters.

This is an observation/discoverability change. The binding DOI engine, automatic split
eligibility, customer communication, authentication and transfer workflows are unchanged.
No real capture, customer fixture, browser or external API is used in implementation tests.
