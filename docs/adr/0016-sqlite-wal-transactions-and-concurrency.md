# ADR 0016: SQLite WAL transactions and concurrency

- Status: accepted for Milestone 4
- Scope: local SQLite connection, transaction, and concurrency mechanics

## Decision

Use one configured SQLite connection per unit of work. Every application connection enables
foreign keys, WAL journaling for file databases, `synchronous=FULL`, deterministic row handling,
and a bounded busy timeout. Reads use explicit read transactions when a coherent multi-query view
is required. Writers use `BEGIN IMMEDIATE`; repositories never commit independently of their
owning unit of work.

Replay lookup and complete canonical-byte comparison occur after the write transaction begins but
before allocation of an ID or trusted commit timestamp. Exact material returns the retained
receipt. Reusing a key with changed material is a conflict; equal digest with different canonical
bytes is a collision. Projection changes use expected version and expected event-head predicates,
then receive readback verification before commit.

SQLite serializes cross-process writers. A process-local maintenance coordinator gives immediate
same-process rejection, and a crash-released filesystem activity lock gives the same exclusion
across CLI processes. POSIX uses shared/exclusive `flock`. Windows uses standard-library
`msvcrt` byte-range locks: each ordinary operation retains one bounded shared-emulation slot and
maintenance atomically locks the complete slot range. Restore cannot enter its checkpoint/copy/
atomic-replacement boundary while any process retains an operation slot; new operations cannot enter
while maintenance owns the range. Busy handling is nonblocking at this maintenance boundary and
never converts a lock failure into implicit replay or success.

## Consequences

Readers can continue while a writer is active, while every multi-row business operation commits
fully before it becomes visible. Injected failures roll back the entire operation. A future schema
version, disabled foreign keys, failed integrity check, or exhausted busy budget fails closed
before business access. This is local single-database coordination, not a distributed protocol.
The activity-lock file is local runtime state beside the database, is never backed up, and is
automatically released by the operating system if a process terminates.
