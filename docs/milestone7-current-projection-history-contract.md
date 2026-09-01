# Milestone 7 current projection and immutable history contract

- Contract: `synthetic-sales-assist-control-center-projection/v1`
- Database schema: `4` (unchanged)
- Authority: ADR 0023

## Population rules

| Surface | Source | Included | Excluded |
|---|---|---|---|
| Current Sales Credit queue/card | latest `sc_cases` projection | current nonclosed cases | closed/purged cases and every prior event/evaluation |
| Current DOI queue/card | latest `doi_case_projections` joined to its current evaluation | current nonterminal cases | hard/reversible closed, superseded, invalidated, or purged material |
| Active DOI opportunity count | opportunities owned by each current active evaluation | current active opportunity rows | prior-evaluation, closed, superseded, invalidated, and purged opportunities |
| Human-review queue | current projections that presently require domain-specific human authority | unresolved Sales Credit and DOI review items | resolved review events and prior evaluations |
| Audit/timeline | immutable owner events, evaluations, artifacts, and command receipts | retained historical evidence for one reserved synthetic subject | deleted identity, raw SQL rows, unrestricted payloads, and reconstructed purged identity |
| Request telemetry | terminal processing rows in the selected declared window | success, fail-closed, exact replay, and conflict according to registry definition | nonterminal work and maintenance unless explicitly selected |

An exact replay is another request receipt but not another evaluation. A changed-material conflict is
a rejected request but not a successful item or a case mutation. Every card population is computed
from the same bounded query contract as its linked list; `total_count`, page counts, and returned
rows reconcile to that population.

## Closed query contract

Dashboard list routes admit only these normalized controls:

- `q`: omitted or a reserved-synthetic identifier prefix, maximum 96 ASCII characters;
- `state`: omitted or an exact allowlisted current state for that domain;
- `sort`: an exact route-specific field token;
- `direction`: `asc` or `desc`;
- `page`: integer 1 through 10,000;
- `page_size`: one of 10, 25, or 50.

Unknown fields, duplicate fields, empty values, invalid percent escapes, arbitrary operators, SQL
syntax, real-looking identity, hidden-payload search, and an out-of-range value fail closed. Stable
ordering always ends with the synthetic primary identifier as a tie breaker.

## Invariants

1. Current cards equal an unpaginated count of the same current filtered projection.
2. Historical events cannot add queue members.
3. Exact replays cannot add unique evaluations.
4. Conflicts cannot add successful requests, cases, or events.
5. Resolving one DOI attention cause cannot clear another cause.
6. Purged identity cannot be reconstructed from aggregate or audit output.
7. Aggregate responses contain no subject identity.
8. Ordinary demo responses contain no absolute local path or local username.

The executable reconciliation tests named by the M7 generated traceability gate are the release
authority for these statements.
