# Dedicated draft-review launch

The separate draft-only mode serves CSV import, review, exact-copy approval and
optional approved unsent-draft creation. It does not require DOI other-rep exclusion
records. The normal START/daily launcher and its policy requirements are unchanged.

This is a source feature, not live activation authorization. No credentials or
private configuration are included in the package. Do not restart an existing app
review, share its data folder, or point this mode at another running integration.

## Configuration and launch

Use a new, nonsynchronized folder on a fixed local drive, outside every repository.
Save `draft-only-launch.json` directly inside that folder. This example is disabled:

```json
{
  "schema": "ssa-draft-only-launch/v1",
  "enabled": false,
  "data_dir": "C:\\Private\\SYN-DraftReview",
  "port": 0,
  "mailbox_id": 166170,
  "user_id": 897275,
  "allow_draft_create": false
}
```

Replace the synthetic example path with the chosen private folder and explicitly
set `enabled` to true to run local review. A port of zero selects an available
loopback port; an explicit occupied port fails without stopping its occupant.
The root accepts only this configuration plus its dedicated `data` and `runtime`
folders. Shared DOI/app roots, synchronization roots, links, unknown keys and
different account targets fail closed. Do not place CSV uploads in this root:
choose them from their existing private location in the import dialog.

From a verified packaged build:

```powershell
.\scripts\start-drafts.ps1 -ConfigFile 'C:\Private\SYN-DraftReview\draft-only-launch.json' -CheckOnly
.\scripts\start-drafts.ps1 -ConfigFile 'C:\Private\SYN-DraftReview\draft-only-launch.json'
```

The wrapper verifies the release payload before configuration validation or launch.
It runs in the invoking console and prints the local URL. Open that URL in the
browser. Ctrl+C stops this instance and releases its own lease. It does not reopen,
stop, or inspect another app. The ordinary STATUS/STOP scripts manage the normal
app and should not be used for this separate mode.

For source development, run `python -m doi_draft_transfer --config <absolute-path>`
from `src`. The same closed configuration, local path and row gates apply;
`--check` validates configuration without opening a listener or constructing auth.

## Separate review and transfer permissions

With `allow_draft_create: false`, all local CSV and review functions work but the
runtime never constructs a Help Scout client, even when transfer-related environment
settings happen to be present. Default configuration is disabled, and transfer is
disabled separately. Configuration contains no token, credential path or secret.

Only after separate activation authorization may an operator set
`allow_draft_create: true` and supply the existing process-only authentication
settings described in [draft transfer](doi-draft-transfer.md). Both switches must
permit transfer; missing auth configuration stops startup. Cached authentication
remains lazy and never renews. The separate session-renewal mode is documented in
[session authentication](doi-draft-transfer-auth-proposal.md), with explicit
ownership and renewal opt-ins. Startup and page GETs perform no Help Scout requests.

Configuration is a launch scope, not row approval. Recipient provenance, exact
eligible rep, order status, factual acknowledgments, complete cart review, duplicate
reconciliation, and approval of the current rendered copy remain required. Customer
decision may explicitly remain pending for conditional outreach. Import does not
approve or create anything. Creation is a separate per-row action, always an unsent
draft; there is no send, status-change, order-change or bulk-create operation.

## Isolation, ownership and recovery

Only draft routes, their styles and the existing authenticated shutdown route are
served. DOI review/override, campaign, order and general dashboard routes return 404.
The UI contains only draft navigation. Host, Origin, CSRF, request/response bounds
and the durable reservation journal use the existing implementations.

The private journal is `data/doi-draft-transfer.sqlite3`. The separate receipt is
`runtime/draft-service.json`, with a crash-released process lease. It records native
process identity, the exact journal, origin and configuration hash. A concurrent
instance on that root is rejected. Changing configuration requires a restart;
it does not reconfigure a running process. A changed config during startup is rejected.
Never delete or replace this journal to clear a duplicate or uncertain-write hold.

Only the runtime's own receipt/lease is released on close. Startup creates no order
database, old split-review marks or alternate-draft store, and does not migrate them.
Known IDs and unknown/in-flight writes survive restart and continue to block repeat
creation. An empty new journal does not prove absence of an existing remote draft.

This implementation was developed using synthetic fixtures and mocked Help Scout
calls. Source implementation does not activate a private instance, import real rows,
establish cart/customer evidence, or authorize credential access or token renewal.
