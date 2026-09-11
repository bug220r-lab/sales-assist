# ADR 0032: private Windows runtime and complete application backups

Status: accepted, 2026-09-11.

Sales Assist 0.2.0 remains a synthetic-only local application with the existing browser
interface. The Windows x64 distribution bundles a private CPython 3.12.14 interpreter
and tzdata 2026.3. It does not discover or depend on Codex or machine Python, install
dependencies at startup, add an external transport, or change the business specifications.
The existing external-runtime demo builder remains available for its historical contract.

The offline Windows application builder takes exact pinned upstream archives as inputs.
The Python input is the astral-sh/python-build-standalone 20260901 Windows x64 stripped
installation archive; the timezone input is the tzdata 2026.3 wheel from PyPI. Input
hashes, origins, versions and licenses are pinned in tools/windows_runtime_lock.json.
Archive validation rejects unsafe paths, links, collisions and over-limit members before
packaging. Runtime libraries and their license notices are preserved under python/.
Source commits contain the builder and lock, not downloaded binaries or mutable app data.

A private python312._pth permits only the bundled standard library, DLLs, site-packages
and the packaged application src directory. Site initialization and Python environment
overrides do not supply application imports. Every production launcher invocation uses
-B to preserve runtime inventory bytes and prevent unlisted bytecode caches. The central
PowerShell selector verifies the runtime manifest, paths, file hashes and complete file
inventory before executing the existing bounded interpreter identity probe. It then
checks private SQLite and timezone imports. Existing path, process ownership, lease and
localhost protections remain binding. A required broken bundle never falls back to PATH
or SSA_PYTHON. The unsigned package's hashes establish integrity, not publisher authenticity.

The one-click dispatcher reopens an already healthy owned instance only when its data
marker matches the package source commit; explicit port disagreement remains an error.
For a fresh start with no explicit port, an occupied default port permits one ephemeral
loopback-port selection. The normal listener bind remains authoritative if a race occurs.
Other processes are never stopped to obtain a port. Direct start.ps1 retains its existing
second-start rejection. Only successful START closes its console automatically; status,
backup and maintenance launchers retain readable output. Builder recipe and runtime-lock
text must match the requested Git snapshot before publishing archives.

First launch seeds the campaign workspace alongside the existing order scenarios. Reopen
and upgrade preserve campaign drafts, history, review revisions and protected send state.
Before adoption or backup, both database identities are checked. New release markers
record the campaign-store format so a subsequently missing workspace cannot silently
be treated as a fresh database.

Application backup creates the existing verified core SQLite backup and a separately
verified campaign SQLite backup, then writes a manifest binding their identities and
hashes. They are independent snapshots, not one transaction across two databases.
The campaign companion lives outside the core backup inventory namespace. Partial failure
does not produce a success manifest; a failed upgrade backup prevents marker advancement.
Existing core receipt and schema-4 contracts remain unchanged. The order backup UI still
has its narrower core scope, documented beside the whole-app BACKUP.cmd workflow.

RESET.cmd remains a confirmed order-demo reset. It now takes a whole-app backup first,
and explicitly preserves campaign history/drafts. A fresh extracted installation provides
a fresh whole-app demo through the existing installation-specific data selection. We do
not invent a cross-store destructive reset or restore protocol as part of packaging.

Conservative removal retains python/ because the interpreter and DLLs are executing from
that directory on Windows. The result reports retained runtime files; the guide explains
optional folder removal after exit. No recursive deletion, force-kill, automatic update,
or manipulation of unrelated data is added.

Release evidence must identify the immutable source commit/tree, vendor inputs and archive
hashes. Same-PC tests remove PATH Python and SSA_PYTHON and supply hostile Python environment
settings; extracted-package startup, persistence, backup, stop/restart and corruption checks
must pass. Browser observations, independent review, human acceptance and a separate clean
Windows machine/VM remain distinct evidence categories.
