
# Implementation Doctrine

## Authority-required stop

Stop only when two plausible choices change:

- Sales Credit or DOI business result;
- reason or transition meaning;
- human approval or actor authority;
- source-completeness/evidence meaning;
- privacy exposure;
- retention/purge meaning or authorized survivors;
- KPI/accounting meaning;
- historical/synthetic classification;
- externally consumed replay or identity semantics;
- read-only safety.

## Bounded engineering decision

Codex may choose and document:

- physical SQLite table decomposition;
- join tables versus checked nullable foreign keys;
- indexes;
- internal DTO/class structure;
- repository and query helpers;
- serializable lock or compare-and-set mechanism;
- migration operation ordering with equivalent semantics;
- fixture organization;
- internal cache strategy;
- browser-side component organization.

Consequential choices require an ADR and tests.

## Internal detail

Helper functions, variable names, factoring, comments, and equivalent query optimizations do not
require escalation.

## Test-and-commit rule

Each milestone commits only after scoped tests, the complete available regression suite,
synthetic-identity scan, localhost-only scan, and secret scan pass on the same candidate tree.
