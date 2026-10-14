# DOI v7 daily source

This source adds local DOI CSV review to the reviewed Windows application baseline.
Application version remains 0.2.0. The v7 label identifies the reviewed DOI behavior.
No release, deployment or acceptance of a new distribution is implied.

The DOI page groups eligible, excluded and held records with explicit ownership and
USD provenance. Currency conflicts remain visible for review and excluded from the
default eligible list. Apparent split candidates are observations for human review,
not confirmed fulfillment decisions. Import the summary and component CSV pair
manually. Imported review state stays in memory and expires 10 hours after loading;
refresh does not extend expiry. Clear or service shutdown removes the session.

Reviewed for split records attention only; it never approves a split or fulfillment.
Checks are saved privately in the app's existing local data directory. Clear, expiry
and restart keep them. Reloading the same evidence restores them; changed evidence
requires review again. Uncheck to remove a saved check. Hide reviewed hides only
confirmed matching checks; ambiguous records or storage errors stay visible.
The saved file contains hashes only, with no email, source text or raw order IDs.
Use the same owned data directory when reopening to retain these checks.

The broader review-leads view also exposes held ready/waiting observations while retaining
their original rep/capture and fulfillment holds. Stock-counter clues have a separate filter
and never establish allocation or partial-split eligibility. Keep Hide reviewed selected to
exclude completed checks across these views. See [Finding additional orders to review](../split-review-discovery.md).

The normal package builders now include the daily policy helper, setup recipe,
required migrations and generic instructions. They generate fresh source identities
and inventories from the requested commit. The private delivery's manifests and
runtime archives are not source inputs. This PR does not build or publish a release.

Read [PRIVATE_CONFIGURATION.md](PRIVATE_CONFIGURATION.md) before any separately
authorized manual launch. START requires an approved external policy. STATUS and
STOP preserve their owned-process checks even if that policy becomes unavailable.
Port 8905 is a candidate with the existing safe loopback fallback behavior.

No CSV, customer data, policy decisions, credentials, receipts or runtime database
belongs in this repository or a distributable archive. The separate Help Scout
closer and its successor are outside this source change.

Manual acceptance on a separately approved disposable installation should confirm:

1. Required configuration rejects missing, invalid, changed or mismatched policy.
2. START opens DOI review and repeated START reopens only its matching owned service.
3. Synthetic CSV ownership scopes, USD provenance and conflicts reconcile correctly.
4. Refresh retains an unexpired session; stale revisions, Clear and expiry behave safely.
5. STATUS/STOP remain available after invalidating policy; STOP affects only its service.

These steps are an acceptance checklist, not a claim they have been completed on
the sanitized package or permission to access private captures.

## Bounded larger DOI imports

The DOI review response limit is 4 MiB. The serializer, DOI state/load/clear HTTP
responses and browser's streaming reader enforce the same bound. Other portal
response limits remain unchanged. Input files are at most 4 MiB and 5,000 records
each, with at most 1,000 joined orders and a 16 MiB JSON request bound. The backend
and browser file/order guards share these bounds. Very dense captures may still need
smaller matching pairs. A rejected load clears only the transient displayed
review; saved evidence-bound checkboxes remain in their separate store. See ADR 0047
for the bounded input update and its synthetic regression checks.
# Alternate email drafts

Use **Alternate email** beside a captured order to open the structured editor.
Enter the exact purchased-line and quantity observations, reviewed alternate ID,
quantity, observed stock wording/date, differences, and exact product link. Record
fitment, ownership, quantity, kit, allocation, stock, finish and price checks separately.
Use recorded supported-tool or human verification with its source and observation time;
already verified product/cart links do not need another manual check. An optional cart
must be pasted with recorded content verification; the app never creates it.

Generate a short draft, preview edits, and explicitly save locally. Regeneration
keeps edited wording. Held candidates and technical conflicts retain visible internal
checks outside the customer body. Held and ready drafts can both be copied for Jude's
review; review-packet copy/export includes the internal checks separately. Copy/export
never approves sending. There is no recipient lookup or send function.

Saved drafts survive review Clear, expiry and service restart in the separate local
`doi-alternate-drafts.json` store. They do not modify Reviewed for split. New capture
evidence clears order-specific confirmations; product/cart-content verification and
exact edited wording remain available with their recorded sources/times. Save or
explicitly close unsaved edits before selecting another order.
Do not enter customer names, addresses, emails, payment information or other personal
data in the editor. See ADR 0037 for limits and persistence behavior.
