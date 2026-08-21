# Milestone 3 DOI domain model

The model is an immutable logical graph; it is not a relational schema.

## Source and run graph

```text
DOIRun
  -> source-import attempts -> optional coherent DOISourceBatch
  -> staged orders or rejected source records
  -> run work items -> exactly zero or one terminal disposition per subject
  -> append-only run and attempt events
```

A failed source attempt ends only that attempt. The parent run remains in progress until a legal
next ordinal or an explicit authorized no-retry finalization wins the run-control boundary.

## Case and evaluation graph

```text
DOIOrderCase
  -> admission/source binding
  -> extraction attempts -> complete DOIOrderSnapshot
  -> ordered DOI line snapshots and continuity proofs
  -> evaluations
       -> exact reason set and registered transition
       -> immutable opportunity scopes
       -> handling, attention, review, and closure dimensions
```

Facts are observations; conclusions are derived. Missing required data is extraction failure.
UNKNOWN is a successfully observed but unnormalizable field and blocks only dependent conclusions.

## Product and coordination graph

Product relationships are product-only natural keys with immutable revisions and current
observations. Case/customer/order/contact material is prohibited from those identities. Contact,
WWC, DEDUPE, Action Context, human facts, and cause-keyed attention each retain separate factual
event streams. A structured fact may bind a case scope but unrestricted note text never becomes a
business conclusion.

Mutually exclusive opportunity grouping is a separate immutable evidence record. It binds the
exact evaluation, order, group, and complete candidate option set to an authorized structured
human fact. Bare caller identifiers and incomplete option partitions cannot alter aggregation.

DEDUPE approval and DEDUPE confirmation are distinct. Approval binds the exact authorized human
fact and yields only `APPROVED_AWAITING_VERIFICATION`. Confirmation requires a separate later
complete snapshot with distinct snapshot, run, and finding identities; exact same-order/source
bindings; both snapshot/finding hashes; the prior approval and projection; and source/finding
observation instants strictly after approval. Reusing the pre-approval finding or supplying only a
later timestamp cannot close the case.

## Intervention and KPI graph

```text
opportunity + exact scope
  -> verified action evidence -> intervention occurrence
  -> optional exact resulting-order link and mapping revisions
  -> value / correction / partial reversal / full reversal events
  -> one current retained KPI contribution
  -> identity-free currency/date aggregate at case purge
```

Recommendations and opportunities are not interventions. Ambiguity or unverified evidence
contributes zero realized value. Histories append; prior events are never rewritten.
