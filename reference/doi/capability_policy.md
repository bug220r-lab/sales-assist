
> **Sanitized supporting reference.** This file is a mechanically sanitized derivative of
> source material supplied for the synthetic proof of concept. Historical status/freeze
> language is nonbinding. The curated files under `specs/` govern. No production-system
> access or real-data use is authorized by this reference.

# DOI v0.1.5 Offline Synthetic Order Portal Capability Policy

Authority patch: v0.1.5.3 count/reference reconciliation only; OA safety semantics and zero-live-access boundary are unchanged; independent audit required; not a freeze declaration.

Status: normative Round-4 remediation contract. This artifact governs every source tree, dependency graph, manifest, registry, generated bundle, and packaged output in the DOI offline release. It does not authorize live Synthetic Order Portal access.

## 1. Permanent boundary and policy identity

The literal policy identifier is `doi-oa-capability-policy/v1`. The DOI v0.1.5 offline release has no production OA adapter, OA host permission, credential/session access, live browser control, or network capability. Its only permitted observation inputs are explicitly supplied fictional/static test fixtures and already-governed local package artifacts.

A future exact OA host/read-only adapter requires a separate reconnaissance-derived contract, an independent safety audit, and an expressly frozen capability version. It cannot amend, extend, infer, or silently override this policy.

The policy is closed: an unlisted field, permission, host, capability, helper, alias, wrapper, runtime, transport, or generated behavior is forbidden and fails the release gate.

## 2. Closed offline manifest contract

If the offline deliverable contains an extension manifest, its normalized security projection MUST equal exactly:

```json
{
  "capability_policy_id": "doi-oa-capability-policy/v1",
  "manifest_version": 3,
  "permissions": [],
  "host_permissions": [],
  "background": null,
  "content_scripts": [],
  "externally_connectable": null,
  "optional_permissions_present": false,
  "optional_host_permissions_present": false
}
```

`null` above means the corresponding manifest member is absent; it is never serialized into the real manifest as a null extension field. `permissions` and `host_permissions` MUST be present as exactly empty arrays if the build format requires them and otherwise MUST be absent. No other security-relevant manifest member is accepted.

The following are prohibited at any nesting level, under any spelling/alias/case transformation, or through any dependency-generated manifest fragment:

- `scripting`;
- `debugger`;
- `cookies`;
- `downloads`;
- `nativeMessaging`;
- `webRequest`;
- `webRequestBlocking`;
- `declarativeNetRequestWithHostAccess`;
- broad `tabs`;
- `activeTab` or any equivalent script-injection grant;
- every nonempty, broad, wildcard, scheme-wildcard, subdomain-wildcard, or OA `host_permissions` entry;
- `optional_permissions` and `optional_host_permissions`, including empty declarations intended for later elevation;
- `externally_connectable` or equivalent external messaging;
- nonempty `content_scripts`, broad content-script matches, or programmatic content-script registration;
- `background`, `service_worker`, persistent/event pages, offscreen documents, hidden frames, alarms, or scheduled/background automation;
- permissions or declarations enabling arbitrary script execution, request/response mutation, download/export, filesystem/native access, clipboard injection, credential/session/cookie access, hidden automation, or privilege elevation.

The scan expands manifest variables, merges fragments, resolves build-time conditionals, and inspects the final installed-output manifest. A clean source manifest does not excuse a forbidden generated permission.

## 3. Closed module capability registry

Every module-capability registry in the offline release uses literal version `doi-offline-module-capability-registry/v1` and contains a duplicate-free canonical set drawn only from:

```text
FIXTURE_BYTES_READ
STATIC_DOCUMENT_PARSE
ALLOWLISTED_TEXT_OBSERVATION
ALLOWLISTED_ATTRIBUTE_OBSERVATION
CANONICAL_NORMALIZE
CANONICAL_HASH
PURE_RULE_EVALUATION
DOI_LOCAL_APPEND_ONLY_PERSISTENCE
```

The first five observation/normalization capabilities operate only on caller-supplied static fixture bytes. They do not navigate, attach to, or inspect a live browser page. `DOI_LOCAL_APPEND_ONLY_PERSISTENCE` means DOI-owned test/local state only and never OA state.

Every unlisted capability is forbidden. In particular, no registry or dependency may contain a network, browser, session, cookie, download, script-injection, DOM-mutation, form, input, arbitrary-selector, generic request, generic page-execution, native-messaging, clipboard, filesystem-export, background, or privilege-escalation capability.

## 4. Closed interaction/helper denylist

The static and built-output scanners reject definitions, imports, exports, re-exports, registrations, calls, property references, strings used for dynamic dispatch, reflection targets, computed members, aliases, wrappers, currying, dependency injection tokens, or generated symbols resolving to any of these helpers or semantic equivalents:

```text
click
dblclick
submit
type
fill
press
keyDown
keyUp
keyboard
insertText
setValue
paste
execCommand
dispatchEvent
mouseEvent
keyboardEvent
inputEvent
changeEvent
selectorAction
executeScript
evaluate
pageScript
activateForm
drag
drop
setFiles
uploadFile
```

Also forbidden are:

- direct or reflected assignment to `value`, `checked`, `selected`, `selectedIndex`, `textContent`, `innerText`, `innerHTML`, form fields, or editable content;
- synthetic mouse, keyboard, clipboard, input, change, submit, drag/drop, focus/blur, or pointer events;
- arbitrary selector actions or any helper accepting a selector plus an action/callback;
- generic page-script execution, `eval`, dynamic function construction, injected script tags, or browser debugging protocols;
- form activation, button/control activation, file input assignment/upload, or download/export initiation;
- wrapper names or deceptive aliases whose data flow reaches any forbidden primitive.

The scanner resolves dot access, bracket access, string concatenation, constant folding, destructuring, renamed imports, re-exports, prototype access, computed lookup, registry indirection, wrapper/callback flow, and minified identifiers. An unresolved dynamic capability name is itself forbidden.

## 5. Required scan surfaces and deterministic result

One `DOIOACapabilitySafetyScan` is produced for each release candidate before packaging:

```text
DOIOACapabilitySafetyScan {
  safety_scan_id: Id,
  capability_policy_id: "doi-oa-capability-policy/v1",
  source_tree_sha256: Sha256,
  dependency_lock_sha256: Sha256,
  normalized_manifest_projection_sha256: Sha256,
  module_registry_projection_sha256: Sha256,
  built_output_sha256: Sha256,
  source_finding_count: NonnegativeInteger,
  dependency_finding_count: NonnegativeInteger,
  manifest_finding_count: NonnegativeInteger,
  built_output_finding_count: NonnegativeInteger,
  mutation_canary_count: NonnegativeInteger,
  rejected_dynamic_capability_count: NonnegativeInteger,
  result: PASS | FAIL,
  content_sha256: Sha256
}
```

The normalized scan object includes every field above except `content_sha256`, uses explicit values, and is hashed as:

```text
content_sha256 = SHA256(
  UTF8("doi-oa-capability-safety-scan/v1\n") ||
  UTF8(RFC8785(normalized_scan_object))
)
```

`PASS` is legal only when all six finding/canary/dynamic counts are zero, the manifest matches section 2, every registry member is in section 3, and source plus built output contain no section 4 capability. The scan result is an offline build artifact, contains no OA URL/session/credential/page content, and does not authorize a runtime capability.

## 6. Runtime-negative invariants

Every offline safety test runs with network denied and a mutation-event journal around the static fixture harness. Passing requires all of the following:

- outbound OA reads = 0;
- outbound OA mutations = 0;
- application-originated OA mutation attempts = 0;
- browser navigation/session/cookie/download/native-message operations = 0;
- mutation-event journal entries = 0;
- byte hash of every supplied page/static-DOM fixture is identical before and after the test;
- DOI-local append-only test outputs are the only permitted writes.

Any prohibited-capability finding stops the build before dispatch or artifact promotion. It cannot be downgraded to a warning.

### 6.1 Closed executable-synthetic identity firewall

The literal policy identifier is `doi-synthetic-identity-firewall/v1`. Before fixture execution, canonical lifecycle serialization, projection reduction, adapter construction, network/navigation dispatch, or output promotion, the harness MUST scan the authored fixture, normalized fixture, generated fixture, canonical-vector input, built output, source map, and test-report identity fields. The scan is exact and fail-closed; it does not guess whether a value merely “looks synthetic.”

Every executable synthetic identity in one of the following semantic fields MUST match its exact closed namespace:

| Identity class | Required exact prefix / lexical contract |
|---|---|
| case | `^SYN-DOI-CASE-[A-Z0-9][A-Z0-9-]*$` |
| order | harness identity `^SYN-DOI-ORDER-[A-Z0-9][A-Z0-9-]*$`; when the governed domain field is `OrderNumber`, a mandatory exact entry in the candidate's closed nonserialized mapping inventory supplies a canonical positive-decimal sentinel and the serialized field remains schema-valid |
| customer | `^SYN-DOI-CUSTOMER-[A-Z0-9][A-Z0-9-]*$` |
| product | `^SYN-DOI-PRODUCT-[A-Z0-9][A-Z0-9-]*$` |

All four harness identities are reserved synthetic namespaces and therefore satisfy the mandatory literal prefix `SYN-DOI-`. A schema-constrained domain value does not silently escape the firewall: it requires an exact one-to-one harness mapping, a schema-valid sentinel, and the same historical denyset check before execution. The v0.1.5 V1 lifecycle mapping is exactly `SYN-DOI-ORDER-0001 -> "1"`; mapping metadata is harness-owned and absent from `DOIStagedOrder/v1` canonical bytes. Lifecycle event IDs, source-record IDs, and snapshot IDs are separate opaque technical identities and do not relax the rule for a case/order/customer/product field. Documentation-only identity examples MUST either use the same reserved namespace/mapping or carry an explicit `NON_EXECUTABLE_EXAMPLE` classification outside all executable and generated fixture inventories.

The complete immutable historical evidence inventory supplies a read-only denyset for the scan. No historical case ID, Order Number, customer identifier, or product identifier may appear in an executable synthetic fixture, canonical vector, generated/built output, source map, or test report. The scanner compares exact controlled tokens in memory and persists neither the denyset nor a matched historical value. An unregistered or production-looking numeric order value, generic `case-*` case identity, empty value, lowercase alias, non-bijective mapping, or unregistered prefix fails before execution. Failure produces only the synthetic test ID, semantic identity class, policy ID, and fixed reason `SYNTHETIC_IDENTITY_NAMESPACE_VIOLATION`; it emits no rejected identity value, lifecycle bytes/hash, OA request, navigation, DOI business event, or durable case/order record.

The lifecycle fixed-vector mapping is closed: the former nonconforming V1/V2 case tokens are replaced in the actual canonical inputs by `SYN-DOI-CASE-0001` and `SYN-DOI-CASE-0002`, respectively, and the Round-3 V3 serialization vector uses exact `SYN-DOI-CASE-0003`. V1 additionally uses the closed harness mapping `SYN-DOI-ORDER-0001 -> "1"`, so its actual `DOIStagedOrder/v1.order_number` remains a canonical positive-decimal string without resembling a production Order Number. All dependent canonical bytes, natural-key hashes, stream IDs, staged-record hashes, payload hashes, event-envelope hashes, and projection hashes MUST be regenerated from those exact values. Retaining a stale hash from either former token or the former numeric-looking order value fails the same promotion gate.

### 6.2 Closed OA safety reason routing

The reason registry version is exactly `0.1.5`. OA safety rejection has two mutually exclusive owners:

| Boundary and exact rejected input | Exact reason set | Required result |
|---|---|---|
| System/build boundary: a candidate source/dependency/manifest/registry/generated output contains the forbidden `click` helper or any semantically equivalent write-capable module/manifest capability | `{RC-082}` (`OA_WRITE_PROHIBITED`) | Fail before runtime and package promotion. RC-083 is absent. No helper executes; OA mutation, DOI state append, persistence, browser/network dispatch, and network side effects are all zero. |
| User/API runtime boundary: a deliberate synthetic `POST|PUT|PATCH|DELETE`, GraphQL mutation/write-RPC, generic mutation-capable action/click request, background poll, or unallowlisted side-effectful read request is offered to the application dispatcher | `{RC-083}` (`UNSAFE_ACTION_REJECTED`) | Reject before dispatch. RC-082 is absent because no forbidden capability was packaged. OA mutation, DOI state append, persistence, browser/network dispatch, and network side effects beyond observing the deliberate local blocked probe are all zero. |
| Exact clean policy surface plus an allowlisted DOI-local action against an immutable static fixture | `{}` | No OA safety reason is emitted. Only the explicitly allowed DOI-local test result may persist; OA/browser/network counters remain zero. |

RC-082 never represents a user/API request, and RC-083 never licenses or excuses a forbidden packaged capability. An unrelated safety failure retains its own exact registered code and must not be aliased to either. Both-code output, an alias, an undefined code, or an unknown reason-registry/policy version fails before append, persistence, dispatch, or promotion. The transient rejection result is sanitized and contains no rejected URL, credential, session, customer/order identity, request payload, or other sensitive value; no rejection record persists.

## 7. Deterministic release blockers

`SYN-OA-RO-003` is amended to inspect the complete source/dependency/manifest/registry/generated-output surface defined above. Its exact oracle is: every clean closed fixture returns one PASS scan with zero findings, no OA safety reason, and unchanged fixture hashes; every forbidden system/build capability that could mutate OA—including the canonical `click` row, its semantic aliases, and unresolved dynamic capability dispatch—returns `{RC-082}` and never RC-083. An unrelated non-write safety failure retains its separately governed code. Every failure occurs before runtime with no packaged extension, OA read, OA mutation, state append, persistence, network side effect, or DOI business result.

`SYN-OA-RO-001` table-drives every canonical runtime user/API predicate at the application dispatch boundary: synthetic `POST|PUT|PATCH|DELETE`, GraphQL mutation/write-RPC, generic mutation-capable action/click request, background poll, and unallowlisted side-effectful read request. Every row has the exact oracle `{RC-083}` and never RC-082, rejection before dispatch, zero OA mutation, zero DOI state append, zero persistence, and zero network side effect beyond observing the local blocked probe. `SYN-OA-RO-005` fault-injects each same runtime predicate and must reproduce that result without committing any dependent DOI result.

`SYN-OA-RO-008` is amended to scan every authored and generated executable synthetic case/order/customer/product identity under `doi-synthetic-identity-firewall/v1`, including both lifecycle fixed vectors, before deliberately offering a conforming reserved synthetic identity to the OA boundary. The complete scan must find zero namespace or historical-identity violations, and the OA boundary must reject the conforming synthetic identity before network/navigation dispatch.

Additional release blockers:

| ID | Fixture | Exact oracle |
|---|---|---|
| `SYN-OA-CAP-001` | Table-drive every prohibited manifest permission/member, wildcard/broad/OA host, optional permission, external messaging, background/service-worker, and content-script form through source fragments and the final merged manifest. | Every row yields `FAIL`, identifies exactly the prohibited normalized capability class, promotes no package, and performs zero OA/network/browser activity. The one exact closed section 2 projection yields `PASS`. |
| `SYN-OA-CAP-002` | Table-drive each section 4 helper through direct call, renamed import, re-export, dot/bracket/computed access, concatenated string, wrapper, registry dispatch, callback flow, reflection, and minified built output; isolate exact `click` as the canonical RC-082 row. | Every forbidden write-capability semantic route, including unresolved dynamic capability dispatch, yields exact `{RC-082}` with RC-083 absent before invocation/promotion. An unrelated non-write safety rejection keeps its separately governed code. No mutation helper is invoked, no state append/persistence/network side effect occurs, the mutation journal remains empty, and fixture hashes remain unchanged. |
| `SYN-OA-CAP-003` | Inject deceptive mutation canaries into a dependency, source tree, generated bundle, and source map while keeping the authored manifest clean. | Each canary is detected on its exact scan surface, `result=FAIL`, built output is not promoted, network is denied, and all OA counters remain zero. |
| `SYN-OA-CAP-004` | Build the exact closed offline fixture-only capability registry and run pure parsing/normalization/rule evaluation against an immutable static fixture. | One PASS scan is produced; output is deterministic, the input byte hash is unchanged, mutation journal is empty, and OA/browser/network counters are exactly zero. Any extra registry member changes the result to FAIL. |
| `SYN-OA-RO-009` | Inject `case-0001` into an executable synthetic `case_id`, then table-drive an unregistered production-looking numeric Order Number, missing/non-bijective order harness mapping, unprefixed customer/product identity, lowercase/alias prefix, and one exact controlled historical-identity canary without exposing the canary in output. | Each row fails `doi-synthetic-identity-firewall/v1` before fixture execution, canonical serialization/hash, reducer/adapter construction, network/navigation, or artifact promotion. The positive control `SYN-DOI-ORDER-0001 -> "1"` validates as a schema-safe synthetic mapping. Only `SYNTHETIC_IDENTITY_NAMESPACE_VIOLATION` plus the semantic class is reported for failures; OA counters, lifecycle append count, projection changes, and durable rejected-identity bytes are all zero. |

Round-4 safety ownership oracles:

| ID | Fixture | Exact oracle |
|---|---|---|
| `SYN-REASON-OWN-005` | Insert exact forbidden `click` capability/helper at the closed system/build boundary | Exact `{RC-082}`, RC-083 absent; fail before runtime/promotion; zero OA mutation, state append, persistence, dispatch, and network side effect. |
| `SYN-REASON-OWN-006` | Run the clean closed capability surface and an allowlisted immutable-static-fixture parse, then separately table-drive every canonical runtime user/API predicate | Clean/allowed rows emit neither RC-082 nor RC-083; each runtime `POST|PUT|PATCH|DELETE`, GraphQL mutation/write-RPC, generic mutation-capable action/click request, background poll, and unallowlisted side-effectful read emits only RC-083. RC-082 is never emitted outside its system/build predicate. |
| `SYN-REASON-OWN-007` | Table-drive exact deliberate synthetic `POST|PUT|PATCH|DELETE`, GraphQL mutation/write-RPC, generic mutation-capable action/click request, background poll, and unallowlisted side-effectful read through the user/API dispatcher | Every row yields exact `{RC-083}`, RC-082 absent; fail before dispatch; zero OA mutation, state append, persistence, browser/network dispatch, and network side effect beyond local blocked-probe observation. |
| `SYN-REASON-OWN-008` | Execute one allowlisted DOI-local/read-only request, then separately present a forbidden static `click` capability and each canonical runtime `POST|PUT|PATCH|DELETE`, GraphQL mutation/write-RPC, generic mutation-capable action/click, background-poll, and unallowlisted-side-effectful-read branch | Clean/allowlisted action emits neither code. The static forbidden capability produces exact `{RC-082}` only before runtime. Each runtime unsafe branch produces exact `{RC-083}` only before dispatch, with RC-082 absent; every branch has zero OA mutation, DOI state append, persistence, browser/network dispatch, and network side effect beyond the deliberate local blocked-probe observation. |

`SYN-REASON-OWN-009` proves every one of the 115 registered reasons has a non-registry external owner and deterministic oracle, with no undefined reference or orphan; unknown code or registry version fails before persistence. `SYN-REASON-OWN-010` compares the exact reason sets across this policy, the v0.1.5.3 reason registry/ownership matrix, technical and machine contracts, provenance/state contract, persistence model, transition artifacts, acceptance/synthetic artifacts, opportunity/KPI contract, and implementation handoff. Any alias or byte-level set mismatch fails release. The added RC-115 is an offline normalization observation and grants no OA capability.

All fixed vectors bind the literal policy/scan versions and canonical object above. A field, member order, policy version, source hash, build hash, result, or finding-count mutation changes the expected digest and fails the vector.

## 8. Implementation and audit checklist

1. Scan source, dependency lock/graph, manifest fragments, final manifest, registries, source maps, and generated output.
2. Resolve aliases/wrappers/computed names; reject unresolved dynamic capability dispatch.
3. Enforce the exact empty browser/host permission surface.
4. Run mutation canaries with network denied.
5. Assert input/page hash invariance and an empty mutation journal.
6. Store only the privacy-safe scan result; never store OA content, host, credential, or session material.
7. Block package promotion on any failure.
8. Treat future OA capability work as a separate, independently audited contract.
9. Scan every authored/normalized/generated/built synthetic identity surface under `doi-synthetic-identity-firewall/v1`; require the exact subtype harness namespace, validate every schema-constrained sentinel mapping, compare both mapping and serialized value against the in-memory historical denyset, and reject before execution.
10. Reproduce both lifecycle fixed vectors only from `SYN-DOI-CASE-0001` and `SYN-DOI-CASE-0002`, with V1 order mapping `SYN-DOI-ORDER-0001 -> "1"`; reject former identities/values and stale dependent hashes.
11. Route exact build/system-boundary `click` or equivalent write-capability rejection to RC-082 only. Route every exact user/API runtime dispatch predicate—`POST|PUT|PATCH|DELETE`, GraphQL mutation/write-RPC, generic mutation-capable action/click request, background poll, or unallowlisted side-effectful read—to RC-083 only; reject aliases, both-code output, and unknown code/version before persistence.
12. Run `SYN-REASON-OWN-005..010` and require 115/115 reason ownership with exact cross-document reason-set parity.
