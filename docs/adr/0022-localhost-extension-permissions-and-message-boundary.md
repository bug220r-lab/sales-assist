# ADR 0022: Localhost extension permissions and closed message boundary

- Status: Accepted
- Date: 2026-08-31
- Decision scope: Milestone 6 localhost Chrome extension only

## Context

Milestone 6 adds a read-only Chrome Manifest V3 observer and side panel to the accepted Milestone 5
synthetic portal. The browser boundary must recognize only governed synthetic pages, independently
check the DOM against the embedded canonical payload, and explicitly request an existing local
evaluation without creating browser automation, general navigation, external fetch, credential
access, or production capability.

Chrome host permissions alone do not prove that a localhost page belongs to this application.
Conversely, allowing an extension-origin request at the service would weaken the accepted M5
same-origin and CSRF boundary. The manifest, content-script admission checks, message schemas, and
request execution location therefore form one security decision.

## Decision

Ship one unpacked Manifest V3 extension at version `0.1.0`. Its permission arrays are exhaustive:

```json
{
  "permissions": ["sidePanel"],
  "host_permissions": [
    "http://127.0.0.1/*",
    "http://localhost/*"
  ]
}
```

There is no `optional_permissions` or `optional_host_permissions` expansion. The extension does
not request `storage`, `tabs`, `activeTab`, `scripting`, `cookies`, `webRequest`,
`webRequestBlocking`, `nativeMessaging`, `debugger`, `downloads`, `clipboardWrite`, or any
permission not displayed above. It uses no action permission and has no broad internet match.

The side-panel document is repository-owned and contains no inline script or event handler.
Extension pages use exactly:

```text
default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'none'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'
```

All scripts and styles are static repository files packaged by the deterministic inventory tool.
There is no remote code, dynamic script creation, `eval`, `new Function`, WebAssembly, CDN, remote
font, analytics, telemetry, source map, or external asset.

The manifest intentionally has no custom icon entry and the package has no icon asset; Chrome's
generic extension presentation is sufficient for this unpacked development build. The
local/generated icon rule is a provenance constraint if an icon is later introduced, without
adding an otherwise unnecessary asset surface now. Any later custom icon must be generated
locally or repository-owned, inventoried, and covered by the static asset tests.

## Package snapshot and local filesystem boundary

Packaging is an offline operation against one clean same-tree candidate owned by the development
user. Each source member must be a regular, single-link, non-reparse file under a non-reparse
extension ancestry. The packager compares pre-open, descriptor, post-read, and post-close identity
and metadata before using the captured bytes. Output is outside the repository. The complete ZIP,
inventory, and checksum trio is written with exclusive unpredictable temporary files, descriptor
writes, `fsync`, and ancestry/target revalidation inside one owned staging directory. Only after
all three exact bytes validate is that directory atomically renamed to its digest-bound generation
name. A failed generation leaves every prior complete generation untouched. A second build must
reproduce the same ZIP SHA-256.

This boundary rejects ordinary symlink, hardlink, reparse, swap, and predictable-temporary attacks.
It is not a security boundary against a malicious process running as the same local user that can
replace directory entries within the remaining syscall-granularity interval. The release procedure
therefore requires an offline clean candidate tree, no concurrent same-user writer, and the repeated
same-tree digest check; it makes no portable-build or hostile-build-host claim.

A static isolated-world content script is declared only for these four page-path match patterns:

```text
http://127.0.0.1/orders/*
http://127.0.0.1/interactions/*
http://localhost/orders/*
http://localhost/interactions/*
```

That match is necessary but not sufficient admission. Before returning supported data, the script
requires:

1. scheme exactly `http`;
2. hostname exactly `127.0.0.1` or `localhost`;
3. port exactly `8765` under the committed local-origin contract;
4. no credentials, query-derived origin, or alternate authority;
5. an exact allowlisted `data-ssa-page-kind`;
6. exact DOM, API/application, and synthetic-identity contracts for that page kind; and
7. successful independent completeness/coherence verification where evaluation requires an order
   representation.

An unrelated page on an allowed localhost origin therefore remains `UNSUPPORTED_PAGE`; origin
permission never converts arbitrary DOM into a supported source.

The portal compatibility change is renderer-only. Order detail labels its existing summary,
completeness, and line-universe sections with exact `data-ssa-section` markers and publishes the
flat governed rule-pack marker. The exact seven-member M5 canonical order payload remains
byte-compatible under `synthetic-sales-assist-dom/v1`. A separate root-scoped canonical payload,
`synthetic-sales-assist-extension-order-binding/v1`, contains exactly the order ID, rule pack, and
its own schema version. The binding order ID must equal the path, root, M5 payload, and DOM marker;
the binding rule pack must equal the DOM marker and an independent exact source-version mapping.
`sales-credit-m5-fixture/v1` plus `synthetic-sales-credit-domain/v1` maps only to `SALES_CREDIT`,
while `shared-fixture/v1` plus `shared-whole-order-completeness/v1` maps only to `DOI`.
`m5-malformed-fixture/v1` plus `synthetic-malformed-input/v1` is never admitted as `COMPLETE` or
evaluable. This avoids same-version unknown-member drift in the closed M5 payload without claiming
that its exact seven members directly carry `rule_pack`.
Interaction detail
publishes its existing closed nine-member application view as canonical `data-ssa-field` values
plus a non-executable canonical JSON payload, labels its summary section, and binds the root to the
existing synthetic order ID. No route, request, business rule, source fact,
persistence model, database schema, or lifecycle behavior changes.

The side panel sends only closed, versioned commands. An evaluation command binds the exact
panel-observed loopback origin, synthetic order identity, and SHA-256 fingerprint of the canonical
closed extraction; page-state commands carry null bindings. The service worker validates each
message, finds the active tab without reading its URL/title/history, and relays the message to the
already installed static content script. The content script re-extracts and compares that binding
before health or POST, so switching the active tab cannot make a stale panel evaluate a different
order. It has no general click, type, fill, keypress, submit, execute script, arbitrary URL, or
arbitrary message forwarding operation. Replies are also closed and versioned. Unknown members,
message types, states, versions, or oversized values fail closed.

All network I/O remains in the validated content script and uses an exact closed path joined to the
independently validated current page origin:

- one `GET /health` when the panel refreshes or opens the supported page state;
- one additional `GET /health` preflight after an explicit evaluation click; and
- one extension Fetch API invocation for
  `POST /api/v1/orders/{synthetic_order_id}/evaluate` after that preflight passes.

These event-bound reads are not polling. There is no timer, hidden loop, or repeated health fetch.
After an ambiguous pre-response socket failure, Chrome may retransmit the same byte-identical POST
and request key at the transport layer. M5 exact replay makes that retry idempotent; the extension
does not make a second Fetch API invocation and does not promise that the server observes only one
transport attempt.

The content script obtains `meta[name="ssa-csrf-token"]` only at POST time and supplies it to the
accepted M5 `X-SSA-CSRF-Token` check. It never places the token in an extraction result, message,
log, diagnostic, or persistent store. The service worker never fetches. No M5 Origin, Host, CSRF,
body, route, or response-validation rule is relaxed, and no route is added for the extension.
Under the committed M5 lease contract (ADR 0021), this value is a per-process localhost
anti-forgery nonce exposed on every rendered local page and is distinct from shutdown/action
tokens; it is not a user identity, browser session, cookie, or production credential. The fetch
uses `credentials: "omit"`, and the nonce is sent only back to its exact
`http://127.0.0.1:8765` or normalized `localhost:8765` origin after the explicit evaluation click.

Extension storage is deliberately unused. Source payloads, evaluation responses, fictional
contacts, tokens, cookies, database data, and last-viewed identifiers are not persisted. A fresh
panel re-derives its view from the active supported tab and local backend.

The extension displays local results and local links only. It cannot mutate source facts, invoke a
human or external action, interact with source controls, access credentials/session data, or open
a production destination. The future-dashboard link remains unavailable because Milestone 7 is
not authorized and no such M5/M6 route exists.

## Consequences

- Chrome presents only the side-panel permission and two exact localhost host permissions.
- Installation works unpacked without administrator rights, store publication, or dependency
  download.
- The extension does not evaluate on page load and does not poll invisibly. A panel refresh/open
  makes one bounded health read; an explicit evaluation makes one additional health preflight and,
  only when it passes, one evaluation Fetch API invocation. A browser-level retransmission after
  an ambiguous transport failure retains the exact body and idempotency key.
- Origin-bound absolute request targets preserve the accepted service Origin/CSRF model and cannot
  be retargeted by document `<base>` state. Extension-origin API access is neither needed nor
  allowed.
- The static host match cannot expose unrelated localhost pages because page kind, versions,
  identities, structure, and coherence are independently admitted.
- No extension state survives reload or uninstall.
- Any future permission, host, page kind, port, storage field, message type, API route, or remote
  asset requires a new explicit decision and exhaustive test update.

## Rejected alternatives

- `<all_urls>`, wildcard internet hosts, HTTPS fallbacks, LAN hosts, arbitrary ports, URL-configured
  fetch, or optional host expansion.
- `tabs`, `activeTab`, `scripting`, generic DOM automation, programmatic injection, or broad action
  helpers.
- Service-worker API fetch, an extension-Origin exception, disabling CSRF, or passing the CSRF token
  through extension messages.
- Blind trust in the embedded payload, arbitrary text/`innerHTML` extraction, unrestricted notes,
  browser storage, cookies, or query strings.
- Remote code/assets, a framework or dependency download, store publication, native messaging, or
  administrator installation.
- A dashboard/control center, production connector, external action, or any Milestone 7 artifact.
