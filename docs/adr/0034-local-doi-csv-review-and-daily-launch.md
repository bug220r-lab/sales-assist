# 0034 - Local DOI CSV review and daily launch

Status: proposed for review with the DOI v7 source-only pull request.

The owner authorized importing the tested local DOI CSV review and daily-launch
source on the reviewed Windows preview baseline. This is an explicit local-input
exception to the original synthetic-only project scope, confined to the separate
`doi_csv_staging` projection and `/doi-csv-review` screen. The original rule engines,
synthetic identity firewall, specifications, migrations and extension permissions
remain authoritative and unchanged. This decision does not authorize production
execution, external system access, messaging or deployment.

CSV observations and exact ownership mappings produce a bounded, in-memory review.
They do not persist imported orders into the synthetic database or determine credit,
fulfillment or customer actions. Tests generate fictional numeric CSV keys and
`example.test` addresses from requirements; they are not anonymized customer records.
Established ownership aliases are preserved as rule constants, including exact-match
rejection of case, whitespace and prefix/suffix lookalikes.

Owner confirmations can only exclude a bounded set of previously unmapped records.
The exact CSV pair, record digest, order key, ordinal and chronology must match.
USD observations and owner policy remain distinct from currency conflicts. No
conversion is inferred. Review expiry remains 1,800 seconds and is not extended by
refresh; stale revisions and oversized inputs fail closed.

The daily launcher requires external configuration with an approved policy hash and
expected decision count. It checks before preparation/launch and binds the policy
to the owned process receipt and source fingerprint. Reopen requires the same
healthy owned process and binding. Status and Stop do not require valid policy.
Process ownership, loopback restrictions, locking and cleanup remain intact.

Source publication removes private delivery metadata. Builders instead derive
`doi_source_payload_sha256` from a canonical inventory of the committed application,
specifications, migrations, scripts, policy helper and project metadata. The existing
daily distribution identifier is retained for launcher compatibility; it is not a
release claim. Generated manifests, runtime archives, configuration and receipts
are never committed. Package tests prove determinism and source-change sensitivity.

The generic setup recipe requires all operator-specific values as parameters and
refuses an existing configuration or service receipt. It uses exclusive creation
and the same policy validator. No private default or approval hash is embedded.
Parameterization adds early checks for absolute paths on fixed local disks, external
policy location, synchronized folders and reparse ancestors. The ancestor walk runs
from root to leaf before any policy probe or package command. Synthetic tests cover
rejected paths, reparse directories, existing state and validation failures.

Validation lives in executable DOI, policy, launcher, packaging and core regression
tests. Automated local tests do not establish manual acceptance of the packaged UI.
PowerShell process-scope execution-policy handling requires a separate operator
decision; a documented command is not automatic permission to change policy.
