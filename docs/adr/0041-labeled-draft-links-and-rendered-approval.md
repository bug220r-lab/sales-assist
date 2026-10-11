# ADR 0041: Labeled draft links and approval of rendered copy

The prior draft renderer recognized raw URLs but left `[label](url)` delimiters
visible. Readback compared rendered HTML text against the stored Markdown source,
so an ordinary labeled link could not satisfy exact-copy verification.

Recognize a deliberately small syntax: a nonempty, single-line plain label in
`[label](https://destination)`, with no nested brackets, URL whitespace or URL
parentheses. This is not a general Markdown or HTML renderer. Escape all text and
HTML attributes; leave other formatting as literal text. Keep existing bare-URL
and standalone CTA behavior. Never normalize, decode or rewrite URL values.
Stored source/selected copy and their hashes remain unchanged. Display line endings
continue to normalize to LF without modifying stored bytes.

Produce shared text/link segments for both outbound HTML and the saved preview.
The browser builds text nodes and anchors, never inserts source HTML. Preview links
open only on a user click, with a separate browsing context and no referrer/opener.
Unsaved edits display source text with a save-required notice and disable approval.
Saving reloads the exact preview from the server.

Verify readback against the intended rendered visible text and each hyperlink's
destination plus visible-text start/end offsets. Safe inline markup can differ,
but moving an anchor, changing a label/target, duplicate href attributes, nested
anchors or unclosed anchors cannot verify. A failed readback keeps the known draft
ID and its no-repeat-create protection.

Approval already binds the rendered HTML along with the row, review and version.
Make the worklist/detail projection check that current binding too. A renderer
change must not leave an old approval visibly valid. Explicitly approving the new
binding replaces the stale approval and records another approval event; it does
not edit source copy or automatically transfer a draft. Existing reserved/created
records retain their lock and cannot acquire a second create.

No CSV schema, factual/cart gate, private-launch policy, authentication route,
destination, draft-only payload or automatic-retry behavior changes here.

Executable coverage: `tests.test_doi_draft_transfer_links` checks exact labels and
URLs, escaped HTML, old plain-copy behavior, approval binding changes, mocked create
and readback, malformed/moved anchors, stale approval and explicit reapproval, and
the conditional-review evidence boundary. The existing frontend runner exercises
saved link nodes, dirty preview invalidation and save/review/create through isolated
localhost HTTP with a mocked Help Scout client.
