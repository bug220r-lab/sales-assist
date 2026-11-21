# Unassigned reader companion rules

The user requested this one optional Help Scout reader as an isolated exception to the repository's synthetic-only core. These rules apply only inside `companions/unassigned_inbox`. They do not change the core application's scope, specifications, startup, UI, or networking rules.

- Keep the companion manually invoked. Do not import or invoke it from the synthetic core, a UI route, startup script, service, scheduler, or background worker.
- During development and tests, use synthetic identities, mailboxes, conversations, and responses. Do not use a live Help Scout connection or include customer data in tests, examples, logs, commits, issues, or pull requests.
- Require an explicit external config path for manual operation. Keep the live config, existing encrypted auth material, runtime directory, reports, work sets, and records outside the repository. Reject paths resolving inside the checkout.
- Limit Help Scout conversation access to identity and mailbox verification, active Unassigned listing in one selected mailbox, and complete conversation/thread reads. Fail visibly on incomplete reads or changed scope. Do not add draft, send, assignment, status, note, tag, delete, customer, order, or other mutation commands.
- A fixed OAuth renewal request needed for read access may remain in memory; never persist refreshed credentials or broaden the HTTP allowlist to conversation writes.
- Preserve bounded reads and exact saved-work-set resume. Keep exceptions and unread IDs visible rather than silently dropping or relisting them.
- Run companion synthetic tests for changes here, and any available core regression checks affected by integration wiring. A synthetic pass does not establish live validation.
