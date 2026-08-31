# Milestone 6 base-route attestation and extension use

This inventory was derived before extension implementation from the committed Milestone 5 route
registry. It freezes the network surface inherited by Milestone 6; it does not add a route.

| Evidence | Exact value |
|---|---|
| Base commit | `28909059cc1ef8a77e3a4bf428782dbf0280d7c4` |
| Base tree | `27ec8ddccb4d2428af5a6b92d5420f1bbb1a18e7` |
| Registry source | `src/synthetic_sales_assist/portal/server.py` |
| Registry source blob | `7b700a7382b3b71c913f271c2d6fc89513bf6d87` |
| Static-asset source blob | `24300caf9d5dca622e0f8197a5e063f4a0cfdc73` |
| API contract source blob | `6237715149e8fb4b6f91cf3ed29b0220806ad4e7` |
| DOM rendering source blob | `90312c9e0169b1b4b0dca88cd1e707854a6d3093` |
| Default service origin | `http://127.0.0.1:8765` |

The route expressions are the exact `_ALIAS_ROUTE`, `_ORDER_ROUTE`,
`_ORDER_EVALUATE_ROUTE`, `_ORDER_HISTORY_ROUTE`, `_INTERACTION_ROUTE`, `_RUN_ROUTE`,
`_GET_ROUTES`, and `_allowed_methods` definitions in the registry blob. The two entries expanded
through `*STATIC_ASSETS` are recorded explicitly below.

## Complete committed M5 method/path inventory

| Method | Exact path or closed path expression | Surface | Success |
|---|---|---|---:|
| `GET` | `/` | HTML redirect to `/scenarios` | 303 |
| `GET` | `/health` | API health | 200 or 503 |
| `GET` | `/api/v1/scenarios` | API scenario inventory | 200 |
| `POST` | `/api/v1/scenarios/{alias}/instantiate` | API instantiation | 201 |
| `GET` | `/api/v1/orders` | API order inventory | 200 |
| `GET` | `/api/v1/orders/{order_id}` | API order detail | 200 |
| `POST` | `/api/v1/orders/{order_id}/evaluate` | API local evaluation | 200; exact request-material conflict 409; unavailable 503 |
| `GET` | `/api/v1/orders/{order_id}/history` | API persisted history | 200 |
| `GET` | `/api/v1/interactions/{interaction_id}` | API interaction detail | 200 |
| `GET` | `/api/v1/runs/{run_id}` | API run detail | 200 |
| `GET` | `/api/v1/metrics/summary` | API metrics | 200 |
| `GET` | `/api/v1/system/status` | API status | 200 |
| `POST` | `/api/v1/system/shutdown` | API owned shutdown | 202 |
| `GET` | `/scenarios` | HTML scenario library | 200 |
| `GET` | `/orders` | HTML order inventory | 200 |
| `GET` | `/orders/{order_id}` | HTML order detail | 200 |
| `GET` | `/interactions/{interaction_id}` | HTML interaction detail | 200 |
| `GET` | `/runs/{run_id}` | HTML run detail | 200 |
| `GET` | `/static/ssa.css` | exact repository-owned CSS | 200 |
| `GET` | `/static/ssa.js` | exact repository-owned JavaScript | 200 |

`{alias}` matches `[a-z][a-z0-9-]{1,63}`. `{order_id}` matches
`SYN-ORDER-[A-Z0-9-]+`, `{interaction_id}` matches `SYN-INTERACTION-[A-Z0-9-]+`, and
`{run_id}` matches `SYN-RUN-[A-Z0-9-]+`. These are expressions in a closed registry, not wildcard
filesystem or proxy routes. Every path rejects query strings, fragments, percent escapes,
backslashes, traversal, network-path references, and absolute-form targets before dispatch.

The method is part of the contract. A known path with a different method returns 405 with its
endpoint-specific `Allow`; an unknown path returns 404. `HEAD`, `OPTIONS`, `PUT`, `DELETE`, and
`PATCH` never act as compatibility aliases. POST requests retain exact Host, same-origin Origin,
bounded-body, content-type, and CSRF checks. Owned shutdown also requires its independent shutdown
token.

## Routes used by the extension

The extension uses no new network route and has no generic fetch primitive:

| Method | Path | Trigger | Purpose |
|---|---|---|---|
| `GET` | `/health` | once per supported-page refresh/open, plus once per explicit evaluation | Block evaluation unless the current local health preflight is `PASS` and all contract checks succeed |
| `POST` | `/api/v1/orders/{order_id}/evaluate` | one extension Fetch API invocation after each explicit user Evaluate click and passing preflight | Send the exact API-request-v1 object for the independently verified synthetic order |

Both calls execute in the supported page's isolated content script. Each target is constructed as
an absolute URL from the independently validated page origin and one exact closed path, so a hostile
page `<base>` cannot redirect request resolution. The extension service worker only relays closed
messages; it performs no fetch. The POST uses the existing page-scoped
`meta[name="ssa-csrf-token"]`, exact same-origin semantics, and `X-SSA-CSRF-Token`; the token is
never included in the extraction object, messaged to the side panel or worker, or persisted.
Milestone 6 does not admit a `chrome-extension://` Origin and does not weaken M5 authentication.
There is no hidden or repeated polling: a supported refresh/open performs one health read, and an
explicit evaluation performs one additional health preflight followed by one extension Fetch API
invocation for the evaluation POST. Chrome may retransmit that same byte-identical POST and
request key after an ambiguous pre-response transport failure; M5 exact replay makes such a
transport retry idempotent. The extension does not issue a second fetch invocation or claim that
the server always observes at most one transport attempt.

The content extractor reads supported HTML representations directly. Local history links point to
the closed `/orders/{order_id}` HTML page, where persisted history is already rendered. No
dashboard/control-center route exists in M6; a future-dashboard affordance must remain unavailable
and unlinked until a separately authorized milestone.

The extension requires exactly API envelope `synthetic-sales-assist-api/v1`, request
`synthetic-sales-assist-api-request/v1`, DOM `synthetic-sales-assist-dom/v1`, and application view
`synthetic-sales-assist-application/v1`. A wrong version fails closed; it is never negotiated or
silently downgraded.
