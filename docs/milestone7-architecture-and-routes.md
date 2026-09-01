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
| `/overview` | current operational cards and denominator summaries |
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
