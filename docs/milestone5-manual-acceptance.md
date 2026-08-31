# Milestone 5 manual acceptance record

Automated test success does not replace this user-run visual and lifecycle acceptance.

The checklist below was completed against launcher-remediation commit
`28909059cc1ef8a77e3a4bf428782dbf0280d7c4`, tree
`27ec8ddccb4d2428af5a6b92d5420f1bbb1a18e7`. The user later supplied the authoritative manual
result in the Milestone 6 authorization. This manual event is separate from the earlier automated
operator report: that report correctly recorded `manual_acceptance_declared: false` because the
manual declaration did not yet exist when the report was finalized. See
`docs/acceptance/milestone5-acceptance.md` for the checksum-bound evidence lineage.

Use a new absolute local data directory containing only synthetic test state. Record the commit,
tree, Python path, data directory, selected port, app version, API/DOM versions, and schema version
in the acceptance notes. Do not use the default application-data database for testing.

For the current Codex workspace, prepare one isolated acceptance session as follows:

```powershell
$acceptanceDataRoot = Join-Path $env:LOCALAPPDATA `
  ('SyntheticSalesAssist-m5-acceptance-' + [Guid]::NewGuid().ToString('N'))
$acceptancePort = 8765
# DEVELOPMENT / NONPORTABLE -- this workspace only
$localAppData = [Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)
$profileRoot = [IO.Directory]::GetParent($localAppData).Parent.FullName
$env:SSA_PYTHON = Join-Path $profileRoot `
  '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
```

Record the interpreter source as `DEVELOPMENT / NONPORTABLE (explicit SSA_PYTHON)`. Keep the
variable set for every lifecycle command in this session. This fallback is not a portable release.

## Lifecycle

- [x] `.\scripts\start.ps1 -DataDir $acceptanceDataRoot -Port $acceptancePort -NoBrowser`
      starts one hidden, non-admin process on `127.0.0.1` only and prints the expected
      `DEVELOPMENT / NONPORTABLE` fallback label.
- [x] A second start is rejected and does not affect the first process.
- [x] `.\scripts\status.ps1 -DataDir $acceptanceDataRoot` reports the exact owned PID, origin,
      app/schema versions, database path/size, nine zero safety counters, and passing health.
- [x] `/scenarios` opens when `-NoBrowser` is omitted.
- [x] `.\scripts\stop.ps1 -DataDir $acceptanceDataRoot` gracefully stops only the owned process.
- [x] A stale or altered receipt cannot terminate an unrelated process.
- [x] An arbitrary reparse-point runtime remains rejected, and the exact Codex runtime receives
      its ancestor-reparse exception only through `SSA_PYTHON`, never through `-PythonPath`.

## Portal and scenarios

- [x] The synthetic/localhost banner is visible and keyboard focus is visible.
- [x] All seven required aliases can be instantiated and show their expected high-level result.
- [x] Long complete, zero-line complete, cancellation/replacement, direct-ship, partial-quantity,
      unknown-containment, overlap, DEDUPE, incomplete, and malformed modes are distinguishable.
- [x] Long orders render every line without virtualization or hidden extraction rows.
- [x] Interaction detail contains only the bounded fictional evidence fields.
- [x] Complete pages show coherent ID, count, ordered manifest, timestamp, and DOM/payload facts.
- [x] Malformed and DOM/payload mismatch modes fail closed and cannot be evaluated.

## Evaluation and persistence

- [x] Evaluate shows result, reasons, explanation, human-review state, scoped opportunities,
      aggregate availability, persisted IDs, and trusted duration.
- [x] Reusing the exact request key shows replay; changed material shows conflict.
- [x] Refresh preserves the instantiated record, evaluation, and privacy-safe history.
- [x] A stop/start cycle restores the same bounded order catalog, evaluation, exact
      replay/conflict attempt receipts, and telemetry linkage; a new anonymous instantiation gets
      a fresh synthetic identity.
- [x] Unknown values remain explicit; overlap opportunities remain separate.
- [x] Database health and metrics pages show schema version 4 and nine zero counters.

## Security and boundary

- [x] Non-loopback Host/origin requests fail; localhost navigation succeeds.
- [x] No remote font, script, style, image, analytics, telemetry, websocket, or source map loads.
- [x] Response headers include the documented local CSP and other security headers.
- [x] No Chrome extension/manifest or dashboard/control-center route exists in the accepted M5 tree.
- [x] Browser developer tools show zero external network requests.

## Reset

- [x] Reset without `-ConfirmReset` makes no change.
- [x] Confirmed reset creates a verified backup, performs an owned stop, reinitializes schema 4,
      and passes deep verification.
- [x] Logs, backups, exports, source, Git, specifications, and an unrelated sentinel file survive.

Record the result only after every item has been personally checked:

```text
M5_MANUAL_ACCEPTANCE = PASS
```
