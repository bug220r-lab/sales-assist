# Consolidated Sales Assist review candidate

This candidate combines the existing DOI review, local saved state, approved CSV draft
transfer, optional session renewal, standalone read-only Help Scout credit evidence
reader, and single-owner pilot coordinator. It is a draft review build. No live connection
is activated by installation.

## Included behavior

The combined follow-up source adds [split-review discovery](split-review-discovery.md):
held purchased-line ready/waiting patterns are visible as review leads with every original
hold retained, while stock-counter clues remain separate. It also includes the reviewed
draft customer-association change from PR7: no separate customer-creation POST is needed,
and the explicitly authorized email mode discloses its possible implicit contact creation.
Existing-ID transfer freshly verifies that exact customer and recipient. This isolated
candidate does not change the installed daily app or activate a live connection.

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
- The disabled single-owner coordinator holds the original owner lock and session lease,
  passes one token/expiry snapshot to the reader first, checks the draft recipient and
  accessible-mailbox duplicates, and binds one approved copy to the existing durable
  transfer service. Unknown outcomes block retry. The separate one-issuance option is
  available only with activation-time authorization and actual cached-token expiry.
- The coordinator's content bundle may preserve an unresolved duplicate check only when
  every other hold is resolved. Sealed current preflight evidence completes a separate
  execution review with source provenance; exact copy and ordinary durable approval rules
  remain unchanged. Literal entity-bearing source URLs and missing factual evidence stay held.

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

This combined follow-up is stacked on draft PR #7 (`codex/unsent-draft-email-association`,
source commit `1e7a0fa9f809d3bfb9e358c8344e82ad9e576bc2`). PR #7 depends on draft PR #6
(`codex/consolidated-review-candidate`, source commit `c6eb66fe794948e85c1c05b32cb423cf671cf45a`).
PR #6 introduced the reviewed credit reader and single-owner coordinator, the tested DOI
limit delta, and packaging documentation on top of draft PR #5
(`codex/doi-approved-draft-transfer`, source commit `3eb1214f667618e3449bc4af494ecdb3b8a8ef30`).
PR #5 itself depends on PR #4. These dependencies remain separate draft reviews; this
candidate does not merge them into the default branch.

Live Help Scout draft and credit pilots remain pending separate credential-owner coordination,
activation approval and supported browser acceptance. No ownership attestation is inferred,
no cache is accessed during installation/tests, and no cleanup process is changed.
Automated cleanup is cancelled and must not be restarted by this release workflow.
This candidate must not be described as production-ready. Human visual acceptance,
clean-machine validation and live compatibility are separate outstanding gates.

The [single-owner coordinator](single-owner-pilots.md) is included from reviewed source
commit `143e1d690c9de492528b6e8d3852a1e6d8f5db47`. Its source integration does not
activate a live pilot. Original ownership, genuine private approval inputs, the preserved
ledger, separate auth authorization and action-time gates remain required. Scoped duplicate
checks do not prove global historical draft absence or prevent concurrent manual inbox edits.
