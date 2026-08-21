# ADR 0021: Local portal, closed API/DOM contracts, and owned lifecycle

- Status: Accepted
- Date: 2026-08-21
- Decision scope: Milestone 5 localhost service and synthetic portal only

## Context

Milestone 5 is the first network-listening and browser-visible boundary. It must expose existing
application services without duplicating Sales Credit or DOI rules, remain unreachable from
non-loopback interfaces, publish a stable future extraction contract, protect local actions, and
allow Windows scripts to stop or reset only the process and files they own.

## Decision

Use the Python standard-library HTTP server behind the module entry point:

```text
python -m synthetic_sales_assist.portal --data-dir PATH --host 127.0.0.1 --port PORT --runtime-receipt PATH
```

No dependency download, debug server, websocket, external client, remote asset, or alternate-port
search is permitted. The bind validator accepts only `127.0.0.1`, `localhost`, and `::1`; the
default and lifecycle-script bind is `127.0.0.1`. Host-header validation remains exact.

The API contract is `synthetic-sales-assist-api/v1`. Its route and member inventories are closed,
unknown members fail before application dispatch, request bodies are bounded, and all actions call
the existing application/service and Milestone 4 repository boundaries.

The document contract is `synthetic-sales-assist-dom/v1`. Stable `data-ssa-*` attributes and one
bounded, non-executable canonical JSON payload describe the same synthetic facts. Exact identity,
count, and ordered-manifest coherence are required for `COMPLETE`; DOM/payload disagreement is
fail-closed `INCOMPLETE`, a malformed value is `MALFORMED`, and neither can be evaluated.

Every state-changing local request requires all of:

- an exact allowlisted Host header;
- an exact same-origin `Origin` header;
- a bounded CSRF token tied to the local service lease and distinct from action tokens;
- the endpoint-specific request or shutdown token where applicable.

Responses use a local-only Content Security Policy and prohibit remote script, style, font, image,
frame, object, connection, analytics, or telemetry sources.

Schema version 4 already supplies generic canonical durable-command, receipt, and owner tables, so
Milestone 5 adds no migration. A bounded application registry stores each closed scenario
instance and each evaluation attempt through that idempotency repository, including exact
success, replay, conflict, fail-closed, telemetry-operation, and recorded-time facts. Anonymous
instantiation uses a cryptographically random synthetic nonce; explicit request keys preserve
exact replay. On process open, at most 256 canonical, hash-verified records are restored and their
fixture source bindings are rebuilt and reconciled. Sales Credit and DOI histories use typed,
bounded repository/service projections that verify canonical stored material against physical
projections before the portal can render it.

An accepted Milestone 5 evaluation key first creates an immutable application binding before the
Milestone 4 service call. The first completed application operation uses a deterministic synthetic
telemetry operation ID derived from that binding command ID. Its primary `SUCCEEDED` (or terminal
`CONFLICT`) attempt and a unique `application.scenario_evaluation_resolution` receipt are then
written in the same schema-4 transaction. The resolution receipt binds the binding command,
attempt, order, outcome, and telemetry operation; later explicit replays retain their own attempt
and telemetry rows but do not replace that primary link.

Startup enumerates bounded, canonical, hash-verified evaluation bindings. A verified resolution
must name an owned attempt and a complete typed telemetry row whose alias, rule pack/version,
result partition, replay flag, and exact timings agree with the retained evaluation. A binding with
no resolution is a recoverable interrupted operation: the unchanged Milestone 4 service is called
again with the retained request key and source binding. Its idempotent receipt prevents a duplicate
business event. If the deterministic telemetry row was already committed, startup validates and
reuses it to reconstruct the exact processing view; otherwise it writes that one row. Finally it
atomically appends the primary attempt and resolution. The delegated malformed-input backend accepts
the same deterministic operation ID for application recovery while preserving its default random-ID
behavior for Milestone 4 callers; it validates and reuses an exact retained telemetry row after a
crash. Ambiguous, corrupt, unowned, or conflicting recovery material fails startup closed.
Consequently a crash after the business commit, after telemetry, or after the attempt transaction
converges to one primary linked outcome without a migration or unlinked evaluation telemetry.

Start and reset first contend on one shared lifecycle-operation mutex beneath the owned runtime
directory. Start holds that mutex from before database initialization through the child process's
passing health and ownership proof. The child acquires the service lease before it opens the
application database, then performs migration and deep startup verification while holding that
lease; this is a deliberate lock handoff with no unowned database-initialization interval. Reset
holds the same lifecycle mutex across backup, owned shutdown, exact-file deletion,
reinitialization, and deep verification. Concurrent start/start and start/reset attempts therefore
fail closed instead of racing database lifecycle work.

After owned shutdown, reset also takes the same byte-range service lease used by the direct
`python -m synthetic_sales_assist.portal` entry point and retains it through exact deletion,
reinitialization, and deep verification. This closes the direct-entry handoff window: a direct
service that wins the lease makes reset stop before deletion, while reset ownership makes the
direct service stop before database open.

One running service instance owns an exclusive sibling lock and atomically publishes a canonical
runtime receipt with schema version, PID, OS process-creation time, process identity token, host,
port, independent CSRF and shutdown tokens, database path, app version, database schema version,
and explicit build version and origin. Shutdown requires both distinct tokens plus Host/origin
validation. Windows scripts
additionally compare the exact PID, process start time, executable, readable active-lease token,
data directory, database, host, port, origin, and receipt path. When the current non-administrator
PowerShell runtime does not expose a command line without CIM/WMI, the stronger active-lease and
authenticated-shutdown proof remains authoritative. CIM/WMI access is not required. The scripts
never fall back to killing a PID or a Python process by name.

Reset requires an explicit confirmation switch. It validates the exact local data root, creates a
verified online backup when a database exists, performs an owned shutdown, removes only the known
database image/sidecars and owned runtime receipt/lock, then initializes and deeply verifies schema
version 4. Logs, backups, exports, source, Git, specifications, and unrelated files survive.
Every controlled child directory is created and then revalidated as a real local directory;
symlinks, junctions, other reparse points, and reparse leaves fail before a lock, receipt,
database, backup, or deletion operation. Non-root data paths are canonicalized without trailing
separators before Windows child-process quoting.
The runtime executable receives the same locality treatment: UNC/device/ADS, mapped-network, and
reparse paths are rejected before execution, followed by an exact application doctor check.

## Consequences

- Schema version remains `4`; Milestone 5 adds no migration.
- Instantiated scenario catalog entries and exact attempt receipts survive a service restart in
  existing canonical durable-command storage; no process-memory counter is presented as durable.
- A stale receipt is removable only when no matching process exists and the lease is not held.
- Database initialization never precedes service-lease acquisition, and destructive reset work
  never occurs outside the shared lifecycle-operation mutex.
- Reset additionally retains the service lease across its destructive interval, so the documented
  direct module entry point and scripts share one exclusion primitive.
- A live PID with any ownership mismatch is never stopped automatically.
- Static and template assets are admitted only beneath reviewed portal/static roots and carry an
  authored-Milestone-5 marker; copied HTML, manifests, dashboards, connectors, and external assets
  remain scanner failures.
- Actual user visual acceptance remains a post-commit checklist; HTTP/HTML tests do not replace it.

## Rejected alternatives

- Binding to all interfaces, LAN addresses, or an automatically selected port.
- A framework or CDN requiring installation or external retrieval.
- Unversioned or open-ended JSON dictionaries.
- Cookie-only, Host-only, or localhost-only action authorization.
- PID-only shutdown, process-name termination, administrator elevation, or recursive data deletion.
- A Chrome extension, generic automation layer, or Milestone 6 extractor.
