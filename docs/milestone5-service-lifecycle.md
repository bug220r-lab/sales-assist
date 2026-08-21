# Milestone 5 Windows service lifecycle

The four operator scripts run without administrator rights and always require an explicit local
data directory in tests. Their production default is `%LOCALAPPDATA%\SyntheticSalesAssist`.

```powershell
scripts\start.ps1 [-PythonPath PATH] [-DataDir PATH] [-Port 8765] [-NoBrowser]
scripts\status.ps1 [-PythonPath PATH] [-DataDir PATH]
scripts\stop.ps1 [-PythonPath PATH] [-DataDir PATH]
scripts\reset-demo.ps1 -ConfirmReset [-PythonPath PATH] [-DataDir PATH] [-Port 8765]
```

The scripts serialize lifecycle-changing work with
`<data-dir>\runtime\lifecycle-operation.lock`. Start holds this mutex until the child owns its
service lease and reports healthy; reset holds it through backup, owned stop, deletion,
reinitialization, and deep verification. A concurrent start/start or start/reset attempt fails
closed. The mutex file may remain as an inert runtime artifact; ownership is the operating-system
byte-range lock, not file existence.

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

An explicitly supplied Python runtime must resolve to an absolute regular file on a local drive.
UNC/device paths, alternate data streams, mapped network drives, and any reparse ancestor are
rejected before execution. The subsequent application `doctor` call proves that the resolved
interpreter can load this exact synthetic application before startup or reset continues.
