# Milestone 4 backup and restore guide

Create a verified local backup with:

```powershell
python -m synthetic_sales_assist.cli --data-dir C:\safe\local\instance db backup backup.sqlite3
```

A bare filename resolves beneath the managed backup directory. An explicit absolute local file is
also accepted when its parent already exists. URL, UNC, device, traversal, symlink, active-database,
and network-share paths are rejected. Existing files require `--overwrite`.

The service uses SQLite's online backup API, verifies the resulting image, computes its SHA-256,
and publishes the image and receipt with same-directory atomic renames. Those two renames are not
one filesystem transaction. A new destination publishes its nonidentity receipt first and its
identity-bearing database second, so interruption between them cannot expose an unreceipted new
database. Before database replacement, fault handling removes a new half and, on overwrite,
restores the prior receipt. Verification rejects any incomplete pair. The old identity database
stays at the canonical path until one atomic replacement; it is never staged as an
identity-bearing `.previous` file. A receipt-recording fault after replacement finishes the new
pair forward. The receipt records controlled versions, migration checksums,
creation time, health results, table counts, image digest, and expiry.

Restore requires an explicit confirmation:

```powershell
python -m synthetic_sales_assist.cli --data-dir C:\safe\local\instance db restore backup.sqlite3 --confirm
```

Restore verifies the receipt and image separately, rejects future/incompatible/corrupt/expired
images, creates a verified automatic pre-restore backup, restores into and verifies a temporary
database, prepares a verified rollback image, replaces the existing active file with one atomic
`os.replace`, and verifies the reopened active database. The active path is not renamed away
before replacement. Any post-replacement failure atomically installs and verifies the rollback
image. Restore is rejected while an application operation is active.
The exclusion is shared by independent handles and independent local CLI processes through a
crash-released operating-system lock; it does not rely only on an in-memory mutex.

Managed backups cannot extend identity retention. Expired identity-bearing backups are ineligible
for restore. The bound is computed from the verified snapshot, including a concurrent earlier
deadline only when its transaction is part of that snapshot; an overlapping transaction appears
entirely before or after commit and never partially. Due-at-capture backup fails closed; restore at
or after the receipt expiry is rejected before the active database is touched. Remove expired
managed pairs with:

```powershell
python -m synthetic_sales_assist.cli --data-dir C:\safe\local\instance db purge-expired-backups
```

Pass an optional backup path to evaluate one explicitly selected local backup. Cleanup uses the
same exact expiry comparison as restore. It unlinks the database directly first and never moves
identity bytes to a hidden `.expired` file. Pre-unlink failure preserves the pair; post-unlink
failure completes receipt deletion forward. A hard-exit orphan receipt is recognized and removed
by the next directory scan, and a repeat after success is an idempotent absence no-op.
That scan also deletes strictly UUID-named backup `.tmp` and legacy `.previous` crash remnants,
identity files first. If an interrupted overwrite left the new receipt over the still-canonical
old database, a matching staged prior receipt is restored before receipt remnants are removed.
