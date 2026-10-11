# ADR 0038: Version-bound, draft-only Help Scout transfer

The user explicitly requested CSV draft import, per-draft review and approval, and
Help Scout draft creation. This is a bounded new production adapter, separate from
the synthetic domain engine, older DOI observation flow, and support cleanup tools.
It supersedes the old blanket no-connector rule only for this adapter. Existing
business evaluations, localhost listeners, browser permissions, checks and drafts
remain unchanged. Sending, publishing, existing-conversation status mutations,
customer contact discovery, and new OAuth grants are outside this implementation.

`doi_draft_transfer` preserves source cells verbatim, including exact UTF-8 body
hashes. CSV data is not authority: imported recipient verification, review approval,
and send-ready values remain source claims. The selected body alone is previewed;
all 34 final contract fields, including pre-cart history, source provenance and prior
Help Scout references, are retained. Local duplicate reconciliation is mandatory;
an existing draft blocks creation. Empty selected strings have their exact SHA-256.
There is no original-body fallback. Preview is ephemeral and expires after 30
minutes. Cancel discards it. Explicit merge adds new orders, preserves local edits,
and reports conflicts against a global store revision. It does not bulk approve.

Approval binds the complete current row, local version, selected body hash,
recipient, fixed mailbox/author, rendered HTML and recorded review. Changes clear
approval; body changes also clear all local verification. Recipient changes clear
recipient verification. Original text, source quantities and rich-text runs are
preserved in immutable versions. Withheld copy, blocked ownership, shipped/canceled
orders, unknown identity, incomplete full-kit scope and missing carts stay held.
Every required check and cart requires explicit reviewer evidence before approval.
Customer decision has its own explicit review: pending conditional outreach or recorded
approval with evidence. Pending outreach requires review of the exact conditional copy;
it does not require customer consent before asking for it. See ADR 0039.

The private `doi-draft-transfer.sqlite3` is separate from both prior review stores
and the synthetic database. It lives under the existing owned data directory,
outside Git. Transactions use BEGIN IMMEDIATE and FULL synchronization. Imported
versions and a chained event journal retain review history; event records contain
hashes and results rather than copies of email bodies. Exact copy and recipient are
necessarily retained in private row versions. No secret is stored in this database.
Storage is bounded to 500 orders, 20,000 audit events, and 256 MiB, without eviction.
Corruption, links/reparse points, invalid paths and denied access fail closed.

A durable per-order reservation is committed before the HTTPS write. Duplicate
clicks, processes, and service restarts therefore cannot repeat that create.
Successful or uncertain writes freeze the row. 401/403, explicit rejection and
rate-limit responses require a deliberate retry, with the same operation identity;
429 honors its cooldown. Timeouts, disconnections, 5xx, redirects and ambiguous
responses never auto-retry. A post-write storage failure leaves the prior durable
reservation locked. There is no claim of remote exactly-once delivery: Help Scout
does not document a create idempotency key. Unknown outcomes require independent
human reconciliation, never a blind retry or journal deletion.

The only write endpoint is conversation creation with one `reply` thread and
`draft: true`, `autoReply: false`, explicit user/assignee, and the approved recipient.
No generic request proxy exists. HTTPS host/path/method are closed, redirects and
automatic retries are absent, and responses are bounded. Returned identifiers and
web links are retained; readback checks draft state, recipient, destination, exact
subject/body and author before reporting verified creation. A failed readback is
CREATED_UNVERIFIED and still blocks another create. Every subsequent readback first
clears earlier verification; a failed read or changed remote draft cannot retain a
verified result. Readback never mutates remote status.

Credentials are server-only and opt-in through existing operator-managed secret
injection. No token/grant is installed by the code, tests, packaging, or this change.
The default client is disabled. Tests mock every Help Scout operation and use only
obvious dummy fixtures. Browser requests remain same-origin and CSRF protected;
customer copy is text/escaped HTML, never executable markup. The application has
no customer-send route or control.

Executable coverage: `tests.test_doi_draft_transfer`,
`tests.test_doi_draft_transfer_http`, and `tools/run_draft_transfer_frontend.py`.

Repository source scanning allows only reviewed public links and synthetic rejection fixtures by exact file, category and SHA-256. New or changed literals still fail. Authored DOI UI assets carry the existing source marker within explicit module roots. Independent secret scanning continues across all files; these source entries grant no runtime network permission.
