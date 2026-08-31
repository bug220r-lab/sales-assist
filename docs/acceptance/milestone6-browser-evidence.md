# Milestone 6 automated browser evidence

- Date: 2026-08-31
- Scope: Milestone 6 localhost Chrome-extension runtime only
- Base commit: `28909059cc1ef8a77e3a4bf428782dbf0280d7c4`
- Base tree: `27ec8ddccb4d2428af5a6b92d5420f1bbb1a18e7`
- Extension version: `0.1.0`
- Final deterministic package SHA-256: `acb0ff977e24d69a7d4fab0d1426ef5eba30c0d8ec9b86a1ab744a6b9319210d`
- Browser mechanism: official Codex in-app Chromium browser control
- Observed User-Agent: `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36
  (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36`
- Service origin: `http://127.0.0.1:8765`
- Python source: verified Codex-bundled Python 3.12.13 selected only through explicit
  `SSA_PYTHON`; launcher output labeled it `DEVELOPMENT / NONPORTABLE`
- Isolated evidence root: `%TEMP%\SyntheticSalesAssist\m6-final-browser-20260831`

## Evidence boundary

The broad browser matrix first exercised deterministic package
`96cb48b46f46887f6a525c5c7634aaa7498f01a03c2a19aa417169aa67cf06de`.
Subsequent security review tightened the response contract and ran the full final-byte matrix.
Independent final review then closed two additional input-coherence edges: raw empty query or
configured-fragment delimiters and impossible bounded health-registry telemetry. The final
current-byte delta rerun loaded the exact current canonical, contract, origin, extraction, content,
and live-renderer DOM sources. It executed 105 ECMAScript grammar/coherence observations and five
health observations: one coherent healthy envelope plus four fail-closed relationship cases.
The unchanged panel, renderer, result, redirect, offline, and network observations remain bound by
their byte-identical source hashes. All final browser observations below are bound to package `acb0ff977e24d69a7d4fab0d1426ef5eba30c0d8ec9b86a1ab744a6b9319210d`.

The controllers supplied only the minimal local `chrome.runtime` relay and deterministic bounded
faults. They did not reimplement extraction, canonical parsing, origin validation, response
validation, state mapping, or panel rendering. The side-panel run used the real HTML, CSS,
canonical/contracts modules, panel script, controls, and rendered DOM.

This is automated browser-runtime evidence. It is not a claim that the unpacked-extension
permission dialog, reload, or uninstall checklist was manually completed. Those user-visible
steps remain `PENDING` in `docs/milestone6-manual-acceptance.md`.

## Immutable evidence binding

The final evidence-bundle SHA-256 is:

```text
17ba8ba6e8d1d813b7ba07097fbc1e8d676efa13a55d0f4e778f131c81cacb5f
```

Its preimage is canonical JSON with lexicographically sorted object members and no insignificant
whitespace, using the exact component map below. The boundary test rejects duplicate or missing
component names, recomputes this aggregate, recomputes all current repository source hashes shown
in the map, and independently rebuilds the deterministic ZIP hash.

Controller, live-DOM, and observation components are operator-recorded SHA-256 values from the
official in-app Chromium run. Their ephemeral preimages are intentionally not represented as
independently executable repository artifacts; the aggregate is a tamper-evident operator record,
not a stronger reproducibility claim. Reproducible deterministic DOM/unit/integration tests cover
the same contracts in the committed suite.

```text
baseline_evidence_bundle=9de0f4f224c55d58ecd558c2c71c27187eaaa5338bc11d53d385cb0f354a6951
baseline_extension_package=96cb48b46f46887f6a525c5c7634aaa7498f01a03c2a19aa417169aa67cf06de
browser_user_agent=40956f08f6c9af83802ecd226385c678a06f995e8a19f59cd575a9a4c6acc287
canonical_source=3937612403f1e021d877fab047ecd44524c27ce854fd7354a6398599e1e7a8d7
content_controller=c6c50ff07ba889eabea0d11c30e6726a5a979f555f7ed1973cf61b27718af870
content_observations=7c70981da1ee69df89d16d7d68e63dce56d0596489d2aac1a1e2b8bd32653ce7
content_script_source=5d5240e74b2d0bc85a36c0b18a2d99ca4f6bc1064942543a783296af80f349d1
contracts_source=50f445072a954d4d87845409bf43adec07df2f49c9bdcc3e5fba35c65581f101
evaluating_observations=f977d1688eccad6cc76f74d4b534a974664e57e2c8b90351d71d5ef321052eb1
extension_package=acb0ff977e24d69a7d4fab0d1426ef5eba30c0d8ec9b86a1ab744a6b9319210d
extraction_source=f4dde4464a764a4bfedb20a4c091033e6af228bcde16ae08ac8ab8d9e85f2e9c
grammar_controller=1d1dd97f75bbb00b522364ea251cd510ca02ef71c4a876f06778592b9cda24f5
grammar_observations=ff8f39132cdf3ec5e40c72366254fe3b4363e5efcf7074711307e3f4e5789757
live_order=3cd5872f8b6a7cf6e1f63334f6ad38bf0d4e6bc9e3c75d83040016f66611e15c
manifest_source=81e29390b08d19db4a29934be0f1b983fba0fa9808d0eabc3c34ff1e26ede53f
network_observations=e07d0a3d42eef4f468e93aec998d2db789bb7f5075e473b1b2f6509019157cfc
origin_source=44188f68a56e9c9498fc808d14a3a2216c38f3defcac7ef92cff9a9d87da081b
package_inventory_source=366bc639e2be6c9be2ff349ce0995d76a4e574af101ef28b00c4aa7b376ce65a
panel_controller=47e554ce9ba9787beadfc5ba5b104d12376c73ae5f42ab7e8a9a3c1ba73ddbd1
panel_observations=7ce5c6e0750fa3f61096c7ed1b97bb2d1eb8fc6e1a7ef70252b0c3f10c7b0101
panel_script_source=ed3312cf24615634e04415eccf19bd3a375e8904886d3c71adaa646dce6ded36
renderer_source=b6e70ad5f2eadb451ed2a3597807a8c0646bbfe2914ca6d8d13c06c22db8f8a1
result_displays=e5c427ad3d432a66701c59d5f5a8b74ed14a45eb1f7208e89bf9a907e6feea07
safety_counters=b8e1f2a6fb665c4652f48968408e6762ce80b2576ef1ee2cb9f6eb371159bd86
service_worker_source=4d7f471720d6a1d22e67ab6e944abe6ab6138f4c52f06004f37497a84d1ae7b0
```

## Live M5 portal and extraction

The owned M5 lifecycle reported application `0.1.0`, build
`synthetic-sales-assist-m5/v1`, database schema `4`, and origin
`http://127.0.0.1:8765`. The DEVELOPMENT / NONPORTABLE launcher fallback was selected only by its
explicit validated `SSA_PYTHON` path. Owned stop succeeded and released the port.

The final live DOI order page proved:

- DOM version `synthetic-sales-assist-dom/v1`;
- exact M5 seven-member canonical order payload, with no `rule_pack` member;
- exactly one root-scoped extension binding payload;
- binding version `synthetic-sales-assist-extension-order-binding/v1`;
- exact binding members `order_id`, `rule_pack`, and `schema_version`;
- matching governed flat order-summary and line-universe markers;
- independently coherent declared/rendered counts, ordered line identities, manifest digest,
  source time, schema versions, and synthetic identity.

It extracted as `SUPPORTED_READY`, `can_evaluate=true`, rule pack `DOI`, and a lower-case SHA-256
source fingerprint. The governed Sales Credit interaction extracted as `SUPPORTED_READY`,
`can_evaluate=false`, with exact interaction/order identities and no evaluable fingerprint.

## Business-result and fail-closed coverage

The real content script validated and projected these committed result partitions without
re-evaluating business rules:

| Scenario | Panel state | Top-level result | Human review |
|---|---|---|---:|
| `sales-credit-target-rep` | `SALES_CREDIT_RESULT` | `CREDIT_CONFIRMED_TARGET_REP` | false |
| `sales-credit-human-review` | `SALES_CREDIT_RESULT` | `MANUAL_REVIEW_REQUIRED` | true |
| `doi-fulfillment-split` | `DOI_OPPORTUNITY` | `DOI_OPPORTUNITY` | true |
| `doi-manual-review` | `DOI_MANUAL_REVIEW` | `DOI_MANUAL_REVIEW` | true |
| `doi-full-ds` | `DOI_EXCLUDED` | `DOI_EXCLUDED` | false |
| `doi-dedupe-review` | `DOI_MONITOR` | `DOI_MONITOR` | true |

Exact retry returned `EXACT_REPLAY` with the persisted evaluation identity. Reusing a bounded key
for different material returned `REQUEST_CONFLICT` /
`IDEMPOTENCY_KEY_MATERIAL_CONFLICT`. The result display preserved rule-pack/version,
top-level/workflow state, human-review flag, value status/value, reasons, separately scoped DOI
line opportunities, persisted IDs, and processing duration.

The deterministic extractor matrix accepted normal, large, explicit-zero-line, and governed
observed-`UNKNOWN` COMPLETE sources as `SUPPORTED_READY`. It failed closed for the actual
malformed/incomplete families: missing governed section or payload, identity mismatch, duplicate
line, declared/rendered count or ordered-manifest mismatch, DOM/payload mismatch, and malformed
governed field. Unsupported pages and wrong contract versions remained unsupported. It also
rejected cross-rule-pack source version pairs, non-string source/currency members, a nested
duplicate end marker, and the literal string `"null"` where a nullable digest value was JSON null.
No failed extraction made a successful evaluation call or persisted a successful evaluation.

The final Node contract canaries accepted all seven captured M5 result fixtures: three Sales
Credit and four DOI. They rejected 18/18 full-response and 18/18 projected-response contradiction
families, including closure/value/cancellation, workflow/result, human-review, replay/conflict,
opportunity/value, identifier, and source-binding contradictions. A source-failure response must
carry either a coherent `INCOMPLETE`/`MALFORMED` summary or a safe error; null data with null error
is rejected.

## Backend, grammar, and network canaries

The final Chromium rerun observed:

- healthy readiness: `SUPPORTED_READY`, backend `PASS`, all nine counters zero;
- inconsistent HTTP 200 health envelope: `BACKEND_UNHEALTHY`, backend `FAIL`;
- redirected health: `BACKEND_UNHEALTHY` / `RESPONSE_REDIRECT_INVALID`;
- redirected evaluation: `SAFE_ERROR` / `RESPONSE_REDIRECT_INVALID`;
- redirect-target requests: zero;
- post-health dropped evaluation connection: `BACKEND_OFFLINE`, backend `null`;
- exact final grammar/coherence observations: 105/105 pass across CR, LF, U+2028, U+2029,
  identifiers, origin, raw empty delimiters, admitted post-fragment question marks, timestamp,
  numeric, money, rule-pack/source, marker, and digest families;
- coherent bounded health telemetry: `SUPPORTED_READY` with capacity `256`, evaluated count not
  above registry count, and registry count not above capacity;
- four impossible health envelopes: capacity zero, capacity above `256`, evaluated count above
  registry count, and registry count above capacity all returned `BACKEND_UNHEALTHY` /
  `HEALTH_CONTRACT_INVALID`.

The wider deterministic suite also covered oversized bodies, wrong media types, unknown conflict
envelopes, cross-rule-pack success envelopes, source mutation during health, stale page binding,
10-second abort/timeout behavior, and safe retry with the same key/source binding.

One explicit Evaluate click issued one origin-bound health GET and one exact evaluation POST from
extension code. When the harness destroyed the POST socket, Chromium transport delivered the same
idempotent POST twice; the content script itself invoked the POST fetch once and had no hidden
polling or retry loop. This transport receipt is recorded rather than misreported as an extension
retry. Every fetch used `redirect: manual`, `credentials: omit`, and an exact bounded loopback URL.
The hostile-document-base canary did not retarget either request.

The evaluation POST carried only:

- exact `/api/v1/orders/{SYN-ORDER-*}/evaluate` path;
- a 64-character lower-case hexadecimal same-document anti-forgery lease nonce;
- `request_key` and `schema_version` in the JSON body;
- no Cookie header, credentials-in-URL, source payload, contact value, database material, or
  credential/session token.

Observed external requests: `0`. The service worker made zero fetches.

## Side-panel states

The real panel rendered exactly these closed states:

```text
UNSUPPORTED_PAGE
SUPPORTED_READY
INCOMPLETE_PAGE
MALFORMED_PAGE
DOM_PAYLOAD_MISMATCH
BACKEND_OFFLINE
BACKEND_UNHEALTHY
EVALUATING
SALES_CREDIT_RESULT
DOI_OPPORTUNITY
DOI_MANUAL_REVIEW
DOI_EXCLUDED
DOI_MONITOR
EXACT_REPLAY
REQUEST_CONFLICT
SAFE_ERROR
```

All 15 response states matched the requested state and accessible heading. Only
`SUPPORTED_READY` enabled Evaluate. The real delayed relay displayed `EVALUATING`, disabled
Evaluate and Refresh, then completed as `DOI_OPPORTUNITY`. Backend cards displayed `PASS` for
healthy/result states, `FAIL` for reachable inconsistent health, and `Not checked` for offline or
pre-backend states. The history link remained exact loopback/order-bound; the future-dashboard
item remained a noninteractive unavailable label.

## Safety closeout

```text
EXTERNAL_MUTATION_REQUEST_COUNT=0
EXTERNAL_PRODUCTION_SYSTEM_ACCESS_COUNT=0
NON_LOCALHOST_RUNTIME_REQUEST_COUNT=0
NON_SYNTHETIC_FIXTURE_COUNT=0
PRODUCTION_MUTATION_REQUEST_COUNT=0
PRODUCTION_SYSTEM_ACCESS_COUNT=0
REAL_CUSTOMER_DATA_COUNT=0
REAL_CUSTOMER_IDENTITY_COUNT=0
SECRET_MATERIAL_COUNT=0
```

The final loopback harness and owned service were stopped after capture, port 8765 was released,
and no extension was installed. Manual permission/reload/uninstall acceptance remains pending.

```text
M6_AUTOMATED_BROWSER_EVIDENCE = PASS
M6_MANUAL_ACCEPTANCE = PENDING
```
