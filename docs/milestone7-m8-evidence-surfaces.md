# Milestone 7 machine-readable M8 evidence surfaces

This inventory creates stable evidence inputs only. It does not implement Milestone 8 packaging,
audit, benchmarking, screenshots, release construction, or publication.

| Surface | Contract | Stable evidence |
|---|---|---|
| `/api/v1/dashboard/evidence` | `synthetic-sales-assist-m8-evidence-surfaces/v1` | fixed dashboard-route inventory, manager-demo step count, and stable selector prefix; the version, safety/network, database, backup, and metric values remain on the closed endpoints below |
| `/health` | existing API v1 health | owned local service/database/projection/safety readiness |
| `/api/v1/dashboard/overview` | Control Center v1 | current projection counts and metric definition references |
| `/api/v1/dashboard/system` | Control Center system v1 | privacy-safe service, database, latest verified backup/restore, recent safe errors, fixed M4 benchmark reference, extension, network, and timestamped safety state |
| `/api/v1/dashboard/system/database` | database status v1 | schema, migration, quick/deep/FK/projection results, latest verified backup/restore, and explicit verification/safety observation times |
| `/api/v1/dashboard/system/backups` | backup status v1 | privacy-safe verified receipt inventory |
| `/api/v1/dashboard/system/telemetry` | metric denominators v1 | numerator, denominator, exclusions, time window, latency, throughput, result distributions, database errors/size, verified backup/restore state, fixed M4 benchmark reference, and currency segmentation |
| HTML `data-ssa-dashboard-*` attributes | Control Center DOM v1 | stable page, card, state, action, current-projection, timeline, table, and live-region selectors |

Every endpoint is loopback-only, bounded, identity-free where aggregate, safe-error wrapped, and
free of absolute paths/usernames in ordinary mode. Snapshot consumers must not treat these inputs
as a final audit verdict; M8 remains a separate milestone.
