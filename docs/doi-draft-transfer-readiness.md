# Conditional draft readiness: what each gate means

This is a source audit, not evidence that any private row is ready. Operator approval
of exact conditional copy, customer permission to change an order, authentication,
local launch configuration and factual review are different inputs.

## Current behavior

| Gate | What the implementation actually requires | Effect on conditional outreach |
| --- | --- | --- |
| Customer decision | `pending_conditional_outreach`, evidence and explicit review that the copy asks for a decision without claiming consent/order changes | Recorded customer consent is not required to ask the question. The generic old customer checkbox cannot substitute for this explicit choice. |
| Facts | Each non-customer review has `resolved=true` and nonblank evidence/acknowledgment | This is a review disposition, not necessarily an assertion that every fact is known. An appropriately qualified unknown may be acknowledged without inventing fitment, allocation, stock, price or remaining quantity. The operator must actually make and document that disposition. |
| Identity/ownership/status | Eligible exact rep, nonterminal observed order, purchased-line scope, recipient provenance and review | Conditional wording does not identify a recipient or prove ownership. These gates cannot be inferred from generic copy approval. |
| Recipient age | Review flag and provenance; no automatic freshness cutoff | Historical order-bound evidence must be described as historical. It is not proof of a fresh lookup; the code does not itself demand or establish one. |
| Cart | Structured option/component mapping, exact cart IDs/quantities, separate verified cart evidence and timestamp | Asking whether to explore an option does not prove what its cart contains. Do not manufacture cart validation from URL syntax or a product label. |
| Existing draft | `no_existing_draft` plus reconciliation evidence | An empty new local store proves only that this store has no prior operation. It does not prove remote absence. Known IDs or uncertain writes remain protected. |
| Existing customer | No customer lookup endpoint in this adapter | The create payload identifies a customer by email and may create a new customer record. If that additional effect is not approved, establish existing-customer evidence through an authorized workflow before creation; do not assume it. |
| Exact draft approval | Current row/review/version/rendered-HTML binding and explicit operator action | Customer consent can remain pending, but the exact intended draft still needs its own current binding. Editing or a changed renderer can invalidate it. |

`row_holds`, `review_holds`, `fresh_review` and `validate_review` are in
`src/doi_draft_transfer/contract.py`. They do not analyze prose to infer facts or
silently clear checks. `DraftTransferService.approve/transfer` enforce the resulting
holds and commit a durable reservation before any possible external write.

The UI explicitly labels review notes **Evidence / explicit acknowledgment**. For
example, a synthetic review can truthfully acknowledge that allocation is unknown
and that the exact conditional copy makes no allocation promise. That must not be
rewritten as confirmed allocation, and it does not waive a missing required cart,
unknown identity or incomplete purchased-line scope. The link regression tests
cover both acknowledged unknowns and unresolved checks remaining held.

## The private-launch dependency is a separate integration constraint

`scripts/start.ps1` invokes `tools/daily_policy.py check` before starting the normal
application. The checker requires an external `doi-private-launch.json`, a reviewed
confirmation-file hash and a count of one through ten decisions. It validates paths,
the hash and the count, then uses `doi_csv_staging.review_policy.parse_owner_confirmations`.

That parser reads `doi-owner-confirmations/v1`: exact summary/line CSV hashes and
record-bound `ConfirmedOtherRep` decisions. Their `match` method applies only to
`REP_UNMAPPED` exclusions. These are not customer approvals and are not permission
to create a conditional email. A positive approval of one draft cannot truthfully
be converted into an unrelated negative rep-confirmation record.

The normal launcher retains those daily requirements. A separate, disabled-by-default
[draft-only mode](doi-draft-launch.md) now supplies the appropriate configuration
boundary: a dedicated private root, fixed account targets, a narrow route set and
separately disabled transfer. It never creates or consumes other-rep decisions.
Its review mode does not construct authentication or touch the old DOI stores.

The existing Host/Origin/CSRF, process lease, durable duplicate journal and exact
row-approval protections remain enforced. Private use still requires explicit local
configuration and real row evidence; source implementation is not activation approval.

## What this source change resolves

Labeled links now render as ordinary hyperlinks in outbound drafts and in the saved
preview, while preserving source text and exact destinations. Readback checks the
visible text and link spans. Old rendered approvals become pending until explicitly
approved again. This resolves a presentation/verification defect; it supplies no
private activation, recipient lookup, factual review, cart inspection, customer
existence check, duplicate reconciliation or usable token.
