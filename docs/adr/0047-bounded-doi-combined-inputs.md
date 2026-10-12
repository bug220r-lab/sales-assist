# ADR 0047: Bounded combined DOI CSV inputs

The previously tested larger response projection supports a longer daily worklist,
but its 500-order and 1 MiB CSV input gates reject larger matching capture pairs.
Carry the tested daily input limits into the consolidated source: 1,000 joined
orders, 4 MiB UTF-8 bytes per CSV, and a 16 MiB JSON request body. This supersedes
only the input values recorded in ADR 0036.

The Python constants supply the backend checks, rendered limit hint, and extracted
JavaScript's file and order guards. Keep the existing 5,000-record limit per CSV,
4 MiB response and streaming-reader bound, ten-hour portal review session, closed
schemas, source minimization, eligibility rules, and saved-state behavior.

Larger input bounds do not guarantee every dense projection fits the response
bound. Reject oversized inputs and responses without truncation. Failed loads
clear the transient review and preserve separate durable review checks and drafts.

Executable checks: `tests.test_doi_combined_limits` tests exact/oversized UTF-8 CSV
bytes and JSON bodies, the 1,001-order rejection, unchanged record cap and malformed
requests. `tests.test_doi_response_limit` exercises a synthetic 1,000-order and
5,000-line shape through session and HTTP, response overflow, and preserved checks.
Existing DOI session, ownership, mark-store and alternate-draft regressions cover
the unchanged behavior. These checks use synthetic fixtures only.
