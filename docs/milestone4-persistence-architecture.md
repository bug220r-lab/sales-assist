# Milestone 4 persistence architecture

Milestone 4 adds one local SQLite database beneath the validated application-data root. It does
not add a portal, server, API, dashboard, browser extension, connector, or network client.

```text
existing synthetic scenario builders and pure rule packs
                         |
                  application services
                         |
           explicit SQLite unit of work
        /                |                 \
shared replay       Sales Credit         DOI histories
and telemetry       case graph           and projections
        \                |                 /
               verified local SQLite file
                         |
       online backup / verified atomic restore
```

Every application connection enables foreign keys, WAL, full synchronous durability, a bounded
busy timeout, strict row handling, and explicit transactions. Writers begin immediately and all
repositories participating in an operation share that transaction. No repository commits on its
own. Startup verifies the complete migration ledger and rejects a future or drifted schema.

Immutable rows retain complete canonical material and, where already defined by the domain, the
versioned hash domain and SHA-256 digest. Replay comparison uses complete bytes, never digest
equality alone. SQL triggers reject updates to events, snapshots, evaluations, evidence,
revisions, value history, closed audit records, and receipts. Mutable projections use expected
version/event-head compare-and-set and readback verification.

Sales Credit and DOI have independent foreign-key roots. Shared tables own only neutral commands,
receipts, telemetry, failures, safety snapshots, and backup/restore receipts. No cross-domain
foreign key or external-system capability exists.

Runtime database and backup files are not repository artifacts. Tests use explicitly selected,
isolated local temporary roots and delete them after verification.
