# Milestone 6 manual Chrome acceptance

Automated DOM, contract, security, and integration tests do not replace this user-visible Chrome
check. Use only reserved synthetic scenarios, an isolated local data directory, and the accepted
loopback service. Do not connect the extension to a production or company system. Do not publish it
to a store.

The exact extension JavaScript has separately passed the automated in-app Chromium session in
`docs/acceptance/milestone6-browser-evidence.md`. That report is runtime evidence for extraction,
transport faults, response validation, and all panel states; it does not claim that this
load-unpacked/reload/uninstall checklist has been performed by the user.

Record the candidate commit/tree, Chrome version, extension version, package/inventory SHA-256,
Python source, isolated data directory, origin, API/request/DOM/application/build/runtime-receipt
versions, and final test counts with the acceptance notes.

## Start an isolated local service

From the repository root in PowerShell:

```powershell
$m6DataRoot = Join-Path $env:LOCALAPPDATA `
  ('SyntheticSalesAssist-m6-acceptance-' + [Guid]::NewGuid().ToString('N'))
$m6Port = 8765

# DEVELOPMENT / NONPORTABLE -- this workspace only
$localAppData = [Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)
$profileRoot = [IO.Directory]::GetParent($localAppData).Parent.FullName
$env:SSA_PYTHON = Join-Path $profileRoot `
  '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'

.\scripts\start.ps1 -DataDir $m6DataRoot -Port $m6Port -NoBrowser
.\scripts\status.ps1 -DataDir $m6DataRoot
Start-Process 'http://127.0.0.1:8765/scenarios'
```

- [ ] Start labels the fallback `DEVELOPMENT / NONPORTABLE` and makes no portable-release claim.
- [ ] Status reports `RUNNING`, origin `http://127.0.0.1:8765`, schema 4, passing health,
      application `0.1.0`, build `synthetic-sales-assist-m5/v1`, and all nine counters zero.
- [ ] The listener is only `127.0.0.1:8765`; no LAN or external listener exists.

## Load unpacked and inspect permissions

1. Open `chrome://extensions` in Chrome.
2. Enable **Developer mode**.
3. Choose **Load unpacked**.
4. Select the repository's `chrome_extension` directory, not a parent directory and not a ZIP.
5. Record extension version `0.1.0` and use **Details** to inspect site access/permissions.
6. Open Chrome's side-panel picker and choose **Synthetic Sales Assist Local Side Panel**.

- [ ] Chrome shows Manifest V3 and no install error.
- [ ] API permissions contain only `sidePanel`.
- [ ] Host permissions contain only `http://127.0.0.1/*` and `http://localhost/*`.
- [ ] Static content-script matches are limited to the `/orders/*` and `/interactions/*` paths on
      those two hosts.
- [ ] There is no incognito enablement, file-URL access, optional permission, broad site access,
      external connection, or administrator prompt.
- [ ] The extension contains only local repository-owned scripts and CSS; it loads no remote
      asset.

Before or after the unpacked check, validate and package the exact candidate outside the
repository:

```powershell
& $env:SSA_PYTHON tools/package_milestone6_extension.py --check
$m6Exports = Join-Path $env:LOCALAPPDATA 'SyntheticSalesAssist\exports'
& $env:SSA_PYTHON tools/package_milestone6_extension.py --output-dir $m6Exports
```

- [ ] The check prints `M6_EXTENSION_PACKAGE_CHECK = PASS`.
- [ ] Packaging prints `M6_EXTENSION_PACKAGE = PASS`, the ZIP path, exact SHA-256, inventory path,
      and checksum path.
- [ ] The ZIP is named `synthetic-sales-assist-m6-extension-0.1.0.zip`, is outside the repository,
      and contains exactly the checked source inventory. It, its inventory, and its checksum are
      together in the printed digest-named generation directory.
- [ ] Repeating the same-tree package command produces the same ZIP SHA-256.
- [ ] A deliberately failed later package run does not alter a prior complete generation.

## Supported-page recognition

Use the portal scenario library to instantiate a normal synthetic scenario, then open its order
detail page.

- [ ] `/orders/{SYN-ORDER-*}` displays `SUPPORTED_READY`, the exact synthetic order identity,
      `COMPLETE`, the scenario alias, and passing backend health.
- [ ] The panel does not evaluate on navigation, page load, refresh, or panel open.
- [ ] The Evaluate control is enabled only for the verified complete order and is keyboard
      operable there; it remains disabled in every other state.
- [ ] An exact `/interactions/{SYN-INTERACTION-*}` page displays the bounded fictional interaction
      identity and associated synthetic order, with Evaluate disabled.
- [ ] The interaction's local order link opens that exact order; it does not generically navigate
      or interact with source controls.
- [ ] `/scenarios`, `/orders`, `/runs/{SYN-RUN-*}`, `/health`, and an unrelated localhost page are
      not treated as an evaluation source.
- [ ] A wrong path/ID, wrong DOM version, duplicate governed root, or unsupported page kind is
      `UNSUPPORTED_PAGE` or a closed safe error; its always-visible Evaluate control is disabled
      and non-actionable.

## Completeness, mismatch, and extraction

Instantiate the deliberate fixture modes from the scenario page and open each generated order.
Do not edit the application database or protected specifications.

- [ ] Normal, large, explicit zero-line, and observed-UNKNOWN complete orders remain coherent;
      every rendered line is accounted for and observed `UNKNOWN` remains explicit.
- [ ] `missing-required-section`, `identity-mismatch`, `duplicate-line`, and
      `declared-rendered-mismatch` display `INCOMPLETE_PAGE` and cannot evaluate.
- [ ] `malformed-value` displays `MALFORMED_PAGE` and cannot evaluate.
- [ ] `stale-source-changed` and `dom-payload-mismatch` display `DOM_PAYLOAD_MISMATCH` and cannot
      evaluate.
- [ ] A wrong contract version is rejected; no silent downgrade occurs.
- [ ] Browser inspection confirms the panel never displays/transfers arbitrary page text,
      `innerHTML`, unrestricted notes, script source, query strings, hidden unrelated DOM, paths,
      cookies, storage, or CSRF/control tokens.
- [ ] Refreshing each blocked page makes no successful evaluation request and creates no successful
      persisted evaluation in the portal history.

## Sales Credit and DOI results

For each row, instantiate the named alias in complete mode, open the order, enter a bounded
synthetic request key if the panel offers one, and make exactly one explicit Evaluate click.

| Alias | Required panel/result evidence |
|---|---|
| `sales-credit-target-rep` | `SALES_CREDIT_RESULT`, target-rep workflow, reasons, no false human-review flag |
| `sales-credit-human-review` | `SALES_CREDIT_RESULT`, manual-review workflow, human review required |
| `doi-fulfillment-split` | `DOI_OPPORTUNITY`, separate opportunity scope and available value status |
| `doi-manual-review` | `DOI_MANUAL_REVIEW`, reasons and human review required |
| `doi-full-ds` | `DOI_EXCLUDED`, closed reasons and no external action |
| `doi-dedupe-review` | `DOI_MONITOR`, monitor workflow and closed reasons |

- [ ] Every result shows rule pack/version, workflow/top-level result, closed reasons, separately
      scoped opportunities, human-review requirement, value status, persisted synthetic IDs, and
      processing duration where applicable.
- [ ] The history link stays on the exact local service origin and shows the persisted result.
- [ ] The future-dashboard label is unavailable/noninteractive; no dashboard or control-center
      route has been added.
- [ ] No external action, generic click/type/fill/keyboard/submit, production connector, or source
      mutation control exists.

## Replay, conflict, timeout, and backend lifecycle

- [ ] Repeat a safe retry with the exact same request key and unchanged order material. The panel
      displays `EXACT_REPLAY`, the durable result identity is unchanged, and history records replay
      without a duplicate business event.
- [ ] Bind one request key, then deliberately reuse it for different synthetic scenario material.
      The panel displays `REQUEST_CONFLICT`; the original result is unchanged.
- [ ] While a request is in flight, the panel displays `EVALUATING` and prevents a duplicate click.
- [ ] Stop only the owned service with
      `.\scripts\stop.ps1 -DataDir $m6DataRoot`; refresh the panel and confirm `BACKEND_OFFLINE`
      with evaluation disabled.
- [ ] Restart the same isolated root, refresh the page/panel, and confirm `SUPPORTED_READY` plus
      the previously persisted history.
- [ ] Run the named deterministic panel/API evidence in
      `tests.test_milestone6_extension.Milestone6StaticExtensionTests.test_offline_unhealthy_timeout_retry_and_history_paths_are_reachable`
      and confirm a reachable nonpassing health envelope maps to `BACKEND_UNHEALTHY`, never ready.
- [ ] Review the real-browser delayed-response evidence in
      `docs/acceptance/milestone6-browser-evidence.md`: its loopback controller delayed POST beyond
      the 10,000 ms deadline, produced `SAFE_ERROR` / `REQUEST_TIMEOUT`, and proved same-key retry.
- [ ] Review the same report's actual unknown-409 and extra-member relay canaries, plus
      `backend-evaluation-failure`; each displays `SAFE_ERROR` without exception text, path, token,
      or source material. No nonexistent portal fixture is assumed.

## Closed 16-state inventory

Record direct manual observation or the named deterministic fixture evidence for every state:

- [ ] `UNSUPPORTED_PAGE`
- [ ] `SUPPORTED_READY`
- [ ] `INCOMPLETE_PAGE`
- [ ] `MALFORMED_PAGE`
- [ ] `DOM_PAYLOAD_MISMATCH`
- [ ] `BACKEND_OFFLINE`
- [ ] `BACKEND_UNHEALTHY`
- [ ] `EVALUATING`
- [ ] `SALES_CREDIT_RESULT`
- [ ] `DOI_OPPORTUNITY`
- [ ] `DOI_MANUAL_REVIEW`
- [ ] `DOI_EXCLUDED`
- [ ] `DOI_MONITOR`
- [ ] `EXACT_REPLAY`
- [ ] `REQUEST_CONFLICT`
- [ ] `SAFE_ERROR`

No other displayed state is accepted.

## Browser network proof

1. Open DevTools on the supported portal tab and select **Network**. Preserve the log and clear it.
2. Inspect the extension service worker from `chrome://extensions` and keep its console/network
   view open.
3. Refresh the panel, run one evaluation, follow the local history link, then refresh once.
4. Export or screenshot the filtered request inventory without exposing the CSRF header value.

- [ ] The only extension-initiated read is an origin-bound `GET http://127.0.0.1:8765/health` (or the
      exact `localhost:8765` equivalent for a page already using that allowed origin).
- [ ] The only extension-initiated action is the explicit origin-bound
      `POST /api/v1/orders/{SYN-ORDER-*}/evaluate`.
- [ ] A hostile or accidental document `<base>` does not change either request target.
- [ ] The service worker makes zero network requests.
- [ ] There are zero requests to an external host, alternate port, HTTPS origin, websocket,
      analytics endpoint, telemetry endpoint, source map, remote font, or remote asset.
- [ ] No request contains credentials-in-URL, a query-derived origin, source payload, unrestricted
      note, fictional contact value, cookie, database data, credential/session token, or source
      control token. The sole permitted exception is the exact ephemeral same-document 64-hex
      CSRF lease nonce required by the committed M5 API; it is never messaged, logged, or stored by
      the extension.
- [ ] Final local status still reports all nine safety counters zero and runtime external network
      count zero.

## Reload, update, and uninstall

- [ ] On `chrome://extensions`, choose **Reload**, then reload the supported portal tab so the
      static content script is reinstalled. Reopen the panel and repeat readiness/evaluation.
- [ ] Loading a deterministically repackaged identical tree does not add a permission prompt or
      change the inventory SHA-256.
- [ ] Choose **Remove** and confirm. The side panel disappears without an administrator prompt.
- [ ] The isolated local service/database and persisted synthetic history remain unchanged after
      extension removal.
- [ ] Re-loading unpacked restores only extension code; no source payload or prior panel preference
      is restored because extension storage is unused.

## Troubleshooting

- `UNSUPPORTED_PAGE`: use an exact order or interaction detail path on port 8765; reload the page
  after loading/reloading the extension; verify the DOM version and synthetic path identity.
- `BACKEND_OFFLINE`: run `status.ps1`; start the exact isolated data root; do not change ports or
  broaden host permissions.
- `BACKEND_UNHEALTHY`: inspect `/health`, schema/application/build versions, database verification,
  and the nine safety counters. Do not bypass the check.
- `INCOMPLETE_PAGE`, `MALFORMED_PAGE`, or `DOM_PAYLOAD_MISMATCH`: use a complete synthetic fixture
  or correct the renderer in source and rerun gates. Do not edit DOM in DevTools to force ready.
- After extension reload: reload the portal tab because an existing tab retains the old content
  script until navigation/reload.
- If Chrome rejects the extension: select the unpacked `chrome_extension` directory and inspect the
  manifest error. Do not download a dependency or loosen the manifest.

After the final stop, verify the owned PID is gone and retain only privacy-safe notes/screenshots:

```powershell
.\scripts\stop.ps1 -DataDir $m6DataRoot
Remove-Item Env:SSA_PYTHON
```

Record the result only after every applicable item and deterministic fixture review passes:

```text
M6_AUTOMATED_BROWSER_EVIDENCE = PASS
M6_MANUAL_ACCEPTANCE = PENDING
```
