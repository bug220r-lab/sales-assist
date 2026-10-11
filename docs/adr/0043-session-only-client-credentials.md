# ADR 0043: Explicit session-only client-credentials renewal

Status: accepted for source implementation; private activation remains disabled.

The connection owner's source establishes a five-field client-credentials record,
while the existing Sales Assist adapter deliberately stops at cached-token expiry.
Support that known shape in a separate provider without changing the cached mode,
copying the owner's implementation, writing its cache, or coupling to cleanup.

Require both process-only renewal opt-in and a completed-cleanup/handoff attestation.
Acquire a global Windows named mutex object scoped to the fixed integration user,
with no initial ownership, and reject
ERROR_ALREADY_EXISTS. The accepted handle's lifetime is the exclusive session lease;
this does not depend on the HTTP worker thread releasing mutex ownership. All denied
extra handles close immediately; process death releases the accepted handle. No
lock file, ACL change or credential-directory write is required. The fixed user
scope also covers connection-path aliases without reading credential metadata. Other consumers
must be stopped or handed off by their owner; this lease cannot coordinate code
that does not participate. Do not infer cleanup state from the attestation alone.

Within the provider, a thread lock protects loading, generation and issuance. Reserve
at most one token POST for the entire session before sending anything. Actual expiry
or a matching-generation 401 permits it; the 120-second margin alone does not.
Ignore delayed old-generation 401s. Reject ambiguous grant fields and malformed
identity or response values. Use only fixed HTTPS host/path and a bounded response.
Never follow redirects, switch grant, retry a token POST, persist tokens or reload.

Only GET is eligible for one retry. Return a draft POST's first result, including
401 or uncertainty, to the existing durable workflow. A later explicit action can
renew after a known 401. Readback failure retains its known draft ID. A rejected
replacement or exhausted issuance allowance is terminal. Release the lease and
clear provider references when the dedicated runtime closes.

The design leaves existing CSV, ownership, recipient, cart/factual, approval,
duplicate and unsent-only behavior intact. No daily policy change is needed.

Acceptance: tests.test_doi_session_auth plus existing transfer/auth/HTTP/launch
suites. Native lease tests use synthetic names and self-owned child processes;
credential decryption and network are mocked. No live readiness is implied.
