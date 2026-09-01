<!-- SYNTHETIC-SALES-ASSIST-AUTHORED-M6 -->
# Synthetic Sales Assist localhost side panel

This unpacked Chrome Manifest V3 extension is a DEVELOPMENT / LOCALHOST ONLY companion to
Synthetic Sales Assist. Version `0.1.1` preserves the accepted Milestone 6 extraction and
evaluation behavior and adds only Milestone 7 localhost Control Center links and truthful
last-seen registration. It is not a portable release, is not published to a store, and requires
no administrator rights.

## Security boundary

The manifest requests only the `sidePanel` permission. Its host permissions are exactly:

```text
http://127.0.0.1/*
http://localhost/*
```

The static isolated-world content script is narrower still: it is injected only under the
`/orders/*` and `/interactions/*` paths on those two hosts. The content script rejects every
scheme, host, credential-bearing URL, query string, alternate port, unrelated page kind,
contract version, non-synthetic identity, and incoherent source. The only accepted service port
is `8765`.

There is no extension storage, remote asset, remote code, cookie access, generic source-page
interaction, external action, or background network client. The service worker only validates
and relays closed messages between the panel and the active supported content script. Health,
extension handshake, and evaluation requests originate in that content script as absolute URLs
constructed only from the independently validated current loopback origin and exact closed paths.
This makes document base elements irrelevant while the M5 Host, Origin, and CSRF controls remain
authoritative. The handshake uses the existing page-scoped local CSRF value and sends only the
exact schema `synthetic-sales-assist-extension-handshake/v1` and extension version `0.1.1`.

The manifest intentionally declares no custom icon and the package contains no icon asset; Chrome
uses its generic extension presentation. This avoids an unnecessary asset surface. If a custom
icon is added later, it must be generated locally or repository-owned, included in the exact
package inventory, and covered by the remote-asset deny tests.

## Load unpacked

1. Start the local M5 service at `http://127.0.0.1:8765/` using the documented launcher.
2. Open `chrome://extensions` in Chrome.
3. Enable **Developer mode**.
4. Choose **Load unpacked** and select this `chrome_extension` directory.
5. Open a synthetic order detail page, then open the extension's side panel.

The panel performs one bounded status refresh when opened. After a supported page and healthy
backend pass validation, that open or an explicit **Refresh page status** click sends one bounded
maintenance handshake. There is no timer or hidden polling. Evaluation never runs on page load. The
**Evaluate synthetic page** button is enabled only for a COMPLETE order whose allowlisted DOM
facts, exact M5 canonical embedded payload, identities, counts, source time, and independently
recomputed ordered-line digest all agree. A separate exact three-member canonical extension
binding supplies the synthetic order identity and `SALES_CREDIT` or `DOI` source rule pack without
changing the M5 DOM-v1 payload. Its identity and rule pack must agree with the path, root, and
rendered order summary. For `COMPLETE`, the source pair
`sales-credit-m5-fixture/v1` plus `synthetic-sales-credit-domain/v1` maps only to `SALES_CREDIT`,
and `shared-fixture/v1` plus `shared-whole-order-completeness/v1` maps only to `DOI`. The malformed
pair `m5-malformed-fixture/v1` plus `synthetic-malformed-input/v1` is never COMPLETE or evaluable.
The independently mapped pack, M6 binding, and DOM marker must agree before health or evaluation.
A safe retry reuses the same bounded request key.
Each evaluation and retry is also bound to the exact displayed loopback origin, synthetic order
identity, and non-sensitive SHA-256 source fingerprint. An initially stale binding, tab switch, or
navigation fails closed before health. If source mutation arises only while the evaluation health
preflight is in flight, that one read-only `GET /health` may complete, but re-extraction always
blocks the evaluation POST.

Interaction detail pages are recognized only when all eight rendered allowlisted facts match the
exact canonical nine-member embedded interaction payload. They provide verified read-only
context; evaluation remains available only from a fully verified order detail page.

## Closed panel states

`UNSUPPORTED_PAGE`, `SUPPORTED_READY`, `INCOMPLETE_PAGE`, `MALFORMED_PAGE`,
`DOM_PAYLOAD_MISMATCH`, `BACKEND_OFFLINE`, `BACKEND_UNHEALTHY`, `EVALUATING`,
`SALES_CREDIT_RESULT`, `DOI_OPPORTUNITY`, `DOI_MANUAL_REVIEW`, `DOI_EXCLUDED`, `DOI_MONITOR`,
`EXACT_REPLAY`, `REQUEST_CONFLICT`, and `SAFE_ERROR` are the complete state inventory.

Results show the local rule pack and version, reasons, separately scoped opportunities, human
review requirement, value status, replay/conflict flags, persisted synthetic IDs, and processing
duration. Closed ordinary loopback links can open the Control Center overview, current order,
validated current case/evaluation, domain-aware review queue, and system health. These links use
only reserved synthetic IDs already validated by the closed panel contract; they carry no token,
credential, source payload, or arbitrary destination. No external action button exists.

## Deterministic package

From the repository root in PowerShell, using the verified development interpreter:

```powershell
& $env:SSA_PYTHON tools/package_milestone6_extension.py --check
& $env:SSA_PYTHON tools/package_milestone6_extension.py --output-dir (Join-Path $env:LOCALAPPDATA 'SyntheticSalesAssist\exports')
```

The second command writes the deterministic ZIP, its SHA-256 checksum, and its exact file/hash
inventory outside the repository. It stages and verifies the complete trio, then atomically
publishes a digest-named generation directory; a failed generation does not replace a prior
complete generation. The ZIP contains only the checked-in unpacked extension files. It never
contains tests, caches, source maps, or packaging code.

The packager is an offline, same-tree developer tool. It accepts only regular, single-link,
non-reparse source files, snapshots each through a checked file descriptor, and writes through an
exclusive random staging directory with identity checks and `fsync` before one directory rename.
Run it only from the clean candidate tree under the same local user that owns that tree, and
reproduce the ZIP hash twice. It does not claim to isolate packaging from a hostile same-user
process that can replace directory entries in the remaining interval inside an operating-system
filesystem call.

## Reload, update, and uninstall

- After a development edit or version update, use **Reload** on `chrome://extensions`, then
  refresh the supported localhost page and the panel.
- To update from a committed package, remove the old unpacked directory selection and load the
  verified replacement directory.
- To uninstall, choose **Remove** on `chrome://extensions`. No extension storage or source data
  remains because this extension does not persist any.

## Troubleshooting

- **Unsupported page:** open an exact synthetic order or interaction detail URL on port `8765`.
- **Backend offline:** start the local service, then use **Refresh page status**.
- **Backend unhealthy:** inspect the local portal status; evaluation stays blocked until health
  and all nine safety counters pass.
- **DOM and payload disagree / incomplete / malformed:** return to the scenario library and
  instantiate a COMPLETE synthetic scenario. The extension intentionally cannot override these
  conditions.
- **Request conflict:** choose a new bounded key only for genuinely new request material. For an
  uncertain timeout, use **Safe retry with same key** so exact replay semantics protect the result.
