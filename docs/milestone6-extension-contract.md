# Milestone 6 localhost extension contract

## Frozen versions and scope

| Item | Exact value |
|---|---|
| Extension | `0.1.0` |
| Manifest | `3` |
| Minimum Chrome version | `114` |
| Extension extraction | `synthetic-sales-assist-extension-extraction/v1` |
| Extension message | `synthetic-sales-assist-extension-message/v1` |
| API envelope | `synthetic-sales-assist-api/v1` |
| API request | `synthetic-sales-assist-api-request/v1` |
| DOM | `synthetic-sales-assist-dom/v1` |
| Application view | `synthetic-sales-assist-application/v1` |
| Application/build | `0.1.0` / `synthetic-sales-assist-m5/v1` |
| Runtime receipt | `synthetic-sales-assist-runtime-receipt/v1` |
| Sales Credit rule pack | `synthetic-sales-credit-rules/v1` |
| DOI rule pack | `synthetic-doi-rule-pack/v1` |
| Service port | `8765` only |

This extension is a synthetic-only, read-only browser observer and local-evaluation panel. It does
not compute or re-evaluate Sales Credit or DOI business outcomes; it validates selected committed
output vocabularies and model/display invariants before rendering the M5 result. It neither mutates
source facts nor performs a human, commercial, production, or external-system action. It adds no
database schema or API route and does not begin Milestone 7.

## Origin and page admission

The only admitted service origins are `http://127.0.0.1:8765` and
`http://localhost:8765`. The normalizer requires scheme `http`, one of those two exact hostnames,
explicit port `8765`, empty credentials, and no query or fragment in a configured origin. It
rejects HTTPS, other loopback spellings or addresses, LAN names/addresses, default or alternate
ports, user information, UNC/device syntax, network-path references, and query-injected origins.

The content script can be statically present at either manifest-approved host, but returns
`UNSUPPORTED_PAGE` until all page checks pass. Closed page admission is:

| Page kind | Exact path | Evaluation policy |
|---|---|---|
| `order-detail` | `/orders/{SYN-ORDER-*}` with the exact root ID | Eligible only after complete independent coherence verification |
| `interaction-detail` | `/interactions/{SYN-INTERACTION-*}` with the exact root ID | Read-only fictional interaction context; use its exact local order link to evaluate the associated complete order |

`scenarios` remains a local portal navigation convenience but is not in the production content
script match inventory and is not an extraction/evaluation source. `orders`, `run-detail`,
safe-error, and every unknown page kind remain unsupported. An unrelated page on an otherwise
allowed localhost origin remains unsupported.

Every supported root must have exactly one governed page root, exact
`data-ssa-schema-version="synthetic-sales-assist-dom/v1"`, its page-kind attribute, and its exact
synthetic ID attribute. The current path and root ID must agree. Duplicate roots, payloads,
sections, IDs, or governed fields fail closed.

## Closed extraction allowlist

The extractor never transfers arbitrary text or `innerHTML`. It reads only exact `data-ssa-*`
attributes and the exact page-kind-specific non-executable canonical JSON payload inventory below:
one interaction payload, or the M5 order payload plus the separate M6 order binding. Unknown or
missing object members fail; object prototypes, duplicate JSON members, noncanonical JSON,
excessive depth or collection size, strings over the bound, non-safe integers, invalid Unicode
scalar sequences, and documents over 524,288 bytes fail.

The versioned allowlist is exhaustive:

| Object | Exact members |
|---|---|
| Extraction envelope | `can_evaluate`, `extraction_schema_version`, `interaction`, `order`, `origin`, `page_identity`, `page_kind`, `page_path`, `panel_state` |
| Order source | `completeness`, `lines`, `mode`, `order_id`, `rule_pack`, `scenario_alias`, `schema_version`, `source_status` |
| Completeness | `declared_relevant_line_count`, `fixture_version`, `observed_order_id`, `ordered_line_manifest_digest`, `rendered_relevant_line_count`, `requested_order_id`, `source_observed_at`, `source_schema_version`, `state` |
| Line | `activity`, `availability`, `drop_ship_state`, `eta`, `line_id`, `line_index`, `line_value`, `product_id`, `quantity` |
| Tagged fact | `reason_code`, `tag`, `value` |
| Money | `amount`, `currency_code`, `currency_registry_version`, `currency_scale` |
| Interaction | `direction`, `evidence_classification`, `identifier_kind`, `interaction_id`, `order_id`, `schema_version`, `target_rep_participation`, `timestamp`, `timestamp_precision` |

The panel receives a reduced summary, never the order or interaction payload. Its exact members are
`backend`, `can_evaluate`, `completeness_state`, `evaluation`, `interaction_id`, `order_id`,
`origin`, `page_identity`, `page_kind`, `rule_pack`, `scenario_alias`, and `source_fingerprint`.
The fingerprint is a lower-case SHA-256 of the complete canonical closed extraction; it carries no
additional source fact and is non-null only for a complete evaluable order.

The allowed order payload element is exactly
`script#ssa-synthetic-order-payload[type="application/json"]`. Its existing order summary,
completeness, and line-universe sections now carry exact `data-ssa-section` markers so the
extractor can prove section ownership before reading governed fields. Its exact `rule_pack`
summary marker must equal the separate root-scoped
`script#ssa-extension-order-binding[type="application/json"]` payload. That payload has exactly
`order_id`, `rule_pack`, and `schema_version`; its schema is
`synthetic-sales-assist-extension-order-binding/v1`, and its pack is restricted to
`SALES_CREDIT` or `DOI`. This separate compatibility payload preserves the exact seven-member M5
`synthetic-sales-assist-dom/v1` canonical order payload and therefore does not create same-version
unknown-member drift.
For a `COMPLETE` source, the extension also binds the two M5 completeness-version members to that
separate rule pack: `sales-credit-m5-fixture/v1` plus
`synthetic-sales-credit-domain/v1` maps exactly to `SALES_CREDIT`, and `shared-fixture/v1` plus
`shared-whole-order-completeness/v1` maps exactly to `DOI`. The DOM rule-pack marker, separate M6
binding, and this independently derived mapping must all agree. The malformed pair
`m5-malformed-fixture/v1` plus `synthetic-malformed-input/v1` can never claim `COMPLETE` or become
evaluable. Coordinated DOM/binding cross-pack substitution therefore fails closed before health or
evaluation POST.
The allowed interaction
payload is exactly `script#ssa-synthetic-interaction-payload[type="application/json"]`.
Interaction DOM markers and payload must agree on all nine interaction members. The renderer-only
M6 compatibility change also adds the exact interaction root `data-ssa-order-id`, an exact
interaction-summary section marker, eight non-schema
`data-ssa-field="interaction.<member>"`/canonical `data-ssa-value` markers, and that canonical
nine-member payload. These additive markers retain `synthetic-sales-assist-dom/v1`; they change no
route, application view, database schema, source fact, Sales Credit behavior, or DOI behavior.
Unrestricted message bodies and notes do not exist in the contract.

The extractor does not read or return cookies, local/session storage, browsing history, query
strings, script source, styles, hidden unrelated nodes, form values, file paths, credentials,
tokens, database contents, unrestricted notes, or arbitrary page text. The CSRF meta value is not
an extracted fact and is read only inside the content script immediately before the explicit
same-origin evaluation POST.

## Independent order coherence

An embedded payload is evidence, not authority. For an order to reach `SUPPORTED_READY`, the
extension independently proves all of the following:

1. the path order ID, root order ID, payload order ID, requested order ID, and observed order ID
   are the same reserved synthetic order identity;
2. DOM, M5 payload, and extension-binding versions are exact and source schema/fixture fields are
   present and bounded;
3. root, payload source, and completeness states are all `COMPLETE`;
4. every required completeness and line section is present exactly once;
5. DOM line IDs and one-based indices are unique, contiguous, ordered, and equal to the payload
   line sequence;
6. declared, rendered, payload, final-marker, and actual DOM line counts are identical, including
   the valid zero-line case;
7. every DOM `data-ssa-value` parses as canonical JSON and equals the corresponding allowlisted
   payload value;
8. every fact has the governed exact tag/value/reason shape, every ID uses its exact synthetic
   namespace, and timestamps, quantities, money, currency, enums, and digests have closed forms;
9. `source_observed_at` is present and identical across the governed representation; and
10. the extension recomputes the ordered line-manifest SHA-256 using
    `synthetic-sales-assist-line-manifest/v1` and domain `m5-rendered-line-manifest/v1`, then
    matches both published digest locations.

An observed fact tagged `UNKNOWN` with its governed reason is valid factual uncertainty and may
remain `COMPLETE`; it is not silently replaced. Missing sections or a source-declared identity,
duplicate-line, or count incompleteness maps to `INCOMPLETE_PAGE`. A malformed governed value maps
to `MALFORMED_PAGE`. A complete claim whose DOM, canonical payload, source facts, or
ordered-manifest digest differ maps to `DOM_PAYLOAD_MISMATCH`. None can evaluate, make a successful
evaluation POST, or persist a successful evaluation. An initial mismatch makes zero requests. If
the page mutates only while the sole read-only `/health` probe is in flight or after it completes,
that probe may have succeeded, but the extension still makes zero evaluation POSTs.

## Closed messaging and requests

A panel command has exactly `expected_order_id`, `expected_origin`,
`expected_source_fingerprint`, `kind`, `request_key`, and `schema_version`. The only kinds are
`GET_PAGE_STATE` and `EVALUATE`; the schema is
`synthetic-sales-assist-extension-message/v1`. `GET_PAGE_STATE` requires all four request/binding
members to be null. `EVALUATE` requires the exact observed loopback origin, synthetic order ID,
lower-case extraction fingerprint, and a bounded key matching
`[A-Za-z0-9][A-Za-z0-9._:-]{0,127}`. A response has exactly `data`, `error_code`, `panel_state`, and
`schema_version`.

The side panel sends a command to the service worker, which finds the current active tab and relays
only that validated command to the installed static content script. The worker does not inspect the
page or fetch. There is no arbitrary message kind or general browser/DOM action.

On page-state refresh, an admitted content script performs one origin-bound `GET /health` with a
4,000 ms abort deadline. It accepts only the exact `application/json; charset=utf-8` media type and
API envelope. Backend status is derived as `PASS` only when HTTP status,
application/build/schema versions, database, migration, projection, and all nine zero safety
counters pass together; every reachable nonpassing projection is normalized to `healthy=false`
and status `FAIL`. A connection failure maps to `BACKEND_OFFLINE`; a reachable nonpassing or
contract-invalid response maps to `BACKEND_UNHEALTHY`.

Evaluation requires an explicit click while the latest extraction remains coherent and backend
health remains passing. Before health or POST, the content script re-extracts the active tab and
requires its origin, order/page identity, and canonical extraction fingerprint to equal the
panel-observed binding. A tab switch or navigation therefore fails closed instead of evaluating a
different synthetic order. Safe retry preserves both its request key and original source binding.
The content script then performs one origin-bound
`POST /api/v1/orders/{order_id}/evaluate` with a 10,000 ms abort deadline and exactly:

```json
{"request_key":"M6-EXT-0123456789abcdef0123456789abcdef","schema_version":"synthetic-sales-assist-api-request/v1"}
```

If the evaluation transport fails after a passing health read, `BACKEND_OFFLINE` carries a null
backend projection rather than stale passing health. A post-health timeout remains `SAFE_ERROR`
with `REQUEST_TIMEOUT`, and a safe retry reuses the exact request key and source binding.

The committed M5 API also accepts null, but the M6 panel deliberately never emits it: each explicit
evaluation uses a generated or user-supplied bounded key, and a safe retry uses that exact key. The
request is same-origin, bounded, JSON,
and protected by the current page's lease-bound M5 anti-forgery meta value. That local nonce is not
a browser session or identity credential and is used with `credentials: "omit"`. No source payload,
fictional contact value, or
other browser material is sent. An abort/timeout becomes a safe non-success state; a safe retry
reuses the same in-memory request key so the existing idempotency contract returns exact replay
rather than a duplicate business event. Changed material under one key maps to
`REQUEST_CONFLICT`. Response envelope, application schema, order identity, rule pack, result,
opportunity line scope, persisted IDs, durations, and safety-relevant members are validated before
display. Both request URLs are built from the revalidated admitted origin plus the exact closed
path; document base-URL state is never consulted.

Full and projected results enforce the same display partition. Sales Credit human review is true
exactly for its seven committed human-review workflows. Its value/aggregate presence follows
`PLACED_VALUE_VERIFIED`, `CURRENT_ONLY`, `CHANGED_REVIEW`, or `UNKNOWN`; its effects always include
`NO_PERSISTENCE_MILESTONE_2`, select exactly one of human review and active-case classification,
and include `ZERO_ACTIVE_VALUE` exactly when the canceled-order reason is present. That reason is
exactly bound to closure `CANCELED`; a canceled placed-value result displays zero active value,
while a noncanceled placed-value result displays the exact placed value. A DOI manual review must
require human review; the converse is not imposed on other DOI states because the M5 model permits
other governed review requirements. Non-opportunity DOI results are unavailable with null values.
DOI closure `NONE` maps to `ACTIVE`, `SHIPPED`/`CANCELED` map to `CLOSED_HARD`, and the remaining
admitted closures map to `CLOSED_REVERSIBLE`; a non-`NONE` closure is displayed only with
`DOI_EXCLUDED`.

## Side-panel state machine

The state vocabulary is closed to these 16 values:

| State | Meaning |
|---|---|
| `UNSUPPORTED_PAGE` | Origin, path, page kind, version, identity, or supported-page structure is not admitted |
| `SUPPORTED_READY` | Supported source is coherent and the backend is healthy; explicit evaluation is available on an order |
| `INCOMPLETE_PAGE` | Required whole-source facts or coherence evidence are absent/incomplete; evaluation blocked |
| `MALFORMED_PAGE` | A governed field or canonical representation is malformed; evaluation blocked |
| `DOM_PAYLOAD_MISMATCH` | A COMPLETE claim disagrees across allowlisted DOM and payload facts; evaluation blocked |
| `BACKEND_OFFLINE` | The exact loopback service cannot be reached |
| `BACKEND_UNHEALTHY` | The service responds but health/version/schema/counter checks do not pass |
| `EVALUATING` | One explicit local request is in flight; duplicate click disabled |
| `SALES_CREDIT_RESULT` | Valid Sales Credit result, including its workflow and human-review fields |
| `DOI_OPPORTUNITY` | Valid DOI opportunity result with separate scopes |
| `DOI_MANUAL_REVIEW` | Valid DOI result requiring manual review |
| `DOI_EXCLUDED` | Valid DOI excluded result |
| `DOI_MONITOR` | Valid DOI monitor result |
| `EXACT_REPLAY` | Existing exact result returned under the same material/key |
| `REQUEST_CONFLICT` | The bounded request key is already bound to different material |
| `SAFE_ERROR` | Closed privacy-safe failure not represented by a more specific state |

The panel displays only validated values: synthetic page identity, source completeness, backend
health, rule pack/version, result/workflow, closed reasons, opportunities/scope, human-review flag,
value status/value when available, replay/conflict, persisted synthetic IDs, processing duration,
and local portal/history navigation. No external action button exists. A future-dashboard label is
noninteractive in M6.

## Volatile state and lifecycle

The extension uses no Chrome storage. Panel state and a safe-retry request key exist in memory only
and disappear on panel, extension, or browser restart. It never persists source payloads,
evaluation details, fictional contacts, CSRF/control tokens, cookies, or database material.

Loading unpacked, reloading, updating, and uninstalling do not require administrator rights and do
not alter the local application database. Uninstall removes only Chrome's unpacked extension
registration; repository and local service data remain governed by their existing lifecycle tools.
