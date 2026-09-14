# Milestone 7 Control Center architecture and route inventory

- Dashboard contract: `synthetic-sales-assist-control-center/v1`
- API response: `synthetic-sales-assist-api/v1`
- API request: `synthetic-sales-assist-api-request/v1`
- Origin: `http://127.0.0.1:8765/`
- Database schema: `4` (unchanged)

## Boundaries

`ControlCenterApplication` is the only dashboard application facade. Read methods consume current
schema-4 projections, immutable history, telemetry, database verification, and backup receipts.
Mutation methods are thin adapters mapped to already committed services/reducers. HTTP handlers
perform only route binding, closed transport validation, local confirmation, and response
validation. Templates and JavaScript contain no business rule.

The server remains a single owned loopback listener with exact Host, Origin, CSRF, body-size,
method, CSP, safe-error, and shutdown-token controls. There is no file server, SQL console,
external asset, remote analytics, or non-loopback capability.

## HTML GET routes

| Route | View |
|---|---|
| `/` | `303` redirect to `/overview` |
| `/overview` | current Sales Credit cases, DOI cases and opportunities, and items needing review |
| `/sales-credit` | current Sales Credit queue |
| `/sales-credit/{case_id}` | Sales Credit current classification, separate manager outcome, and timeline |
| `/doi` | current DOI queue |
| `/doi/{case_id}` | DOI current result, opportunities, human facts, value history, and timeline |
| `/review` | unified presentation of domain-distinct unresolved review items |
| `/orders/{order_id}` | existing synthetic order detail, enhanced with safe Control Center links |
| `/runs/{run_id}` | existing immutable run view |
| `/audit/{subject_kind}/{subject_id}` | allowlisted subject timeline |
| `/system` | local service, database, extension, network, and safety health |
| `/system/database` | quick/deep/foreign-key/projection verification |
| `/system/backups` | verified backup receipts and explicit create action |
| `/system/telemetry` | denominator-bound metrics and accessible table alternatives |
| `/system/extension` | truthful package/last-seen status and exact permission identity |

Routes admit an optional closed `presentation=1` query only where documented. Queue query fields
are the bounded contract in `docs/milestone7-current-projection-history-contract.md`.

## Local JSON API routes

| Method | Route | Purpose |
|---|---|---|
| `GET` | `/api/v1/dashboard/overview` | current cards and metric definitions |
| `GET` | `/api/v1/dashboard/sales-credit` | bounded current Sales Credit list |
| `GET` | `/api/v1/dashboard/sales-credit/{case_id}` | current detail plus immutable timeline |
| `GET` | `/api/v1/dashboard/doi` | bounded current DOI list |
| `GET` | `/api/v1/dashboard/doi/{case_id}` | current detail plus immutable timeline |
| `GET` | `/api/v1/dashboard/review` | domain-aware current review list |
| `GET` | `/api/v1/dashboard/audit/{subject_kind}/{subject_id}` | bounded immutable timeline |
| `GET` | `/api/v1/dashboard/system` | privacy-safe system status |
| `GET` | `/api/v1/dashboard/system/database` | latest database verification |
| `GET` | `/api/v1/dashboard/system/backups` | verified receipt inventory |
| `GET` | `/api/v1/dashboard/system/telemetry` | denominator-bound metrics |
| `GET` | `/api/v1/dashboard/system/extension` | five-state extension status |
| `GET` | `/api/v1/dashboard/evidence` | stable machine-readable M8 evidence inventory |
| `POST` | `/api/v1/dashboard/sales-credit/{case_id}/manager-outcome` | confirmed existing manager-outcome service |
| `POST` | `/api/v1/dashboard/doi/{case_id}/scenario-selection` | confirmed atomic thin adapter over existing DOI authorities |
| `POST` | `/api/v1/dashboard/system/database/verify` | explicit deep verification |
| `POST` | `/api/v1/dashboard/system/backups` | explicit verified backup creation |
| `POST` | `/api/v1/system/extension/handshake` | process-local closed version observation |

Existing M5/M6 route methods and paths remain available. Restore and reset remain separate CLI
workflows and are not overview actions.

## Privacy-safe output

Ordinary pages classify the database with a closed privacy-safe location class such as
`LOCAL_APPLICATION_DATA`, `LOCAL_TEMPORARY`, or `LOCAL_FILESYSTEM`, and classify the runtime as
`OWNED_LOCAL_RUNTIME_DIRECTORY`; they do not expose absolute paths or usernames. Presentation mode
further suppresses volatile PID/timestamp details without falsifying state. Every identifier is
validated against its reserved synthetic namespace before query or rendering.

## Overview presentation

The landing page shows four current-work cards with links to their queues. Technical
request counts, latency measurements, distributions, metric definitions, and health
diagnostics are available under System and its telemetry page. The overview API still
returns the full metrics and reconciliation contract; presentation does not change
counts, validation, business outcomes, or stored history.

## Sales Credit list presentation

The current case list shows Order, Status, and View case. Status labels use plain
language, with a separate Needs review indicator for unresolved human review. Full
order IDs and links remain intact. Evidence, attribution, placed-value status,
interactions, updates, and manager outcomes remain on the case detail page.

Search stays visible. Status, sort, direction, and page size sit in Filter and sort,
which expands automatically for a nondefault filter or sort. Query values, pagination,
API contracts, and business rules are unchanged.

## DOI list presentation

The DOI list shows Order, Opportunity / status, and View case. Short opportunity
labels replace internal tokens, and repeated types appear once without changing
underlying opportunity counts. Reason codes, value availability, lifecycle, and
explanations remain in the case detail and existing API.

A single Needs review cue covers evaluation review, current attention, required
option selection, or manual review. A case without an evaluation says Not evaluated.
Search stays visible; Filter and sort contains status and sorting controls, using
the same compact layout and query-preservation rules as Sales Credit.

## Human review list presentation

Human review uses the same compact three-column case list: Order, Next step, and
View case. Each order keeps its Sales Credit or DOI label. DOI rows display the
order ID while their links retain the distinct case ID. Plain-language next steps
replace action codes, and cases with no available action are marked View only.

Reason codes, source metadata, and history remain in the detail and audit pages.
All review validation and authority checks remain unchanged; the list creates no
new action or permission.

## System presentation

System keeps its status cards and diagnostic sections, with plain-language labels
for app checks, database checks, extension observations, connections, and safety
counters. A package being available does not imply installation or recent activity.
An unrequested integrity check says Not run, and projection drift still needs review.
The performance reference remains explicitly labeled as a saved test run.

Technical versions, timestamps, backup identities, and error codes remain available.
Detailed maintenance pages and all underlying status validation are unchanged.
