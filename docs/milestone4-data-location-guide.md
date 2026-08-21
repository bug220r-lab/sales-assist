# Milestone 4 data-location guide

The default application root is:

```text
%LOCALAPPDATA%\SyntheticSalesAssist\
```

Its controlled layout is:

```text
data\synthetic_sales_assist.sqlite3
logs\
backups\
runtime\
exports\
```

The default never points into the Git checkout or a OneDrive-synchronized repository. Tests and
isolated local instances may use an explicit absolute `--data-dir`. Resolution rejects relative
paths, `..` traversal, URLs, UNC/network shares, Windows device paths, alternate data streams,
symlink/reparse escapes, protected specification/reference paths, and the active repository root.
No administrator access is required.

`db init` is the command that creates the controlled directories and database. Read-only status
commands do not silently create an instance. Runtime database, journal, WAL, shared-memory,
temporary restore, backup, and receipt files remain untracked.
