# DOI intake companion integration profile

This subtree proposes the isolated integration requested by the repository owner
on 2026-09-23. Review its optional Google-read capability separately from the
synthetic application. It does not broaden any existing core runtime, identity,
networking, database, browser-permission or protected-specification contract.

- Keep the supplied intake script and its tests separate from `src/`.
- Never import this companion into the synthetic application or its startup.
- Never insert companion or real order identifiers into the synthetic database.
- Tests use fictional fixtures and mocked transport, never production credentials.
- Live reads are not authorized during development; the supported launcher requires
  explicit `--enable-google` and independently approved read-only credentials.
- Keep credentials, history and generated records outside the checkout.
- Do not add Order Admin access, source writes, messaging or order mutation.
- Do not weaken core tests or edit protected specifications to admit this subtree.
- Review handoff checks are not execution authorization or source authentication.
- Preserve vendored v1 bytes unless deliberately versioning, documenting and testing
  an upstream change. See `docs/integrations/doi-intake.md`.
