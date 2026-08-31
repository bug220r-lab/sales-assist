# Milestone 5 DOM and embedded-payload contract

- Contract: `synthetic-sales-assist-dom/v1`
- Embedded payload element: `script#ssa-synthetic-order-payload[type="application/json"]`
- Maximum inbound API request body: 16,384 bytes
- Maximum API response body, HTML document, or embedded canonical payload: 524,288 bytes

The order page is semantic, nonvirtualized HTML. The complete relevant line universe is present in
document order. One non-executable canonical JSON object carries the same allowlisted facts. HTML
text is escaped and JSON is embedded so `</script`, executable markup, duplicate members, and
nonfinite values cannot cross the boundary.

## Stable attributes

| Attribute | Owner |
|---|---|
| `data-ssa-page-kind` | Page root |
| `data-ssa-schema-version` | Page root and payload |
| `data-ssa-order-id` | Page/order region |
| `data-ssa-interaction-id` | Interaction region |
| `data-ssa-field` | Allowlisted scalar fact |
| `data-ssa-line-id` | One complete line row |
| `data-ssa-line-index` | One-based document/manifest ordinal |
| `data-ssa-completeness` | Completeness panel |
| `data-ssa-manifest-digest` | Completeness panel and payload |

## Coherence rule

`COMPLETE` requires requested ID equals observed ID; declared count equals rendered count equals
payload count; line IDs are unique; indices are contiguous and ordered; the DOM and payload line
facts match; the recomputed ordered-manifest digest equals both published digests; required
sections and source timestamp exist; and every value validates under its tagged-value contract.

Missing sections, count mismatch, identity mismatch, duplicate lines, stale/source-changed facts,
DOM/payload mismatch, malformed values, or digest mismatch are fail-closed. An individually
observed `UNKNOWN` field is distinct from incomplete extraction and may coexist with a complete
snapshot.

## Executable known answer

The exact canonical UTF-8 embedded payload for the one-line fixture is below. It has no BOM,
insignificant whitespace, or trailing newline.

```json
{"completeness":{"declared_relevant_line_count":1,"fixture_version":"shared-fixture/v1","observed_order_id":"SYN-ORDER-PORTAL-0001","ordered_line_manifest_digest":"6cd6f84917dcddcd376f9c835a2087f0a94390aca6939174c78c343c229c454f","rendered_relevant_line_count":1,"requested_order_id":"SYN-ORDER-PORTAL-0001","source_observed_at":"2026-08-21T12:00:00Z","source_schema_version":"shared-whole-order-completeness/v1","state":"COMPLETE"},"lines":[{"activity":{"reason_code":null,"tag":"KNOWN","value":"ACTIVE"},"availability":{"reason_code":null,"tag":"KNOWN","value":"IN_STOCK"},"drop_ship_state":{"reason_code":null,"tag":"KNOWN","value":"NON_DS"},"eta":{"reason_code":null,"tag":"KNOWN","value":"2026-08-22T12:00:00Z"},"line_id":"SYN-EVIDENCE-PORTAL-LINE-0001","line_index":1,"line_value":{"reason_code":null,"tag":"KNOWN","value":{"amount":"10.00","currency_code":"USD","currency_registry_version":"synthetic-iso-style-currency-registry/v1","currency_scale":2}},"product_id":"SYN-SKU-PORTAL-0001","quantity":{"reason_code":null,"tag":"KNOWN","value":"1"}}],"mode":"complete","order_id":"SYN-ORDER-PORTAL-0001","scenario_alias":"doi-overlap","schema_version":"synthetic-sales-assist-dom/v1","source_status":"COMPLETE"}
```

The ordered line-manifest digest is exactly
`6cd6f84917dcddcd376f9c835a2087f0a94390aca6939174c78c343c229c454f`.
It is independently recomputed over the closed one-line manifest by
`Milestone5BoundaryTests.test_dom_contract_known_answer_payload_and_digest_are_exact` and is
also checked against the rendered DOM and payload by
`PortalHTTPTestCase.test_complete_payload_and_manifest_known_answer_are_exact`.

## Closed malformed and mismatch examples

`mode=malformed-value` publishes `data-ssa-completeness="MALFORMED"`, payload
`completeness.state="MALFORMED"`, and payload `source_status="MALFORMED"`. A local Evaluate
request is rejected with HTTP 503 and the closed API error code
`SOURCE_REPRESENTATION_NOT_EVALUABLE`; no rule evaluation is persisted. This is proved by
`PortalHTTPTestCase.test_malformed_value_mode_is_fail_closed_and_not_evaluable`.

`mode=dom-payload-mismatch` deliberately omits a rendered DOM line while retaining it in the
closed payload. It publishes `data-ssa-completeness="INCOMPLETE"`, payload
`completeness.state="INCOMPLETE"`, and payload `source_status="INCOMPLETE"`. A local Evaluate
request is rejected with HTTP 503 and `SOURCE_REPRESENTATION_NOT_EVALUABLE`; no payload member
or digest can override the line-count mismatch. This is proved by
`PortalHTTPTestCase.test_dom_payload_mismatch_mode_is_concrete_and_fails_closed`.

Executable fixtures additionally cover large complete, explicit zero-line, missing section,
identity mismatch, duplicate line, count mismatch, stale representation, observed unknown, and
backend-failure modes.

Milestone 6 preserves this exact canonical byte contract. Its governed rule-pack proof is carried
in a separate `synthetic-sales-assist-extension-order-binding/v1` compatibility payload and an
order-summary DOM marker; the extension requires both to agree. The M5 DOM version and payload
member set remain unchanged, as do every M5 route, rule, and database behavior.
