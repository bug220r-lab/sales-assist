# Optional Unassigned inbox reader

The repository proposes a Windows-only, manually invoked companion at `companions/unassigned_inbox`. It reads a single configured Help Scout mailbox's active Unassigned queue and saves a private local report with complete conversation histories. See the companion README for setup and commands.

This is an explicit, isolated exception to the synthetic-only sales-assist core. The core application has no live inbox setting or startup dependency on the companion. No reader output is imported into synthetic fixtures, training data, a UI workflow, or GitHub. The existing draft pull requests #1 and #2 are independent; this proposal does not assume either has merged.

To run it, an operator supplies an existing encrypted connection and an external config file with the intended user and mailbox identity. Both the auth file and runtime directory must be outside the checkout. The program checks the signed-in user and mailbox before listing and refuses conversations whose current metadata indicate another mailbox, a non-active state, or any user or team assignment.

One run lists all pages and persists a unique ID work set before reading histories. The default command reads a bounded number of full histories; `--all` reads the saved work set, and `--resume` continues its unread IDs. The report records page coverage, per-conversation outcomes, read times, and incomplete or changed scope. It is an observed snapshot: assignment can change between reads or afterward.

This companion only captures source history. It does not decide whether a reply is needed, generate response text, create or edit drafts, send messages, or change any conversation. Its local report includes private customer content, so the report, config, credentials, and work set must stay outside the repository. No background worker, scheduled task, or UI control invokes it.

Synthetic tests provide package-level checks for pagination, scoping, failure handling, resume, and rendering. A successful synthetic run is not evidence that the packaged companion has read a live mailbox. Any live use is a deliberate manual invocation with separately verified private configuration.
