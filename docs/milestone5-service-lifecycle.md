# Milestone 5 Windows service lifecycle

The four operator scripts run without administrator rights and always require an explicit local
data directory in tests. Their operator default is `%LOCALAPPDATA%\SyntheticSalesAssist`.

```powershell
scripts\start.ps1 [-PythonPath PATH] [-DataDir PATH] [-Port 8765] [-NoBrowser]
scripts\status.ps1 [-PythonPath PATH] [-DataDir PATH]
scripts\stop.ps1 [-PythonPath PATH] [-DataDir PATH]
scripts\reset-demo.ps1 -ConfirmReset [-PythonPath PATH] [-DataDir PATH] [-Port 8765]
```

When this workspace has no ordinary local Python 3.12 installation, use the verified bundled
runtime as a session-scoped fallback:

```powershell
# DEVELOPMENT / NONPORTABLE -- this workspace only
$localAppData = [Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)
$profileRoot = [IO.Directory]::GetParent($localAppData).Parent.FullName
$env:SSA_PYTHON = Join-Path $profileRoot `
  '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
.\scripts\start.ps1 -NoBrowser
.\scripts\status.ps1
.\scripts\stop.ps1
Remove-Item Env:SSA_PYTHON
```

Keep `SSA_PYTHON` set for start, status, stop, and reset so every ownership check selects the same
executable. This is a DEVELOPMENT / NONPORTABLE Codex workspace configuration. It does not create
or claim a portable release.

The scripts serialize lifecycle-changing work with
`<data-dir>\runtime\lifecycle-operation.lock`. Start holds this mutex until the child owns its
service lease and reports healthy; reset holds it through backup, owned stop, deletion,
reinitialization, and deep verification. A concurrent start/start or start/reset attempt fails
closed. The mutex file may remain as an inert runtime artifact; ownership is the operating-system
byte-range lock, not file existence.

Start also retains the mutex through the optional browser handoff. On any failure after launching
the child, it terminates and waits for that child, removes only the now-stale owned receipt/lease,
and then releases the mutex. Successful start disposes only its local process wrapper; the owned
service continues running.

The lifecycle concurrency tests do not infer overlap from timing or file existence. A test-only,
per-process PowerShell wrapper uses a random 256-bit token to pause the real start or reset script
at its first source-directory entry after the real byte-range lock has been acquired. The parent
independently proves byte 0 is locked, runs the competing independent PowerShell process, and then
releases the holder with the exact token. This wrapper exists only in the test process; no
test-only environment variable, barrier, delay, or test command is accepted by production
scripts.

After stopping the prior instance, reset acquires `service.json.lock` as a maintenance lease and
holds it through database deletion, initialization, and deep verification. The direct module entry
point contends on that same lease before opening the database, so direct-entry/reset races are
also fail-closed.

The service owns `<data-dir>\runtime\service.json` and `service.json.lock`. The canonical receipt
schema is `synthetic-sales-assist-runtime-receipt/v1` and carries exact app/build/schema versions
plus independent CSRF and shutdown tokens. The child acquires `service.json.lock` before opening,
initializing, migrating, or deeply verifying the database. Start launches that hidden background
process, waits for a passing `/health`, validates the exact
receipt/process identity, and only then opens `/scenarios` unless `-NoBrowser` is supplied.

Stop authenticates to the owned shutdown endpoint only after matching PID, OS creation time,
Python executable, readable active-lease token, data directory, database, receipt path, origin,
host, and port. CIM/WMI, command-line inspection, and elevation are not required; the random
active-lease identity plus two independently authenticated shutdown headers bind the real service.
Stop never invokes process-name termination, never sends a signal to the receipt PID, and never
force-kills an ownership mismatch.

Reset requires `-ConfirmReset`. If the configured database exists, it first creates a verified
timestamped backup beneath the configured backup directory. It then performs the same owned stop,
deletes only the exact database, journal/WAL/SHM sidecars, service receipt, and sibling lock,
reinitializes schema version 4, and runs deep verification. Backups, logs, exports, source, Git,
specifications, and unrelated files remain untouched.

Status always emits one closed member set for `RUNNING`, `STOPPED`, and `STALE`: state,
app/build versions, data/database path, schema and size, PID/origin/port, safety counters, and last
health. A live unhealthy or unreachable service remains `RUNNING` with `FAIL` or `UNAVAILABLE`
health; an unreadable stopped database reports unavailable schema/counter values without losing
the closed JSON report. Unavailable identity and counter values are explicit JSON `null` values.

The data root is normalized without a trailing separator before Windows argument quoting. Every
controlled `data`, `runtime`, `backups`, and related child is revalidated as a real directory;
symlinks, junctions, and other reparse points fail before files are read, written, backed up, or
removed.

An explicitly bound `-PythonPath` is authoritative and remains under the strict path policy. With
no parameter, the scripts first validate `python` from PATH, so a normal local non-reparse Python
remains preferred. Only when that candidate fails do they consider a nonempty `SSA_PYTHON`, which
must be an absolute path. The scripts never search through arbitrary reparse-point locations.

Every candidate must exist as a regular non-reparse `python.exe` leaf on a local drive and must
report CPython 3.12.x through a bounded isolated probe before application code runs. UNC, device,
URL, alternate-data-stream, mapped-network, and unsafe arbitrary reparse paths are rejected. The
only ancestor-reparse exception is the exact verified Codex primary-runtime location selected
through `SSA_PYTHON`; the exception never applies to `-PythonPath`, PATH, a suffix match, an alias,
or another reparse path. Before any interpreter invocation, an open Windows file handle resolves
that logical path to its final target. The final target is independently required to be a regular
local non-reparse `python.exe`, and that resolved path is the one probed and launched. The
subsequent application `doctor` call proves that the selected interpreter can load this exact
synthetic application before startup or reset continues.
