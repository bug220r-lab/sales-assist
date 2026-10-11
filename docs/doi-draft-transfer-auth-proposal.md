# Proposed managed authentication lifecycle — not implemented or activated

The shipped `dpapi-cached-token` adapter is deliberately read-only and never renews.
This proposal does not change it, retry a stopped attempt, open credentials or call
an API. It describes a possible separately approved successor using an existing
approved connection, without a new OAuth application or grant.

## Protocol distinction

Help Scout documents two flows. Internal client-credentials integrations obtain an
access token using the existing application's ID/secret at `POST /v2/oauth2/token`.
That flow's documented token lifetime is two days, and replacement is requested
after expiry/401. Authorization-code integrations instead receive an access/refresh
pair and use the refresh-token flow for a replacement pair. Do not assume those
flows or stored credential fields are interchangeable. Establish the approved flow
from the credential owner's configuration, not by guessing or exporting secrets.
[Official authentication documentation](https://developer.helpscout.com/mailbox-api/overview/authentication/).

The following is a proposed local design, not a claim about existing coordination
or undocumented provider behavior.

## One issuer with explicit ownership

1. Leave authentication disabled until the existing credential owner confirms the
   renewal authority and all active consumers. An active cleanup process must be
   included in that assessment. A new lock used only by Sales Assist cannot protect
   a cleanup process that does not participate in it.
2. For the first implementation, wait for owner-confirmed cleanup completion or a
   separately authorized, controlled handoff. Do not stop, inspect process memory,
   borrow its token, or change its code/locks during this source-only work. No second
   issuer should be activated while ownership remains ambiguous.
3. In the approved session, one provider owns renewal. It loads the exact approved
   encrypted connection once under the existing Windows identity, performs only the
   declared flow, validates the bounded response, and holds tokens in memory. It
   never logs payloads/headers, exports credentials or writes the connection file.
4. Serialize concurrent callers within that provider. A longer-term shared issuer
   would need a reviewed authenticated local IPC boundary and participation by every
   consumer; a mutex declaration alone is insufficient. That is additional work and
   approval, not an invitation to use another process's current runtime token.

## Expiry, errors and writes

Use validated expiry for request admission. The existing 120-second safety margin
is a reason to hold a request, not proof that actual expiry has occurred. A successor
must distinguish margin hold from expiry and must not renew early solely because
the cached adapter reported its combined expiry/margin error.

After actual expiry or a qualifying 401, permit at most one coordinated token
request for that failure episode. Recheck token generation under the lock first so
concurrent callers cannot each issue a replacement. No unbounded retry, alternate
grant, new application, browser login or permission change is an implicit fallback.
A second 401, malformed response, denial, timeout or uncertain renewal stops the
episode for reconciliation. Do not assume whether issuing a replacement invalidates
another consumer's token; the cited documentation does not establish that behavior.

A known read-only destination GET can be retried once after an authorized successful
renewal. Never replay a draft POST automatically. Before-write auth failures remain
known no-write states requiring explicit application retry. An uncertain create or
known draft ID retains the existing journal lock regardless of token changes.

All consumers in a Help Scout account share its API budget. A 429 is a rate-limit
condition, not an instruction to renew; coordinate use and respect the returned
retry interval. [Official rate-limit documentation](https://developer.helpscout.com/mailbox-api/overview/rate-limiting/).

Process-memory operation does not persist a new cached token for another launch.
A persistent DPAPI cache or rotated refresh-token store would be a different design
requiring explicit approval for exact file writes, atomic replacement, recovery and
all-consumer coordination. It is excluded from this proposed first session.

## New approval needed before implementation is activated

The concrete request must name the existing approved connection and session scope:

> May I activate a separately reviewed, single-owner authentication provider for one
> isolated Sales Assist session, after the credential owner confirms cleanup has
> completed or an explicitly approved handoff is complete? It may read/decrypt only
> the named existing connection and, using its confirmed existing flow, request a
> replacement token from Help Scout after actual expiry or a qualifying 401. Tokens
> stay in process memory. It will not create a grant/application, persist credential
> settings or token files, borrow another process's token, modify cleanup, or retry
> a draft write automatically. It may then perform the two fixed destination GETs.
> Any draft creation remains subject to its existing exact-copy approval and all
> legitimate readiness/customer/duplicate gates; no send or order change is included.

Approval of the earlier cached-token read does not authorize this token POST. This
request is a proposal only; no renewal approval has been received or acted upon.

Required mocked acceptance cases before release: disabled mode/no credential access;
correct declared flow; margin versus expiry; concurrent one-issuer behavior; cleanup
ownership unconfirmed; malformed/denied/timeout/second-401 stops; 429 without renewal;
no token/header leakage or file writes; fixed GET retry bound; and preservation of
known/uncertain draft IDs with no automatic create retry.
