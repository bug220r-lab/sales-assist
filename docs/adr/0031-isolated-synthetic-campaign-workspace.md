# ADR 0031: Isolated synthetic Campaigns and Replies workspace

The September handoff adds offline campaign simulation and local draft review. The
existing Sales Credit/DOI schema, migrations, order adapter and rule engines remain
authoritative and unchanged. The Control Center exposes the new feature through its
existing owned loopback HTTP server and Host, Origin, CSRF and CSP controls.

A sibling `campaign_replies.sqlite3` is the versioned feature store. It uses the
existing local path guard, SQLite WAL, FULL synchronization, foreign keys, bounded
busy waits and explicit BEGIN IMMEDIATE transactions. This avoids attaching a new
domain to closed schema-4 business projections or altering historical migrations.
Feature services own namespaced tables and validate inputs before atomic writes.
The format marker is `synthetic-campaign-workspace/v1`. Schema-4 backups do not
include this file; use SQLite backup separately for this store, never a live file copy.

Imported facts and source bytes are immutable provenance; drafts are versioned human
records. Source evidence and style versions bind review. A compare-and-swap revision
rejects stale edits. Re-import is idempotent and older or conflicting snapshots cannot
replace accepted facts. Snapshot completeness is required before commit.

Reply summary projections carry a separate schema marker. Initialization repairs older
cached summary fields once from retained source facts, without mutating snapshots or
draft/review records. Read-only queue requests do not repeat this work. A history corpus
is bound to the first immutable report's target writer; another writer needs a separate
corpus/store, preventing cached attribution from crossing author scopes.

Initial outreach is a closed simulation transport. Durable intent precedes creation;
unknown outcomes block retry. Reply review saves only local drafts. No production
transport, credentials, sender, poller or remote draft action is installed. A local
SQLite writer is never represented as cross-PC worker ownership. Future transfer
requires immutable source files, byte hashes, all current protections and a deliberate
single-writer cutover as specified by the handoff.

Legacy companion schemas are reference contracts, not permission to weaken the
synthetic firewall. Generated executable fixtures use reserved identifiers and
example.test addresses. Original companion files remain untouched. Thread content is
displayed as text, attachments as metadata, and external links are unavailable.

Writing-history preparation is deterministic and inspectable. Template removal and
near matches are heuristics, raw originals are retained, and the candidate set is
neither verified personal authorship nor an exhaustive sent-history archive. The
13-message style reference stays provisional; no model training or AI connection is
claimed. Future profile revisions invalidate review without rewriting draft text.

The required saved-reply wording is an exact-byte, read-only package resource at
`campaign_replies/data/saved_reply_references.json`; its source and hash are recorded
in `data/README.md`. Missing resources fail initialization instead of silently removing
template detection. Setuptools includes this JSON and the workspace JS/CSS assets.
Only the two pure companion JS contracts and synthetic scenario inventory needed by
regression tests are vendored under `tests/fixtures/campaign_replies`, with provenance.
The application and regression suite do not depend on the untracked original handoff,
worker modules, production identities or data. The original handoff remains untouched.

The repository content scanner admits the two immutable companion JS test references
only at their exact test-fixture paths with their reviewed SHA-256 bytes and a bounded
file size. They contain legacy wording/link strings but perform no networking and are
never served by the app. Modified copies or other locations retain normal rejection;
the credential scanner continues to scan them. Regression tests cover these boundaries.
