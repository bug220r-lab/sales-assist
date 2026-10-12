# Help Scout evidence reader for Sales Credit

This standalone reader collects source facts for a later human Sales Credit review. It does
not award credit, qualify a two-way interaction, change orders, or update Sales Assist state.
It is separate from the installed daily DOI app and the draft-transfer adapter. Development
and acceptance use synthetic fixtures and fake HTTP only; this build does not activate live
authentication or access.

The user explicitly approved this isolated implementation on 2026-10-12. That approval is
a bounded exception to the repository's synthetic-only source-adapter boundary, not a
change to the synthetic rules engine or permission to activate live credentials. See
[ADR 0044](adr/0044-isolated-helpscout-credit-evidence.md).
The subsequently approved cached snapshot runner is described in
[ADR 0045](adr/0045-cached-read-only-evidence-pilot.md). Its implementation and offline
tests do not run a live pilot or authorize token issuance.

## Intended use and fixed scope

The entry-point contract is `EvidenceReader(ReadClient(...)).read()`. Supply one exact,
source-proven customer email to the read client. Results contain identity candidates,
conversation and thread facts, reply associations, and explicit coverage. Review these
facts alongside actual Dialpad and Order Admin evidence before applying existing rules.

The intended account scope is the ECS mailbox `166170`, with target author user `897275`.
These are fixed integration identifiers. A conversation assigned to that user is not proof
that the user wrote any particular message. A phone-only contact needs a source-proven
email first; the reader does not guess emails or perform broad name searches.

Use the synthetic offline fixture entry point to exercise the reader before considering
live use. Fake transports must remain in memory and cannot invoke the real HTTP transport.
Keep generated offline output synthetic. Do not replace fixture addresses with real
customer addresses or paste real response bodies into tests, documentation, or Git.

From the isolated checkout with the project installed in its local Python environment:

```powershell
.\.venv\Scripts\python.exe -m sales_credit_evidence --demo
.\.venv\Scripts\python.exe -m pytest tests/test_sales_credit_evidence_reader.py tests/test_sales_credit_evidence_transport.py tests/test_sales_credit_evidence_cached_auth.py tests/test_sales_credit_evidence_pilot.py tests/test_sales_credit_evidence_cli.py tests/test_sales_credit_evidence_literals.py -q
```

The default invocation prints help; `--demo` uses a built-in synthetic in-memory transcript
and prints counts and safe outcome codes. Neither path reads a connection or uses live HTTP.
The CLI also provides the explicitly gated cached snapshot pilot described below. It has
no token/secret argument, automatic credential discovery, or customer-input importer.

The lower-level Python API accepts an already supplied, nonrenewing credential. This
example describes the boundary and is not run by setup or tests:

```python
from sales_credit_evidence import EvidenceReader, ReadClient, SuppliedCredential

# These three values must be supplied by the authorized caller in memory.
# Do not extract them from a cleanup process or put them in shell arguments.
# The coordinated cached snapshot runner below is the supported cache bridge.
credential = SuppliedCredential(authorized_token, authorized_expiry)
client = ReadClient(source_proven_email, credential=credential, enable_live=True)
result = EvidenceReader(client).read()
safe_summary = result.summary()  # Counts/codes only; detailed source facts stay in memory.
```

`EvidenceReader(..., include_content=True)` optionally retains bounded plain-text excerpts
in memory for human relevance review; default results omit message content. `read` can take
`order_placed_at="2026-10-01T16:00:00Z"` to compare source creation times, without treating
those as verified send times. Never log/serialize the full detailed result during live use.

## Authentication and a later authorized read

Networking defaults to disabled. An authorized caller must explicitly enable the
read transport with `enable_live=True` and supply a nonrenewing
`SuppliedCredential(token, expires_at)`. The caller owns the credential's lifecycle and
must supply a valid, timezone-aware expiry. The core reader has no environment lookup, cache
loading/decryption, authentication-provider import, token issuance, or refresh behavior.
An expired credential or HTTP 401 ends the read; HTTP 403 is an access failure, not an
empty search. No automatic renewal or fallback connection is permitted.

Keep tokens out of shell arguments, output, logs, fixtures, and saved evidence. Do not
obtain a token by inspecting another process or a cleanup job. The core reader does not
coordinate or change that job's authentication. A transport constructed with live access
disabled must fail before making a request. The separate bridge below can read one
explicitly approved cached snapshot only after the credential owner coordinates access.

Help Scout documents bearer authentication and uses 401 for expired access. Its OAuth
issuance/refresh endpoints are intentionally outside this reader's allowlist.
[Official authentication reference](https://developer.helpscout.com/mailbox-api/overview/authentication/).

## Coordinated cached snapshot pilot

`pilot.py` is a minimal one-customer runner. Before it reads any connection bytes, require
all of these explicit inputs:

- `--live` to enable this invocation.
- One `--email` containing an exact source-proven customer address.
- One `--connection-path` naming the approved existing `.dpapi` connection; it is a
  nonsecret path, not a token. There is no environment or default-path discovery.
- `--ownership cleanup-complete` or `--ownership controlled-handoff-complete`, based on
  the credential owner's actual coordination outside this runner.
- `--confirm-sole-owner` to attest that all users of this connection have been coordinated.

Do not assert an ownership state merely to make the command run. The runner does not
inspect cleanup processes, infer that they finished, or independently verify the attestation.
It acquires the existing fixed-user `SessionLease` before loading a snapshot, holds that
lease throughout the read, and closes it on every exit path. This excludes cooperating
session providers only; it cannot establish that unrelated consumers have stopped.

The following is a **synthetic command example**, not a live test or a real approved path.
For an authorized pilot, replace the example address and path with the exact approved
scope only after the ownership statements are true. Do not put secrets on this command line.

```powershell
.\.venv\Scripts\python.exe -m sales_credit_evidence --live --email person@example.test --connection-path 'C:\approved-example\connection.dpapi' --ownership controlled-handoff-complete --confirm-sole-owner
```

`cached_auth.py` reuses stable-file and read-only DPAPI primitives without instantiating
an issuing provider. It accepts the existing session-cache schema: `client_id`,
`client_secret`, `access_token`, `expires_at`, and `user_id`, with optional `grant_type`
and `token_type`. The fixed user must be `897275`. The snapshot's authoritative epoch
`expires_at` is converted to UTC without changing it; no guessed TTL is substituted.
Client credentials present in that schema are never used to issue a token. The decoded
record and plaintext buffers/references are cleared after projection to the supplied
credential. Do not interpret reference clearing as a guarantee of physical memory erasure.

The runner enforces a 120-second expiry margin initially and before every GET through
`ReadClient(expiry_margin_seconds=120)`. Near-expiry, stale, malformed, or missing cache
data blocks the pilot. The snapshot is loaded only once: it is not held until stale,
reloaded after failure, renewed, rewritten, or replaced by a fallback credential. A 401
stops the read. Any token issuance is a separate action requiring credential-owner
coordination and specific approval outside the reader; do not weaken the margin to proceed.

Pilot limits are one exact email, mailbox `166170`, author `897275`, `max_requests=50`,
`max_attempts=1`, and `include_content=False`. It returns counts and safe codes only;
detailed customer facts and message bodies are not written to output or disk. No total
wall-clock deadline is guaranteed: the transport timeout bounds individual socket
operations, and traversal limits bound work. These tighter limits apply to the runner;
the general reader's defaults are documented separately below.

| Pilot status | Meaning |
|---|---|
| `DISABLED` | Live access was not explicitly enabled; no cache or API read occurred. |
| `BLOCKED` | Required inputs, ownership, lease, or credential checks prevented a usable run. |
| `INCOMPLETE` | Read coverage did not establish a complete successful scoped traversal. |
| `COMPLETE` | The available scoped search/history traversal completed successfully. |

The pilot's `credit_classification` is always `NOT_EVALUATED`. A complete read is not a
credit decision or proof of personal sending; incomplete coverage is not a negative finding.
The CLI exits with code `0` for `COMPLETE` and `2` for every unsuccessful pilot status;
offline help and demo also exit with `0`. Invalid arguments produce a redacted code only.
No live test, cache read, credential activation, lease acquisition, or external request is
performed as part of this build's documentation and fake-HTTP verification.

## API contract verified on 2026-10-12

The API origin is exactly `https://api.helpscout.net`, with version prefix `/v2`.
All allowed requests use GET. No mutation, token, attachment download, browser, or
general-purpose URL-fetch capability is exposed.

| Stage | Request and evidence rule |
|---|---|
| Identity search | `GET /v2/customers?mailbox=166170&query=(email:"person@example.test")`. URL-encode query values; traverse all pages before declaring no exact match. |
| Customer identity detail | `GET /v2/customers/{id}/emails` for every scoped search candidate. This endpoint is an unpaginated collection: no `page` query or metadata. Email objects use `id` and `value` under `_embedded.emails`. Missing/malformed collections or unexpected pagination leave identity coverage incomplete. |
| Conversation discovery | `GET /v2/conversations?mailbox=166170&status=all&query=(customerIds:123)`. Proceed only with one unambiguous exact customer; deduplicate conversations and verify native customer identity and `mailboxId` before fetching threads. |
| History | `GET /v2/conversations/{id}/threads`. Retrieve separate thread pages; embedded conversation threads are not a completeness proof. Retain native conversation and thread IDs. |

The customer email query is a **contains** search. Exact identity is a local check against
each returned email value, using outer-whitespace trimming and case-insensitive comparison.
Do not add aliases, remove plus suffixes, or correct spelling. Multiple exact customer IDs
remain ambiguous. A search hit that does not exactly match is not a customer identity match.
Ambiguous or incomplete identity stops conversation reads; no candidate is silently selected.
[List Customers](https://developer.helpscout.com/mailbox-api/endpoints/customers/list/),
[List Emails](https://developer.helpscout.com/mailbox-api/endpoints/customers/emails/list/).

Conversation search defaults to active records, so the explicit `status=all` is necessary.
The `customerIds` query alone spans inboxes; the mailbox filter must remain present on
every page. Email conversation search can also match recipients and profile addresses,
which is why it cannot replace verified customer identity. Embedded chat threads can be
truncated. [List Conversations](https://developer.helpscout.com/mailbox-api/endpoints/conversations/list/).

Use the conversation's native `_links.web.href` as its UI reference, with the native thread
ID alongside it; do not invent a thread permalink. Preserve conversation state and status.
The conversation `threads` count excludes notes and counts published threads, so it is
not the number of rows expected from the full thread endpoint. Merged records can produce
301 or 404 responses; redirects are refused and the affected history remains incomplete.
[Get Conversation](https://developer.helpscout.com/mailbox-api/endpoints/conversations/get/).

## What the evidence does and does not establish

Preserve each thread's raw `type`, `state`, `status`, `source.type`, `source.via`, native
author/customer IDs, relevant recipient identity matches, and timestamp evidence. Use
thread `createdBy`, not conversation `assignee` or thread `assignedTo`, for authorship.

Only a published `message` attributed to the target user is an outbound candidate.
Drafts, notes, lineitems, forwards, bounced/hidden/review/underreview states, scheduled
messages, and known automated sources do not establish sent email. A published `customer`
thread must match the verified customer identity to become an incoming candidate. Preserve
exclusions and uncertain source provenance rather than treating them as customer silence.
Help Scout's thread contract exposes source and state fields but no universal automation,
delivery-confirmation, or causal reply-parent field. An unrecognized source stays uncertain.
[List Threads](https://developer.helpscout.com/mailbox-api/endpoints/conversations/threads/list/).

Even a published user-attributed reply is not independent proof of personal sending or
delivery. Help Scout permits imported historical replies that generate no email and permits
explicit user attribution. Its creation timestamp can be supplied for imports. A saved
reply ID indicates template usage, not necessarily automation.
[Create Reply Thread](https://developer.helpscout.com/mailbox-api/endpoints/conversations/threads/reply/).

Preserve raw `createdAt` (bounded to 128 characters, hidden from repr), validated time,
precision, and parse failure separately. Help Scout
documents UTC ISO 8601 timestamps with seconds; do not silently label malformed, date-only,
or timezone-free values as exact. `createdAt` is source creation time, not a separately
verified send timestamp. Scheduled time is not evidence that sending occurred.
[Time](https://developer.helpscout.com/mailbox-api/overview/time/).

An incoming and outgoing thread in the same conversation can be associated for review
when identity and chronology support it. That association is not proof that the customer
replied to a specific message, that the exchange concerned a purchase, or that it preceded
an order. An outbound message alone never becomes a two-way interaction. Human review must
resolve relevance, import/automation uncertainty, and the order chronology. This reader
does not change the existing 14-day operational review horizon or any credit rule.

## Coverage, pagination, and errors

Report coverage independently for identity search, each conversation search, and each
conversation's thread traversal. Useful facts from completed pages survive a later failure;
they do not authorize conclusions that require complete coverage.

| Result condition | Permitted interpretation |
|---|---|
| Every required page succeeds, validates, and terminates | Complete traversal of currently accessible results in the stated scope. |
| Exact identity search completes with zero exact matches | No exact customer identity found in this accessible mailbox search. |
| Verified identity and every conversation page complete with no conversations | No matching accessible conversations found for that identity and mailbox. |
| Any page fails, loops, violates scope, or has contradictory metadata | Partial/failed coverage; never convert the failure into a negative finding. |
| Multiple exact customer identities or conflicting identity facts | Ambiguous identity; preserve candidates and block dependent attribution. |

HAL pagination uses `_links.next` and `page.number/size/totalElements/totalPages`.
Conversation lists normally have 25 results per page and other lists 50; do not infer
completion from a short page. Validate metadata, monotonic progress, deduplicated IDs, and
end-of-list agreement. Enforce finite page/item limits; reaching a limit is partial coverage.
Reject malformed links, credential-bearing URLs, fragments, unexpected parameters,
off-origin URLs, scope changes, resource changes, and loops before sending anything.
Refuse HTTP redirects, including to another allowed resource.
Missing unchanged scope filters in a valid next link are restored from the original
request. Changed filters are rejected. Conversation detail is re-read after its thread
pages; changed scope/state/history markers make coverage partial. This is not an atomic
source snapshot, and inaccessible/deleted records remain outside the completeness claim.
[Pagination](https://developer.helpscout.com/mailbox-api/overview/pagination/).

Bound retries and elapsed waits for transient server errors and 429 responses. Help Scout's
rate-limit wait header is `X-RateLimit-Retry-After` in seconds; the account shares a rate
limit with other users. Return a useful incomplete result when the retry budget is spent
or the required wait exceeds the configured bound. Do not retry authentication or access
failures. [Rate limiting](https://developer.helpscout.com/mailbox-api/overview/rate-limiting/).

Default bounds are 100 pages per traversal, 5,000 records per traversal, and 250 logical
GET requests per read. A request has at most three attempts, with at most five seconds per
retry wait and ten seconds total retry waiting. Longer server-directed waits return a
rate-limit/server error with the requested delay. Responses are capped at 2 MiB. The
15-second network timeout is per socket operation, not a whole-pilot deadline.

Diagnostics may preserve a validated HTTP status, safe error category, and bounded `logRef`
for support. Do not log request query URLs, rejected values, customer addresses, bodies,
subject/preview text, tokens, or raw response/error payloads. Error payloads can contain
input values, so useful errors must be projected onto a safe allowlist.
[Errors](https://developer.helpscout.com/mailbox-api/overview/errors/).

## Verification and remaining limits

Focused fake-HTTP tests must cover exact/ambiguous identity, multiple emails, unrelated
mailbox exclusion, author versus assignee, outbound exclusions, incoming associations,
timestamp precision, complete/looping/failed pagination, 401/403/429/5xx, expired credentials,
disabled live access, redirect refusal, and absence of credential renewal or external writes.
Runner tests additionally use fake snapshot/lease boundaries to prove that validation
precedes cache access, the lease covers the snapshot and read and closes on every path,
authoritative expiry and the 120-second margin are enforced, and summaries exclude secrets
and customer content. DPAPI/file primitives are mocked; no real connection is loaded.
Regression checks must establish that the existing DOI, draft-transfer, and Sales Credit
behavior is unchanged. Passing synthetic tests does not establish live API readiness.

The reader has no persistent evidence store or raw body logging. Review output still
contains sensitive source facts during an authorized live session; its caller must not
serialize those facts into Git or general logs. It does not retrieve attachments, verify
deleted/unavailable history, establish delivery, resolve every automated reply, or decide
commercial relevance. The reader and cached-only pilot have no UI integration, automatic
import, token issuance, or new persistent credential storage. The cached-only bridge reads
an existing approved snapshot after its ownership gates succeed. The separate
[single-owner coordinator](single-owner-pilots.md) adds source-only orchestration for two
bounded pilots and an independently gated one-token issuance capability. Its default live
path requires the original shared lock and explicit action-time authorization. Duplicate
checks report their accessible mailbox scope rather than claiming global draft absence.
