# ADR 0049: Customer association within the one approved draft POST

Status: accepted for source review; live activation remains separately gated.

Help Scout accepts a customer ID or email on a new conversation. Supplying an
email associates an existing contact or creates the underlying contact if missing.
A separate customer-creation POST is not required for draft transfer.

The existing review screen discloses this contact side effect beside the exact
row approval. CSV import and approval remain per row, with unchanged recipient,
copy, cart, version, mailbox, assignee and durable transfer claims.

The default coordinator still requires an existing exact customer. A separately
authorized --allow-email-customer applies only to its one approved bundle.
Global email identity lookup must finish without ambiguous matches. An absent
identity also requires complete all-status email conversation pagination in the
fixed mailbox. Any existing email conversation with unresolved identity blocks;
drafts, matching orders, incomplete coverage and metadata conflicts still block.
Only a genuine sealed preflight authorizes the email payload. It preserves the
single conversation POST, reply draft=true, no auto-reply, durable reservation,
unsent readback and no uncertain-outcome retry. No customer POST capability is
added to the client.

An operator may instead supply --known-customer-id for an explicitly verified
handoff. Fresh direct customer and email GETs must match the approved recipient.
The normal customer-scoped mailbox conversation and complete thread checks then
run. This avoids search-index rediscovery of a newly created known ID. A failed
direct verification never falls back to email creation. The two modes are
mutually exclusive, and all invalid selections block before ownership or auth.

Customer search is global by exact supplied email query; the API search itself
is a contains search, so every candidate still needs exact email verification.
Mailbox filtering remains mandatory for conversation reads. These are bounded
accessible-result snapshots, not atomic or global historical absence guarantees.

Existing ID execution bindings remain unchanged. Email association records the
explicit implicit-contact-creation authorization in execution review provenance.
Source approval and copy are not rewritten.

The same original cleanup byte lock, SessionLease and one ephemeral authentication
snapshot cover identity checks through draft readback. Neither mode persists
credentials, sends email, creates other contacts, runs cleanup, or activates an
installed app.

References:

- [Verified API contract and official endpoint references](../helpscout-credit-evidence.md#api-contract-verified-on-2026-10-12)
- [Action-time ownership and draft safeguards](../single-owner-pilots.md)

Tests: test_sales_credit_evidence_email_customer.py covers both selection modes,
exact identity, duplicate and ambiguous results, incomplete coverage, forged
email authority, unchanged unsent payload, uncertain POSTs, readback and review
disclosure. The existing durable-transfer and coordinator suites remain required.
