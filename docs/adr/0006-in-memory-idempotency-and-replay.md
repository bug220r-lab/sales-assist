# ADR 0006: In-memory idempotency and replay

- Status: accepted for Milestone 1
- Scope: generic command identity and replay mechanics only

## Decision

An accepted command is identified by an immutable natural key and by a canonical token that
retains both its lowercase SHA-256 digest and its complete canonical bytes. The in-memory receipt
store performs the lookup and byte comparison under one lock before invoking any caller-supplied
ID, timestamp, or result allocator.

Exact key and byte replay returns the original immutable receipt. A reused key with a different
digest is a conflict. Equal digest with different canonical bytes is a distinct collision error;
digest equality never substitutes for byte equality. Receipt results are immutable canonical
bytes, not mutable application objects. Errors expose only closed codes.

## Consequences

The ordering rule is executable and concurrent callers cannot allocate twice for one exact
command. This store is deliberately process-local and nonpersistent. It establishes no business
natural key, transaction protocol, run terminalization rule, database table, or distributed-lock
strategy; those require later authorized designs.
