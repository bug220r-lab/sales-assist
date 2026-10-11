# ADR 0040: Opt-in cached Windows DPAPI authentication

The draft adapter previously accepted only an operator-injected process access token.
An existing approved Windows connection cannot be reused through that interface
without a separate injector. The authorized development scope adds a compatible
local reader, tested with synthetic data and mocks; it does not activate access.

Keep transfer disabled by default. The existing `access-token` mode remains available.
The explicit `dpapi-cached-token` mode accepts an operator-approved absolute local
`.dpapi` path through the process environment. Reject ambiguous modes/token inputs,
remote or device paths, mapped drives, reparse components and changing/oversized files.
No real account directory, customer row, recipient, copy or connection is bundled.

Construction is lazy. Only an explicit access check or approved transfer requests
the token. Use Windows CryptUnprotectData with UI forbidden, no optional entropy,
and system DLL loading. Never invoke protection, token exchange, refresh, login,
fallback authentication, a subprocess or the existing cleanup implementation.
Decryption and file access require separate activation approval for the exact path.

Retain only a valid ASCII bearer token and finite numeric expiry from bounded JSON.
Reject duplicate keys and treat the last 120 seconds of validity as expired. Serialize
concurrent callers so a process reads at most once. Any load/expiry failure is terminal
for that provider instance; later calls neither reload the file nor renew a token.
Clear native plaintext before freeing it and clear the mutable decoded buffer.
Python does not guarantee erasure of all transient string copies; this is process
isolation and data minimization, not a secure-memory guarantee.

Local authentication failure before HTTP is a known no-write `AUTH_REQUIRED` result,
not an uncertain write. The durable operation still requires explicit retry after
approved setup. Expiry during readback leaves the known conversation unverified and
preserves its no-create-again lock. HTTP 401 never triggers renewal. Existing fixed
mailbox/user, request allowlist, draft-only write and exact-version approval remain.

Executable coverage: `tests.test_doi_draft_transfer_auth` covers lazy/no-access startup,
mode ambiguity, validity boundaries, cached failure, bounded/denied file access,
concurrency, redacted errors, synthetic filesystem and mocked native decryption,
GET-only checks, no renewal on 401, and no HTTP on local authentication failure.
`tests.test_doi_draft_transfer` covers durable retry and known-ID protection.
