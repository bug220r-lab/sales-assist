# Milestone 7 screenshot-safe manager-demo route sequence

Prepare the fixed synthetic dataset while the local service is stopped. From the repository root,
use the same verified Codex Python 3.12 runtime as the M5/M6 development workflow:

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
& 'C:\path\to\approved-development-runtime\python.exe' `
    .\tools\prepare_milestone7_demo.py
```

The command uses the normal LocalAppData `SyntheticSalesAssist` runtime root, matching
`scripts/start.ps1` with no `-DataDir`. It emits canonical privacy-safe JSON and never includes an
absolute runtime path. A rerun preserves every ID and reports four exact evaluation replays. It
does not record a Sales Credit manager outcome or a DOI overlap selection; both actions remain
pending for the visible walkthrough. Start the service only after preparation completes.

The preparation creates these exact stable identities:

| Scenario | Order | Case | Evaluation | Run |
|---|---|---|---|---|
| Sales Credit target rep | `SYN-ORDER-M5-SC-018FB80ED91C1EBD` | `SYN-ORDER-M5-SC-018FB80ED91C1EBD` | `SYN-EVALUATION-M5-SC-018FB80ED91C1EBD` | `SYN-RUN-M5-SC-018FB80ED91C1EBD` |
| Sales Credit human review | `SYN-ORDER-M5-SC-86229FF7F2E2100A` | `SYN-ORDER-M5-SC-86229FF7F2E2100A` | `SYN-EVALUATION-M5-SC-86229FF7F2E2100A` | `SYN-RUN-M5-SC-86229FF7F2E2100A` |
| DOI fulfillment split | `SYN-ORDER-DOI-DEMO-B3A345A9AAB76E0E` | `SYN-EVIDENCE-M4-DOI-CASE-CDBA2B0FD86833CD6C96515A` | `SYN-EVALUATION-DOI-DEMO-B3A345A9AAB76E0E-FULFILLMENT-SPLIT` | `SYN-RUN-DOI-DEMO-B3A345A9AAB76E0E-FULFILLMENT-SPLIT` |
| DOI unresolved overlap | `SYN-ORDER-DOI-DEMO-5B5294694586A283` | `SYN-EVIDENCE-M4-DOI-CASE-A153ABFE7BF6A864850763EF` | `SYN-EVALUATION-DOI-DEMO-5B5294694586A283-OVERLAP` | `SYN-RUN-DOI-DEMO-5B5294694586A283-OVERLAP` |
| Malformed/incomplete | `SYN-ORDER-M5-MALFORMED-8499F4AC6427E3EF2B2EBA39` | Not created | Not evaluated | Not created |

After `scripts/start.ps1` reports healthy, follow these exact loopback routes. Add
`?presentation=1` only where the closed query contract accepts it; presentation mode suppresses
volatile local details and never hard-codes an outcome.

| Step | Route | Visible evidence |
|---:|---|---|
| 1 | `/system` | loopback origin, schema/database health, truthful extension state, and nine zero safety counters |
| 2 | `/overview` | current Sales Credit cases, DOI cases and opportunities, and items needing review |
| 3 | `/sales-credit/SYN-ORDER-M5-SC-018FB80ED91C1EBD` | separate current system classification and empty manager outcome |
| 4 | `/sales-credit/SYN-ORDER-M5-SC-86229FF7F2E2100A` | record a confirmed synthetic outcome, then demonstrate exact replay and changed-material conflict |
| 5 | `/doi/SYN-EVIDENCE-M4-DOI-CASE-CDBA2B0FD86833CD6C96515A` | fulfillment-split opportunity, exact scope, and ordered explanation |
| 6 | `/doi/SYN-EVIDENCE-M4-DOI-CASE-A153ABFE7BF6A864850763EF` | separate opportunities, RC-087, unavailable aggregate, then manually select a scenario |
| 7 | `/review` | domain-aware unresolved current review items |
| 8 | `/audit/evaluation/SYN-EVALUATION-DOI-DEMO-5B5294694586A283-OVERLAP` | immutable ordered timeline and receipts |
| 9 | `/orders/SYN-ORDER-M5-SC-018FB80ED91C1EBD` | open the M6 side panel on a supported source page, then use its ordinary validated dashboard deep link |
| 10 | `/orders/SYN-ORDER-M5-MALFORMED-8499F4AC6427E3EF2B2EBA39` | fail-closed incomplete evidence with recovery guidance and no successful evaluation |
| 11 | `/system/telemetry` | registry-bound rates, denominators, replay/conflict split, and currency tables |
| 12 | `/system/backups` | latest verified backup and receipt inventory |

Stable `data-ssa-dashboard-*` selectors identify the page, route, cards, state labels, tables,
actions, live regions, current projection, timeline, and evidence contract. IDs contain only
reserved synthetic values. There is no hidden tooltip-only evidence or live animation.

The sequence remains fully keyboard-operable and the pages remain truthful if no extension has
ever been observed, a backend has restarted, a denominator is empty, or value is unavailable.
