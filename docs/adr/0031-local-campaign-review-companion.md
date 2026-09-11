# ADR 0031: Opt-in local campaign review companion

## Status and authorization

Accepted for the user-requested Campaign Replies integration, 2026-09-11.
The user requested integrating the separately running local draft dashboard into
Sales Assist. This adds a bounded presentation exception to the original
synthetic-only product scope. It does not authorize real inputs to the Sales
Credit or DOI engines or customer messaging from this application.

## Decision

Add an HTML-only `/campaign-replies` page in the Control Center navigation.
The feature is disconnected by default. The exact environment opt-in
`SSA_CAMPAIGN_REPLIES=1` enables an isolated frame only when the portal's origin
is `http://127.0.0.1:8765`. Its destination is fixed at
`http://127.0.0.1:8770/?embedded=1`; neither requests nor environment values can
replace that destination.

The companion is independently installed and started by its existing local
workflow. Its records, review logic, refresh cycle, authentication and lifecycle
remain outside this repository. Sales Assist neither reads companion artifacts
nor requests its API, proxies responses, receives cross-frame messages, or
persists customer content. No schema, rule, telemetry population, extension
permission, source extraction, or synthetic identity contract changes.

The live companion page has distinct labeling. Existing module pages retain
their synthetic-only labels. A saved draft receipt must not be relabeled as a
fresh check of remote state; the companion retains its own provenance warnings.

## Browser boundary

Only the enabled successful companion response permits `frame-src` for the
fixed companion origin. All other pages and errors retain the original CSP.
The frame's sandbox permits its scripts, its own origin, and separate-window
review links. It does not permit forms, top navigation or downloads.
`allow-same-origin` preserves the child's own data access; the different port
still prevents the parent from reading the child's DOM or responses.

The companion must allow only the exact portal origin in `frame-ancestors`.
It must keep same-origin data access, no CORS permission, no remote resource
loads from message content, and its existing read-only action boundary.
There is no readiness or row-count proxy. A persistent separate-window link and
local-service guidance remain available if the frame cannot load.

## Verification and limits

`tests.test_campaign_replies` covers default-off behavior, exact enablement,
fixed origin, navigation, sandbox, route and CSP limits, and absence of backend
calls. Existing portal security and complete regressions remain required.
The optional companion is not included in the synthetic demo package and its
service is not started by the portal. Review records must never enter fixtures,
logs, repository files, or the synthetic database.
