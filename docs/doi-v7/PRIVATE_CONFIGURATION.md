# Explicit private setup

Daily START requires `doi-private-launch.json` in the installation's external data
directory and an already approved confirmation file on a local nonsynchronized disk.
Neither file belongs in the application folder or source checkout. Setup does not
create or approve confirmation decisions, launch the service or contact an API.

The generic `scripts/setup-daily-private.ps1` recipe requires `PackageRoot`,
`ConfirmationPath`, `ApprovedSha256` and `ExpectedDecisionCount`. Supply the independently
reviewed hash and exact approved count (1 through 10). It verifies package integrity,
locates the data directory using the existing support tool, refuses existing config
and service receipts, creates config exclusively, then runs the same policy checker.
It never copies decisions or overwrites an existing setup. A failed validation is
an error requiring review; it is not permission to bypass the check.
Paths must be absolute and on fixed local disks. Network, device, synchronized,
package-contained policy and reparse paths are rejected before policy access or
package commands. The returned data directory and its config/receipt paths are also
checked before any configuration write.

The daily checker repeats these location checks on every START, binding write and
reopen, including after a manual config edit. It rejects the standard OneDrive
(including organization suffixes), Dropbox, Google Drive and iCloudDrive folder
names and the roots declared by OneDrive environment variables. On Windows only
`DRIVE_FIXED` is accepted; unknown, unavailable, removable, network, optical and
RAM drives fail closed. Reparse ancestors are checked from root to leaf before
opening configuration or policy. Operators must still choose a nonsynchronized
location: arbitrary third-party sync roots with custom names are not discoverable
from these path checks alone.

Synthetic structural example only (the repeated hash is not an approval):

```json
{
  "schema": "ssa-doi-private-launch/v1",
  "confirmation_path": "C:\\SyntheticPrivate\\confirmations.json",
  "confirmation_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "expected_decision_count": 1
}
```

START rejects absent/malformed config, unsupported paths, missing policy, hash or
count mismatches, and invalid or empty policy. Exact-record confirmations apply only
when the loaded CSV pair and record evidence match. No result count is promised for
a different input. Changed policy requires stopping the owned service and explicitly
reviewing/updating private setup before a restart. Reopen verifies the policy,
process identity and packaged source fingerprint. STATUS and STOP remain usable
when private policy is missing or invalid.

PowerShell must permit the reviewed scripts in the process used for setup/launch.
The existing CMD wrappers invoke PowerShell with `-ExecutionPolicy Bypass` for that
child process only; they do not change User or Machine policy. This existing flag
does not constitute permission or override organizational Group Policy. The generic
setup script does not change execution policy. If policy permits and the operator
separately chooses it, `Set-ExecutionPolicy -Scope Process Bypass` affects that
PowerShell process and its children. Run the reviewed setup in that same process.
Do not change User or Machine scope, bypass organizational controls, or treat these
instructions as automatic permission. A restrictive Group Policy may still block execution.

Moving the package selects a separate default data directory; review setup there
explicitly. Preserve existing installations, data, captures and receipts. No startup
registration, credential entry or external API access is part of this recipe.
