# ADR 0037: Local, evidence-bound alternate-email drafts

Add a focused editor to each order in the existing DOI review worklist. The CSV
endpoint and its closed projection remain unchanged. A separate authenticated
localhost endpoint accepts a bounded structured entry for one selected alternate
per order. It generates deterministic short prose; no paid model, credentials,
mail transport, ticket writes, order mutations or remote lookup are added.

The selected order must exist in the current review revision. The subject uses
that native order number. Recipient email is always null and send_ready is always
false. Draft readiness is a human-review workflow state, not send approval or a
business eligibility result. The original rep gate cannot be overridden by a form
checkbox. Technical conflicts remain HELD_TECHNICAL_REVIEW. Other missing facts
remain HELD_CANDIDATE; otherwise the state is READY_FOR_HUMAN_REVIEW. Fitment,
ownership, quantity, kit scope, allocation, stock, finish and price checks have explicit
review states and evidence notes. Original capture checks remain visible separately.
Unknown split eligibility is never expressed as cannot-split.

Use reviewed exact line IDs and source quantity wording, product ID and reviewed
alternate quantity, dated stock observations, and material/brand/scope differences.
These are explicit reviewer entries, not facts inferred from stock or raw counts.
Product links require an exact HTTPS ECS/Turner URL and recorded content verification,
including a source/reference, observation time and verifier kind (supported research
tool or human review). Existing tool verification does not require another manual check.
The app never claims it has visited a link. Optional cart URLs must be pasted with
recorded tool or human verification. The recognized single-product ECS Cart schema
must match the recorded product ID and positive whole quantity. Customer-specific
quantity/kit-scope checks remain separate holds and do not negate verified cart contents.
Other cart formats/contents remain held and are omitted from the
customer body. No cart is constructed, and the supplied schema example is never reused.

The editable body is plain text. Exported HTML escapes all entered text and turns
only exact verified product/cart URLs and the fixed CTA into links. Unverified URLs
in edited prose are rejected. The immutable subject and signature are added by the
renderer. Edited wording requires a human review check; regeneration retains edits,
invalidates their review, and requires preview. Selecting another order while edits
are unsaved keeps the current editor open until saved or explicitly closed.

Both held and ready drafts can be copied for Jude's review; the status stays visible
and copy/export never grants send approval. Review packets include internal checks
outside the customer body. Clipboard operations happen only on explicit clicks. HTML exports
contain no script, remote resources, recipient address or sending action.

Persistence is a separate doi-alternate-drafts.json in the existing owned local data
directory, never in the source repository or package. It stores an order hash,
capture evidence hash, structured product review, edited body and update time; it
does not automatically retain contact data or raw captures. This new store contains
user-authored prose and is distinct from the hash-only reviewed-checkbox store.
The editor tells users not to add personal data. Save is explicit. Clear, expiry and
restart do not delete drafts. Delete saved draft is explicit and affects only this
store. Capacity is 500 drafts and 4 MiB total, with 32 KiB request and 256 KiB response
bounds. No permission repair, recursive cleanup or silent eviction is allowed.

The existing single-process lease remains the sole writer boundary. Store revisions
reject stale tabs; identical repeated saves do not increment the revision. Atomic
replace/fsync, duplicate-key/schema validation, local-path and symlink/reparse/hardlink
checks prevent partial or redirected writes. Storage errors preserve existing bytes
and allow preview without claiming a save. Existing reviewed markers and review TTL
are untouched. Ambiguous capture identity permits only held preview, not persistence.
Changed capture evidence retains the original saved record and exact edited wording,
clears order-specific confirmations, and exposes prior wording for reference. Recorded
product/cart-content evidence remains reusable, with its source and observation time;
it never transfers customer-specific fitment, quantity or price approval.

Executable coverage: tests.test_doi_alternate_drafts plus the existing DOI response,
ownership, session and reviewed-marker regressions. A separate synthetic DOM harness
exercises the shipped editor through real localhost HTTP, including clipboard and
HTML download stubs. Supported Chrome visual/clipboard QA is separately required.
