# ADR 0028: deterministic demo release and local ownership

Status: accepted, 2026-09-05.

The demo retains the checkout directory layout because migrations and closed registries are
root-relative. External CPython 3.12 and Windows time-zone data (`tzdata==2026.3`) are
required; the exact existing Codex fallback remains DEVELOPMENT/NONPORTABLE under the
unchanged runtime guard. No interpreter or unverified redistribution license is bundled.
The locally installed tzdata distribution declares Apache-2.0; its bytes are not copied.
Application processes ignore Python environment overrides and user-site packages, while
retaining the selected interpreter's system-site time-zone data. The executable identity
probe still disables all site initialization. An isolated extracted-process test exposed
the missing time-zone prerequisite; dependency metadata and startup guidance now name it.

Build from immutable local Git commit C and its tree T using Git archive, without copying
Git history. Archive paths, collisions, links, modes, order, compression, and timestamps are
validated/normalized. Commit time is the timestamp input; PowerShell/batch line endings are
deterministically CRLF in the runtime package. Supplied protected bytes are never normalized.
The source archive retains exact Git blobs. Runtime build metadata and payload inventory are
generated outside tracked source. The inventory excludes its own hash; outer archive hashes
exist only after archives are built. Reports and reviewer attestation are external to C.

The dispatcher verifies payload hashes, resolves its own installation and source path, and
uses a fresh release-specific local application-data root. It never chooses the old working
database. Existing unmarked or changed demo data requires explicit Upgrade. The existing
start lifecycle lock encloses package preparation, verified backup before upgrade, startup,
and owned-process verification. Same-schema code upgrades preserve history; migration
transactions and immutable migration checksums retain their established authority.
Preparation also holds the existing service maintenance lease, excluding direct module
startup while data is prepared. Successful explicit data-root selection is persisted
atomically in release-specific local configuration so subsequent double-click actions
target the same demo. Configuration and defaults also include a digest of the normalized
installation path: two copies of one ZIP cannot overwrite each other's selection. Moving
an extracted folder creates a fresh selection; an explicit data root is required to reuse
its prior disposable demo. Metadata rejects links before writes; original data is never selected
by default. Reset seeding remains inside its existing lifecycle and maintenance leases.

Only marked, exact M8 launcher paths are admitted by the repository scanner. Batch content
is scanned as text with the existing secret and network checks. The extension bytes and
permissions are unchanged. No new listener, external endpoint, or background watchdog exists.

Conservative removal uses the package inventory and removes only unchanged named files.
It never recursively deletes the installation or a data root. Modified/unknown files and
external data/backups remain. Reset delegates to the existing confirmed backup/owned-stop
boundary on explicitly disposable data. No machine configuration is persisted.
Removal holds the lifecycle and service maintenance leases and preflights all named paths
before deletion. Configuration is project-local, outside both source and original data.
The running REMOVE.cmd bootstrap remains on disk: deleting it caused Windows cmd.exe to
report failure after successful removal. Unknown generated cache files are also preserved;
removal never broadens into recursive deletion to produce an empty directory.

Packaging tests cover archive determinism and unsafe paths, payload modification detection,
actual extracted service workflows, backup-before-upgrade failure/success, conservative
removal, launcher scanning, and required component identities. Release evidence additionally
binds exact extracted packages, browser observations, measurements, and separate review.
