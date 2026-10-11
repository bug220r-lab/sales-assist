# ADR 0042: Separate disabled draft-only runtime

Accepted for the requested source-only CSV-to-approved-draft implementation.

The normal daily launcher requires record-bound other-rep DOI exclusions. Those
records do not authorize conditional outreach. Requiring invented exclusions would
misstate their purpose; bypassing the daily checker would weaken an existing boundary.

Add an explicit `doi_draft_transfer` entrypoint and packaged `start-drafts.ps1`
wrapper. The normal launcher is unchanged. A closed, disabled-by-default private
configuration binds a dedicated nonsynchronized local root, fixed mailbox/user,
port and separately disabled transfer permission. Review mode never constructs
authentication, even with ambient transfer settings. Transfer still requires the
existing process-only opt-in/authentication and all existing per-row gates.

Reuse the portal HTTP guards and draft service but enforce a narrower route allowlist.
No normal application or DOI persistence is opened. Reject shared roots and linked
paths; preserve the durable draft journal. Reuse the OS single-instance lease and
owned receipt under a distinct filename, bind the configuration hash, and reject
configuration changes between validation and lease acquisition. The foreground
wrapper verifies packaged source and leaves existing app processes untouched.

This is process isolation, not an OAuth issuer coordination mechanism. No token
renewal, new grant, cleanup integration or credential persistence is introduced.
The managed-authentication document remains a proposal requiring separate approval.

Synthetic regressions exercise disabled/malformed configuration, path and root
isolation, ambient auth suppression, concurrent startup, occupied ports, restricted
routes, Host/Origin/CSRF rejection, conditional review and exact approval, one mocked
unsent draft, persisted no-repeat-create behavior, and packaged configuration check.
Existing daily-launch regression remains required.

The repository scanner registers only this authored script path and the exact
SHA-256 fingerprints/location of the new public documentation, link-parser expression
and synthetic rejection URLs. No hostname/directory exemption or runtime network
permission is added. Altered literals, unknown scripts and secret material remain
rejected by executable boundary tests.
