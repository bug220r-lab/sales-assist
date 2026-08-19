# Pre-Milestone 0 Specification Reconciliation v1.0.1

This document records the narrow correction made after Codex's mandatory pre-edit
contradiction gate. No business-rule inventory count changes.

## Decision 1 — Failed source attempts

A terminal failed source-import attempt does **not** terminalize its parent run merely because
no retry has yet been accepted.

The run remains `IN_PROGRESS` until exactly one serialized command wins:

- a legal next-ordinal retry; or
- an authorized human's explicit
  `FINALIZE_FAILED_SOURCE_IMPORT_NO_RETRY` command.

Absence of both commands is not an event. There is no timeout, expiry, background finalizer,
or automatic failure.

`TR-100` terminalizes only the source-import attempt. `TR-004` branch
`SOURCE_IMPORT_FAILED_EXPLICIT_NO_RETRY` terminalizes the parent run only after the explicit
command commits.

## Decision 2 — RC-084

RC-084 retains one identity: `RULE_VERSION_UNAVAILABLE`.

Its closed legal emission sites are:

1. evaluation-level rules-version handling through `TR-027` / `TR-037`; and
2. pre-extraction run-level systemic failure through `TR-004` branch
   `PRE_EXTRACTION_RULES_UNAVAILABLE`.

The run-level branch is legal only before extraction-occurrence reservation, appends no
evaluation, performs zero portal reads, records zero order dispositions, and serializes against
extraction reservation.

## Inventory preservation

```text
DOI reasons = 138
DOI reason-ownership rows = 138
DOI transitions = 115
```

Every emission site still requires a real collected executable test before its consuming
milestone commits.
