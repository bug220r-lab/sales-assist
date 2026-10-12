# ADR 0045: Coordinated cached snapshot for one read-only evidence pilot

Status: accepted for source implementation and offline verification; live test not run.

## Context

The user approved a minimal cached snapshot pilot runner for the standalone Help Scout
evidence reader. The lower-level reader already requires an explicitly supplied,
nonrenewing credential. A narrow bridge to the existing approved connection is useful
without adopting the draft-transfer issuing provider or competing with the cleanup owner.

This approval covers implementation and synthetic tests. It does not establish that
cleanup has completed, activate a credential, or authorize token issuance. The installed
daily app, saved reviews, cleanup process, connection configuration, and draft-transfer
runtime remain outside the build's change scope.

## Decision

Add a separate `pilot.py` runner with explicit `--live`, one exact `--email`, an approved
`.dpapi` `--connection-path`, an `--ownership` value of `cleanup-complete` or
`controlled-handoff-complete`, and `--confirm-sole-owner`. Validate every input and
attestation before any cache access. Help/default and synthetic demo paths remain offline.
No token or secret command-line argument and no environment/default-path credential
discovery is supported.

The credential owner must coordinate all consumers outside the runner. The ownership
flags record that operator attestation; they are not an inspection of cleanup state.
Acquire the existing fixed-user `SessionLease` before taking a snapshot, retain it for
the entire read, and release it on every path. The lease excludes only cooperating
providers. It cannot prove that an unrelated cleanup or other consumer has stopped.

`cached_auth.py` reuses only stable-file and read-only DPAPI primitives and never
instantiates a provider that can issue or refresh credentials. Require the existing
session-cache fields `client_id`, `client_secret`, `access_token`, `expires_at`, and
`user_id`; allow only the documented optional `grant_type`/`token_type` metadata. Verify
the fixed user `897275`. Project the access token and authoritative epoch expiry to
`SuppliedCredential`; convert expiry to UTC without modifying it or guessing a TTL.
Clear the decoded record and plaintext buffers/references after use. This is minimized
exposure, not a claim of guaranteed physical memory erasure.

Load one snapshot only. No reload, renewal, token issuance, cache write, or fallback is
allowed. Enforce a 120-second expiry margin initially and before every GET using the
transport's `expiry_margin_seconds=120`. Missing, malformed, expired or near-expiry
credentials stop the pilot. HTTP 401/403 stops further reads. Any separate token-issuance
request needs explicit approval and coordination by the credential owner; never weaken
expiry validation or inspect another process to make progress.

Fix the pilot to one email, mailbox `166170`, author `897275`, `max_requests=50`,
`max_attempts=1`, and `include_content=False`. The transport's socket timeout is not a
whole-pilot deadline; make no total wall-clock guarantee. Emit counts and safe codes with
explicit `DISABLED`, `BLOCKED`, `INCOMPLETE`, or `COMPLETE` status and
`credit_classification=NOT_EVALUATED`. Do not emit customer identifiers, message content,
cache paths, credentials, or raw errors. Preserve the reader's exact-scope GET allowlist,
pagination/redirect restrictions, and incomplete-coverage semantics.

## Consequences and verification

The core reader remains independent of cache discovery and credential renewal. This
bridge grants no ongoing access and creates no credential storage. It neither inspects
nor changes installed apps, processes, cleanup scripts, connection configuration, orders,
customer records, messages, or sheets. Existing Sales Credit and DOI business rules,
including the operational review horizon, remain unchanged.

Tests inject fake leases, snapshots, DPAPI/file behavior, and HTTP responses. Verify that
validation and lease acquisition precede snapshot access; denied or failed gates issue
no requests; every exit releases the lease; authoritative expiry/margin checks run before
requests; no refresh/reload/write is possible; and output contains safe counts/codes only.
Run applicable reader and existing regression checks without a real token, cache, or API.

The practical command example and API limitations are in
[Help Scout evidence reader](../helpscout-credit-evidence.md). No live pilot readiness is
implied by synthetic tests, and a successful traversal does not establish credit approval.
