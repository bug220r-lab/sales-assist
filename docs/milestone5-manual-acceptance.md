# Milestone 5 manual acceptance checklist

Automated test success does not replace this user-run visual and lifecycle acceptance.

Use a new absolute local data directory containing only synthetic test state. Record the commit,
tree, Python path, data directory, selected port, app version, API/DOM versions, and schema version
in the acceptance notes. Do not use the default application-data database for testing.

## Lifecycle

- [ ] `start.ps1 -NoBrowser` starts one hidden, non-admin process on `127.0.0.1` only.
- [ ] A second start is rejected and does not affect the first process.
- [ ] `status.ps1` reports the exact owned PID, origin, app/schema versions, database path/size,
      nine zero safety counters, and passing health.
- [ ] `/scenarios` opens when `-NoBrowser` is omitted.
- [ ] `stop.ps1` gracefully stops only the owned process.
- [ ] A stale or altered receipt cannot terminate an unrelated process.

## Portal and scenarios

- [ ] The synthetic/localhost banner is visible and keyboard focus is visible.
- [ ] All seven required aliases can be instantiated and show their expected high-level result.
- [ ] Long complete, zero-line complete, cancellation/replacement, direct-ship, partial-quantity,
      unknown-containment, overlap, DEDUPE, incomplete, and malformed modes are distinguishable.
- [ ] Long orders render every line without virtualization or hidden extraction rows.
- [ ] Interaction detail contains only the bounded fictional evidence fields.
- [ ] Complete pages show coherent ID, count, ordered manifest, timestamp, and DOM/payload facts.
- [ ] Malformed and DOM/payload mismatch modes fail closed and cannot be evaluated.

## Evaluation and persistence

- [ ] Evaluate shows result, reasons, explanation, human-review state, scoped opportunities,
      aggregate availability, persisted IDs, and trusted duration.
- [ ] Reusing the exact request key shows replay; changed material shows conflict.
- [ ] Refresh preserves the instantiated record, evaluation, and privacy-safe history.
- [ ] A stop/start cycle restores the same bounded order catalog, evaluation, exact
      replay/conflict attempt receipts, and telemetry linkage; a new anonymous instantiation gets
      a fresh synthetic identity.
- [ ] Unknown values remain explicit; overlap opportunities remain separate.
- [ ] Database health and metrics pages show schema version 4 and nine zero counters.

## Security and boundary

- [ ] Non-loopback Host/origin requests fail; localhost navigation succeeds.
- [ ] No remote font, script, style, image, analytics, telemetry, websocket, or source map loads.
- [ ] Response headers include the documented local CSP and other security headers.
- [ ] No Chrome extension/manifest or dashboard/control-center route exists.
- [ ] Browser developer tools show zero external network requests.

## Reset

- [ ] Reset without `-ConfirmReset` makes no change.
- [ ] Confirmed reset creates a verified backup, performs an owned stop, reinitializes schema 4,
      and passes deep verification.
- [ ] Logs, backups, exports, source, Git, specifications, and an unrelated sentinel file survive.

Record the result only after every item has been personally checked:

```text
M5_MANUAL_ACCEPTANCE = PENDING
```
