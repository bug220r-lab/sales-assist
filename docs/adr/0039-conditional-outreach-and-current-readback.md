# ADR 0039: Explicit customer decision and current readback

The customer decision about changing an order is distinct from the reviewer's approval
to create the exact Help Scout draft. A conditional email may ask for that decision
while it is still pending. The old generic customer-approval checkbox made this
distinction unclear and required every check to be marked resolved.

Keep the existing private review key `checks.customer_approval`, but replace its
generic resolved checkbox with an explicit decision: `unreviewed`,
`pending_conditional_outreach` or `approval_recorded`. Pending outreach requires
evidence and a separate attestation that the exact copy asks for a decision without
claiming approval or an order change. Recorded approval requires its own evidence.
This review binds to the same immutable version and exact-draft approval as all other
evidence. Copy changes reset it; decision/evidence changes invalidate prior approval.

Older persisted resolved/evidence objects remain readable, with a customer-decision
hold. The UI defaults them to unreviewed and retains their historical evidence.
They must be explicitly reviewed using the new fields; old checkboxes never imply
recorded customer consent. No bulk conversion or automatic data migration occurs.
Identity, recipient verification, withheld copy, prohibited order status and complete
listed-cart scope remain hard gates. No order-modification or send API exists.

Every Help Scout verification describes the current GET result. Before reading, reset
the result to `CREATED_UNVERIFIED` / `DRAFT_READBACK_REQUIRED` and `retry_allowed=false`,
retaining its known conversation ID and operation identity. Only a successful exact
readback restores `DRAFT_CREATED_VERIFIED`. Published or changed content, deletion,
non-success HTTP, malformed response and transport failure all leave it unverified.
Both states preserve the duplicate-create lock across reopens and restarts.

Executable coverage: conditional decision, legacy review, hard gates and approval
invalidation in `tests.test_doi_draft_transfer`; sequential readback adapter and
durable no-retry checks in the same suite; explicit pending-decision frontend flow
in `tools/check_draft_transfer_frontend.mjs`.
