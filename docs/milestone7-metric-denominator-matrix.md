# Milestone 7 metric denominator matrix

- Registry: `synthetic-sales-assist-metric-denominators/v1`
- Authority: ADR 0026
- Default window: all retained terminal local synthetic business requests, explicitly labeled

Every computed rate record carries `numerator`, `denominator`, `defined`, and `display`. The
telemetry response carries the selected window beside those rates, and the versioned registry
supplies each metric's inclusions, exclusions, time basis, and empty-display rule. Overview cards
link to the corresponding registry entry on the telemetry route. Empty denominators render `N/A`.

| Metric | Numerator or basis | Denominator | Required exclusions / presentation |
|---|---|---|---|
| Requests received | terminal business-processing telemetry rows | not a rate | maintenance excluded; replays included and broken out |
| Unique evaluations | new durable Sales Credit and DOI evaluation IDs | not a rate | exclude replay, conflict, and malformed request without evaluation |
| Successful request rate | successful terminal business requests | all terminal business requests | exact replays included in request population and shown separately; maintenance excluded |
| Fail-closed rate | terminal business requests flagged fail-closed | all terminal business requests | maintenance excluded |
| Human-review rate | new unique evaluations whose current result requires review | new unique evaluations | replay and conflict excluded |
| Active Sales Credit cases | current nonclosed Sales Credit projections | not a rate | historical/closed/purged cases excluded |
| Manager-outcome rate | eligible presented cases with a recorded manager outcome | eligible cases actually presented for human decision | not-yet-eligible or unpresented cases excluded |
| Active DOI opportunities | current active opportunities | not a rate | closed/superseded/invalidated/purged opportunities excluded |
| DOI state distribution | current cases in each DOI state | current DOI case population | population definition displayed |
| Opportunity type count | current active opportunities of each type | not a rate | count may exceed case count and is labeled |
| Latency median/P95 | processing duration of terminal business requests | declared sample count | maintenance separate; replay sample visibly identified |
| Throughput | terminal business requests | declared wall-clock seconds | inclusion rules and unit displayed |
| Potential value | exact eligible opportunity potential | not a rate | grouped by currency; unavailable and unresolved overlap excluded and counted separately |
| Realized value | current exact verified intervention contribution | not a rate | grouped by currency; unverified actions excluded; correction/reversal applied once |
| Database/backup/safety | latest verified result or receipt | not a rate | timestamp and schema displayed; nine counters individually displayed |

No conversion or mixed-currency total is produced. `Unavailable` is distinct from exact zero.
Aggregate surfaces do not expose synthetic subject identity.
