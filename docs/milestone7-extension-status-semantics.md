# Milestone 7 extension status semantics

- Contract: `synthetic-sales-assist-extension-status/v1`
- Handshake: `synthetic-sales-assist-extension-handshake/v1`
- Stale threshold: 300 seconds
- Authority: ADR 0025

| State | Exact meaning |
|---|---|
| `EXPECTED_PACKAGE_ONLY` | A deterministic expected package identity is configured, but this owned service process has received no extension handshake. It does not mean installed or running. |
| `LAST_SEEN_HEALTHY` | A matching-version handshake was received no more than 300 seconds ago. |
| `LAST_SEEN_STALE` | A matching-version handshake was received more than 300 seconds ago. |
| `VERSION_MISMATCH` | The latest observed extension version differs from the expected package version. |
| `UNKNOWN` | Neither a usable expected package identity nor an accepted current-process handshake establishes a more precise state. |

The last-seen record is process-local and contains only observed version and canonical timestamp.
Restart returns to package-only or unknown semantics. The dashboard works with every state.

The event-bound handshake occurs only after a successful panel-open or explicit-refresh page-state
health check. There is no timer, hidden polling, cookie, browser storage, database record, external
request, user identity, or installation claim. It uses the accepted same-origin Host/Origin/CSRF
boundary and `credentials: "omit"`.

Deep links are static anchors to a closed route assembled from an independently validated loopback
origin and reserved synthetic identifier. They introduce no new Chrome permission and cannot carry
credentials, tokens, arbitrary query material, or a non-loopback destination.
