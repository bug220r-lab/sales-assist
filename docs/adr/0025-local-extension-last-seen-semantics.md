# ADR 0025: Local extension last-seen semantics

- Status: Accepted
- Date: 2026-09-01
- Decision scope: Milestone 7 extension health and deep links

## Context

The dashboard must not equate a repository package with a browser installation. It may receive a
minimal local extension handshake and offer ordinary loopback deep links, but cannot add a Chrome
permission, persist source payloads, poll, or make the dashboard depend on extension presence.

## Decision

The dashboard exposes exactly five extension states:

```text
EXPECTED_PACKAGE_ONLY
LAST_SEEN_HEALTHY
LAST_SEEN_STALE
VERSION_MISMATCH
UNKNOWN
```

Expected version and deterministic ZIP SHA-256 describe package bytes only. In a configured
development repository with no observed handshake, the state is `EXPECTED_PACKAGE_ONLY`; when
expected package identity is unavailable it is `UNKNOWN`. A process-local record of a closed
loopback handshake becomes `LAST_SEEN_HEALTHY` for 300 seconds, then `LAST_SEEN_STALE`. A received
version different from the expected version is `VERSION_MISMATCH` regardless of freshness.
Process restart deliberately forgets last-seen state and returns to package-only semantics. No
database migration, cookie, browser storage, identity, or installation claim is introduced.

The extension sends at most one handshake after a successful explicit panel-open/refresh page-state
health event. It does not use a timer or hidden polling. The request is same-origin, CSRF-protected,
credentials-omitting, closed, and contains only its contract and extension versions. The response
reports expected/observed version, canonical last-seen time, state, and stale threshold.

Dashboard deep links are ordinary validated `http://127.0.0.1:8765` or normalized
`http://localhost:8765` GET links composed from closed route kinds and reserved synthetic IDs. The
extension uses static anchors; it gains no `tabs` permission or arbitrary-URL operation. Missing
destinations fail safely in the local dashboard.

## Consequences

- Package presence never claims installed or running.
- Last-seen status is truthful within the owned service lifetime and visibly timestamped.
- The extension and dashboard still work independently.
- Extension byte changes require a version bump, deterministic package rebuild, and complete
  permission/current-byte regression.

## Rejected alternatives

- Calling package presence `installed` or `healthy`.
- Persistent browser identifiers, extension storage, cookies, or a database heartbeat table.
- Repeated polling, external telemetry, remote update checks, or new Chrome permissions.
- Arbitrary destination URLs or programmatic generic tab control.
