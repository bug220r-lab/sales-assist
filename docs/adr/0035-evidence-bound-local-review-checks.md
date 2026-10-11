# Local checks for split review

Status: accepted for the owner-approved local workday update.

## Decision

The normal app passes a fixed 36,000-second lifetime to its CSV review session.
Only successfully loading a pair starts a new deadline. Reads, sorting, filters
and attention-marker writes never renew it. The independent 24-hour capture-age
warning and every evidence, ownership and fulfillment rule stay unchanged.

Reviewed for split is attention metadata only. A companion endpoint leaves the
existing review v5 contract unchanged. A check never authorizes a split, makes an
order eligible, confirms allocation, or records fulfillment.

The app supplies one fixed `doi-reviewed-split.json` file under its existing
user-local data directory. Nothing is written to source, exports or customer CSVs.
No browser storage, sharing, new dependency or settings system is introduced.
The file contains a schema, integer revision and pairs of SHA-256 hashes only:
one domain-separated canonical order-key hash and the latest checked evidence
hash. It contains no raw order IDs, email, CSV bodies or capture text. Hashes are
identity binding, not encryption; the file remains private local app state.

The evidence hash covers exact summary and line capture fields, including
timestamps, stock, quantity, identifiers and provenance. Customer email is
excluded because it is unrelated to split review. Lines are sorted before
hashing so CSV row order cannot move checks. A new capture timestamp or changed
evidence produces an unchecked, visible `Evidence changed - review again` state.
Only the latest checked evidence is retained for an order, not a historic audit
log. Unchecking removes the saved entry; checking changed evidence replaces it.
Duplicate/conflicting IDs and global quarantine cannot be checked.

Clear, expiry, failed load and service stop remove only the temporary review.
They do not erase saved markers. Reloading the same pair restores matching
checks. The UI states these semantics before the controls and keeps changed,
ambiguous or unavailable records visible when Hide reviewed is selected.

## Storage and concurrency

The existing per-data-directory process lease and single-threaded HTTP server
supply one application writer. An independent storage revision rejects stale
tabs; the existing session revision and exact evidence hash reject outdated
capture requests. Existing same-origin, CSRF, loopback and body-size controls
apply to both companion routes. No cross-user path is accepted from the UI.

Writes use exclusive random adjacent temporary files, flush/fsync and atomic
replacement. Paths reject symlinks/reparse points, linked files, relative paths,
remote paths and unexpected filenames. No permission repair is attempted.
The store is bounded to 10,000 entries and 2 MiB; corrupt, inaccessible or full
storage fails closed. No checkbox is reported saved without server confirmation.
Failed marker operations preserve the imported review and its fixed deadline.
External edits by arbitrary processes are not a supported concurrency model.

## Executable evidence

`tests.test_doi_session_workday`, `tests.test_doi_review_marks` and
`tests.test_doi_review_mark_store` cover time boundaries, unchanged eligibility,
reopen/reload/clear/expiry, changed captures, order and line reordering, ambiguous
IDs, stale revisions, private field minimization, actual hash-only file reopen,
atomic write failure, malformed storage and guarded HTTP transport.

Frontend checks execute the shipped handlers against fictional payloads. Browser
screenshots verify the existing GUI's tokens, controls and compact worklist;
they do not establish a real customer CSV import succeeded.
