# ADR 0033: Optional read-only Unassigned companion

Status: proposed for a separate draft pull request.

## Context

Sales-assist is scoped to synthetic examples. The user also has a local Help Scout Unassigned reader and requested a GitHub integration. Copying live data or connecting the core application to a production inbox would expand that scope and make ordinary app startup dependent on a private support system.

## Decision

Add the reader under `companions/unassigned_inbox` as an opt-in command, with no import path from the core application, UI action, service, scheduler, or background worker. A manual run must name one configured mailbox and pass a private config file. The connection and all runtime artifacts stay outside the checkout. Commit only source code, a synthetic sample config, tests with synthetic fixtures, and documentation.

The reader is limited to identity and mailbox verification, complete Unassigned listing, full conversation/thread reads, scope checks, and local reports. It has no conversation mutation transport. It reports incomplete listings, changed scope, failed reads, and unread IDs explicitly. Resume is tied to the saved work set rather than expanding it silently. The output is a point-in-time observation, not an atomic mailbox snapshot.

The existing draft pull requests #1 and #2 establish a pattern of isolated review, but neither is assumed merged or made a dependency of this companion. This decision is the proposed exception for this package only; it does not authorize live data in the synthetic core or any future Help Scout write capability.

## Consequences

Operators must provide their own verified account/mailbox configuration and existing encrypted connection. The companion can be tested offline with synthetic fixtures; live behavior of the packaged revision requires a separate manual check. Reports contain customer data and must remain in the private external runtime directory. There is no automatic data flow back into sales-assist or GitHub.
