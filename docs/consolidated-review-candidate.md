# Consolidated Sales Assist review candidate

This candidate combines the existing DOI review, local saved state, approved CSV draft
transfer, optional session renewal, and standalone read-only Help Scout credit evidence
reader. It is a draft review build. No live connection is activated by installation.

## Included behavior

- DOI review accepts up to 1,000 joined orders, 5,000 records per CSV and 4 MiB per CSV.
  JSON requests are bounded to 16 MiB; review responses remain bounded to 4 MiB.
  The fixed review session remains ten hours. Capture facts and eligibility rules are unchanged.
- Evidence-bound reviewed checks and explicitly saved alternate drafts survive restart.
  Reload the same CSV pair to recover matching checks; transient imported captures are not
  persisted. Changed evidence requires another review and does not inherit approval.
- The separate CSV draft-transfer workflow preserves exact approved copy and a durable
  transfer journal. Unknown create outcomes block another create until reconciled.
  The only implemented external write is an explicitly approved unsent draft; no send exists.
- Cached authentication and memory-only client-credentials renewal remain separate opt-in
  modes. The renewal provider never automatically replays a draft POST.
- The standalone credit evidence reader and coordinated cached-snapshot bridge remain
  disabled by default. The reader only gathers scoped facts; credit is always NOT_EVALUATED.
  The bridge does not renew, rewrite or reload credentials.

## Isolated installation and review

Extract the Windows archive into a new local directory. Keep its bundled Python directory
and release manifests together. Use a new absolute local data directory and an unused
loopback port; do not select an existing daily installation or data directory.
The ordinary launcher retains its private-policy checks. Installation does not configure
a live policy, credential cache, customer CSV or connection.

The existing [daily guide](doi-v7/DAILY_README.md) and
[private configuration guide](doi-v7/PRIVATE_CONFIGURATION.md) explain ordinary launch
requirements. [Draft review launch](doi-draft-launch.md) has its own isolated configuration
and defaults to review-only. The [reader guide](helpscout-credit-evidence.md) documents
offline `--demo` and every additional live gate. The reader is a separate module rather
than a new Control Center screen.

All build acceptance uses fictional identities, temporary storage, loopback HTTP and mocked
external APIs. Test evidence, exact source commit and artifact checksums accompany the
candidate outside the source archive. Windows package verification is not clean-machine
or human visual acceptance.

## Save, backup and recovery

Explicitly save editor changes before closing or restarting. The built-in database backup
covers core and campaign SQLite databases; the restore CLI covers only the core database.
Campaign restore requires a separate verified stopped-service procedure. Backups exclude DOI
reviewed-check JSON, alternate-draft JSON, private launch policy, or draft-transfer journal.
For a complete local review-state backup, stop the owned isolated process and retain those
stores separately using a byte-verified copy. Preserve the newest saved state before any
recovery; never overwrite newer work with an older snapshot.

Malformed imports clear the transient review but retain saved state. Storage corruption or
write failure must remain visible and must never be reported as a successful save. Restore
only a verified known-good copy while stopped, then reload the same synthetic pair and
check the saved state. A known or uncertain draft creation remains protected against replay
after restart. Do not reset that journal to work around an unknown external outcome.

## Review stack and remaining gates

The candidate is stacked on draft PR #5 (`codex/doi-approved-draft-transfer`, source commit
`3eb1214f667618e3449bc4af494ecdb3b8a8ef30`). PR #5 itself depends on PR #4.
This candidate adds the two reviewed credit-reader commits and the tested DOI limit delta,
plus packaging documentation. It does not merge either dependency into the default branch.

Live Help Scout draft and credit pilots remain pending separate credential-owner coordination,
activation approval and supported browser acceptance. No ownership attestation is inferred,
no cache is accessed during installation/tests, and no cleanup process is changed.
This candidate must not be described as production-ready. Human visual acceptance,
clean-machine validation and live compatibility are separate outstanding gates.

The combined single-owner live-pilot coordinator is also an outstanding source gate for
this snapshot. It must provide the session-issued token and authoritative expiry handoff,
recipient/duplicate prechecks, and durable binding to one approved copy. The existing
cached-snapshot bridge is included; it does not establish that this combined coordinator
has been completed or reviewed. Do not run a combined live pilot from this snapshot.
