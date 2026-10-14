# ADR 0051: Verify an unsent reply through its documented customer association

Status: candidate correction. Existing live receipts are not upgraded.

Create Conversation delegates reply-thread fields to Create Reply. The required
reply customer identifies who is being replied to; it accepts the documented ID
or email representation. No To input is documented. Drafts use reply with
draft=true. List Threads documents customer as the conversation customer for a
message, and To as an email-header array, without promising a populated array for
an unsent draft. The exact request already supplies the customer correctly.

Requiring a populated To array unconditionally was an unsupported readback
assumption. Do not add an undocumented input or infer a wrong customer from an
empty draft header. An empty/omitted To array can verify only when both primary
and message customer objects have the same positive native customer ID and the
approved email. Explicit wrong, multiple, malformed or null To remains a hold.
Any returned contradictory customer association blocks even if To is correct.
The existing exact populated-To path remains available when no message customer
object is returned. The single-POST client's independent selected-customer ID
guard remains in place for both paths. No approval, copy, state, mailbox, author,
assignee, cc/bcc, scheduled, text/link or no-repeat-create condition is removed.

The mutation surface is unchanged: no recipient repair, send, additional reply,
customer update or thread update is added. Update Thread supports text and hidden,
not a To/customer recipient patch. A recipient repair mutation cannot be derived
from that contract and must not be invented.

Saved private pilot evidence does not contain the message customer object, so
this source correction alone cannot establish that pilot's new predicate or alter
its durable CREATED_UNVERIFIED receipt. Reconciliation needs actual retained
customer-association evidence before any verified status. Never recreate an
existing known conversation.

References: the official Create Conversation, Create Reply, Get Conversation and
List Threads links in [the API contract](../doi-draft-transfer.md#api-semantics-verified-against-official-documentation).

Tests: test_doi_draft_transfer_reply_customer.py proves the unchanged documented
request, known-ID binding, empty/omitted draft-header acceptance only with exact
customer evidence, unknown/malformed/mismatched identity rejection, contradictory
explicit recipients, other draft safeguards and GET-only re-verification.
