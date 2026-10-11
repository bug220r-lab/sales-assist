# Session-only client-credentials authentication

The compatible renewal provider is implemented but disabled. No live credential
access, token request or private activation was performed while developing it.
The existing `dpapi-cached-token` mode is unchanged and never renews.

## Flow established from the credential owner's source

Read-only inspection of the owner's `connect_server.connect` and
`helpscout_client.Client._renew` established the existing client-credentials flow.
The connection writer stores `client_id`, `client_secret`, `access_token`, numeric
Unix `expires_at`, and `user_id`. It does not store a refresh token or grant-type
field. The owner source calls the client-credentials token endpoint and persists
its updated cache. Source hashes and inspection evidence are retained privately;
no owner implementation, credential values or machine paths are published here.

The new provider independently supports that exact legacy shape, with optional
`grant_type: client_credentials` and `token_type: bearer`. It verifies the fixed
user identity. Unknown fields, refresh-token fields, a different grant, duplicate
JSON keys or malformed values stop before token HTTP. It does not guess another
flow or fall back to login, another connection, a new application or grant.

The request and response match the documented client-credentials flow.
[Official authentication documentation](https://developer.helpscout.com/mailbox-api/overview/authentication/).
There is no remaining request for the user to identify the OAuth flow.

## Scope and ownership

Use only the dedicated draft-only launcher, a new private root and the exact
previously approved connection. Before activation, the credential owner must
confirm cleanup is complete or a controlled handoff is complete, including any
scheduled consumers. Do not stop cleanup, change its code or permissions, inspect
its memory, borrow its runtime token, or assume a Sales Assist lock coordinates it.

The provider requires an explicit process-only ownership attestation. Before any
credential read it atomically acquires a Windows named-object lease for the
fixed integration user. This covers alternate path spellings, hard-link aliases
and different private roots without opening any file to compute the lease key. An existing object or access denial stops
startup of authentication. The sole accepted handle remains open for the session;
closing the provider or process death releases it. This excludes cooperating Sales
Assist providers across processes and private roots. It does not prove external
cleanup inactivity; the owner-confirmed handoff is a separate required gate.

The provider reads/decrypts the connection once under the existing Windows user.
It retains credentials and tokens only in process memory, clears mutable plaintext
buffers, and discards application credentials after the single issuance attempt.
Python strings are not a secure-memory guarantee. It never calls a credential
protection/write API, writes a token/cache/configuration file, or reloads the cache.
The new token is lost when the session ends. A later session requires its own
approved setup and may encounter the unchanged old cache.

## Renewal and failure behavior

A cached token outside the 120-second margin is used unchanged. Entering the margin
returns `HELP_SCOUT_SESSION_TOKEN_MARGIN_HOLD` without renewing. A later explicit
action can renew after actual expiry. A qualifying API 401 may also trigger renewal.

At most one token POST is allowed in the entire session. The attempt is reserved
under a thread lock before network activity. Concurrent callers share the resulting
token; a delayed 401 for an old token cannot invalidate a newer generation. The
only token endpoint is the fixed HTTPS `POST /v2/oauth2/token`, with the existing
client ID/secret and `grant_type=client_credentials`. Redirects are not followed.
Responses and lifetimes are bounded and validated; unexpected grant material stops.

A permitted GET may retry once after that renewal. A draft POST is never retried
automatically: its 401 is returned as the existing known-no-write auth result, and
only a later explicit action may obtain a token. Known draft IDs and uncertain
writes retain their existing durable no-repeat locks, including readback failure.
A second 401, later token expiry, denial, redirect, malformed response, timeout or
uncertain issuance ends renewal for that session. No token or response is logged.

A 429 does not cause renewal or an automatic retry. Token-endpoint 429 stops the
session attempt; draft endpoint rate-limit handling remains unchanged. Coordinate
account use with the owner because consumers share its API budget.
[Official rate-limit documentation](https://developer.helpscout.com/mailbox-api/overview/rate-limiting/).

## Exact activation handoff after source validation

Default review mode does not construct authentication. To request renewal in a
separately approved dedicated session, its private launch configuration must have
`enabled: true` and `allow_draft_create: true`. In that process only, configure:

- `SSA_HELPSCOUT_DRAFT_TRANSFER=1`
- `SSA_HELPSCOUT_AUTH_MODE=dpapi-session-client-credentials`
- `SSA_HELPSCOUT_DPAPI_AUTH_PATH` = the exact approved existing connection path
- `SSA_HELPSCOUT_SESSION_RENEWAL=1`
- `SSA_HELPSCOUT_RENEWAL_OWNERSHIP=cleanup-complete`, or
  `controlled-handoff-complete` after that handoff is actually confirmed

Do not set `SSA_HELPSCOUT_ACCESS_TOKEN`, persist environment settings, enter secrets
in chat or command arguments, or change execution policy. Wrong/combined modes and
missing ownership fail before reading credentials. Configuration validation and
startup are lazy and do not prove credential compatibility or live API acceptance.
Stop on any path, lease, schema, identity or access error; do not bypass it.

The bounded additional approval is:

> Authorize one isolated Sales Assist session to read/decrypt the exact existing
> approved connection and, using its source-confirmed client-credentials flow,
> make at most one token replacement request after actual expiry or a qualifying
> 401. Confirm cleanup and scheduled consumers are finished or their controlled
> handoff is complete and Sales Assist is the sole renewal owner. Keep all tokens
> in memory and write no credential files. Perform only the two fixed mailbox/user
> GET checks first. No draft POST is included in this access check; any later
> approved draft still requires its unchanged readiness and exact-copy gates.

The shipped source needs no new grant or user-supplied OAuth choice. This approval
is for actual credential use and token issuance, not further source development.
It has not been received or executed as part of implementation. Live compatibility
and current credential validity are untested until the separately approved check.

Mocked acceptance covers default/lazy behavior, the source schema, ambiguous-grant
rejection, margin versus expiry, one concurrent issuance, terminal failures, one
GET retry, no automatic draft replay, and retained known/unknown-write outcomes.
Windows synthetic tests verify same-process and cross-process lease exclusion and
release on process death. Test counts and package identity are in the build handoff.
