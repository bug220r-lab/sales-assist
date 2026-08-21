# ADR 0018: Backup, restore, atomicity, and retention

- Status: accepted for Milestone 4
- Scope: local SQLite backup images, restore coordination, and retained identity safety

## Decision

Create backups with SQLite's online backup API into a temporary database, verify schema,
migration checksums, quick check, and foreign keys, then publish the database and its closed
receipt sidecar through same-directory atomic renames. For a new destination the nonidentity
sidecar is published before the identity-bearing database, so a hard exit between publications
cannot leave a newly published unreceipted database. The pair is not one filesystem transaction;
before database replacement, fault handling removes the new half and restores a staged prior
receipt when overwriting. The prior identity database itself always remains at its canonical path;
it is never moved to an identity-bearing `.previous` file. After database replacement, receipt
recording completes forward. Readers reject an incomplete pair. A receipt binds the
application/schema versions, migration inventory,
trusted creation time, verified image digest, controlled table counts, health results, and an
expiry bound. Existing backups are never overwritten without explicit authorization.

Restore requires explicit confirmation and exclusive maintenance ownership. It verifies the
sidecar, digest, schema compatibility, integrity, and foreign keys before touching the active
database; creates a verified automatic pre-restore backup; restores through a temporary database;
verifies that database; prepares and verifies a rollback image from the pre-restore backup; and
uses one atomic replacement of the existing active pathname. The active path is never deliberately
removed or renamed away first. It then reopens and verifies the active result. A failure after the
replacement atomically replaces it with the verified rollback image and verifies that result.

Identity-bearing managed backups cannot bypass retention. Their restore eligibility expires at
the earliest governed identity deadline represented in the image or the documented backup
retention bound. The expiry is derived from the verified backup image after the online snapshot
completes. A writer that overlaps the SQLite online copy is represented as one complete state:
fully before or fully after its commit, never a partial transaction. A due-at-capture image is not
published, and restore rejects an image at or after its bound before maintenance, pre-backup, or
activation. At or after that same exact bound, managed cleanup directly unlinks the
identity-bearing database first; it never renames those bytes to a hidden or alternate retained
path. A fault before unlink preserves the pair. Once unlink succeeds, cleanup completes the
nonidentity sidecar forward. A hard exit in that narrow interval leaves only a sidecar, which the
same idempotent cleanup recognizes and deletes. The local CLI can scan its managed backup
directory or evaluate one explicitly selected local backup, so external backups remain subject
to the same deletion mechanism. Directory cleanup also recognizes only the implementation's
strict UUID-named `.tmp` and legacy `.previous` crash artifacts, deletes identity-bearing
artifacts before receipt metadata, and restores a matching staged prior receipt when the
canonical overwrite database still has its earlier digest.

## Consequences

No open database is copied byte-for-byte as the primary backup mechanism. Interrupted backup or
restore cannot publish an unverified half-result. A successful restore preserves logical history
and replay behavior; the newly recorded restore receipt means physical file bytes need not equal
the source image. Expired full-database images do not survive merely because they are no longer
restorable. Backup paths never grant network or external-system capability.
