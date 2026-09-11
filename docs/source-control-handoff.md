# Private source-control handoff

This checkout contains the developed Synthetic Sales Assist application, version 0.1.4,
and localhost Chrome extension, version 0.1.2. The root README describes the original
specification bundle and is deliberately preserved because it is checksummed.
Start with [DEVELOPMENT.md](../DEVELOPMENT.md) for current setup and verification,
[known limitations](m8/KNOWN_LIMITATIONS.md) for acceptance status, and
[the extension guide](../chrome_extension/README.md) for the optional localhost panel.
Read [AGENTS.md](../AGENTS.md) and [the specification index](../specs/SPEC_INDEX.md)
before changing the implementation.

The user approved the private GitHub destination `bug220r-lab/sales-assist` for the
first source upload. This document records the upload scope; successful publication,
visibility, and remote commit identity must be verified separately after the push.

## Source and history

The existing application baseline is commit
`d667eb38ea89c218c7f72681b21a21242b367111` on `finish/synthetic-v0.1`.
It has 14 commits of local development history. The upload preparation changes only
the ignore rules and this handoff document. Application code, protected specifications,
reference material, migrations, and existing commits remain unchanged.

The reviewed source scope comprises `src/`, `chrome_extension/`, `migrations/`,
`tests/` (including generated-in-code synthetic fixtures), `scripts/`, `tools/`,
`pyproject.toml`, relevant documentation, tasks, and the protected specification bundle.
No dependency lockfile exists in this checkout; none is synthesized during upload.
The Python manifest records the runtime dependency and optional development tools.

## Excluded local material

Ignored `.runtime/` working artifacts and Python caches are excluded. Credentials,
populated environment files, browser state, customer exports, logs, screenshots,
databases, campaign queues, protection manifests, suppression lists, send receipts,
production audit records, dependency directories, and unrelated backups must remain
outside published source history. A placeholder-only `.env.example` may be included
only after content review; none is present in this upload.

Ignore rules are preventive convenience, not a content or history audit. Before a
later push, review staged and untracked files plus all commits being transmitted.
Do not force-add local data or push additional branches or tags without review.

## Operating boundary

This is a private source-control handoff, not deployment or a complete operational
backup. Excluded local data, credentials, and campaign state are not backed up.
Only reserved synthetic identities are executable; application networking remains
localhost-only. Uploading source does not authorize live integrations or operations.
There are no GitHub Actions workflow files in the reviewed source. Do not enable Pages,
deployment, or live automation as part of this handoff. No license or collaborators
are added by this task.

Source-only safety checks can run without starting the application. The complete
regression suite also exercises service lifecycle and external temporary data roots;
it is not part of this upload's no-services scope. Historical test reports do not
establish a new test run, human manual acceptance, or clean-machine validation.
