# DOI Synthetic Test Catalog

The source-derived baseline contains 312 base IDs across 29 families. These are planning requirements, not proof of executable collection. Codex must regenerate actual collected IDs/selectors and reconcile every ownership reference.

| Family | Source-derived base IDs |
|---|---:|
| `ACTX` | 8 |
| `ALT` | 17 |
| `ALT-REV` | 8 |
| `BATCH-REF` | 7 |
| `CUR` | 6 |
| `DED` | 8 |
| `EVAL-PROV` | 8 |
| `EXT` | 10 |
| `GEO` | 4 |
| `IDEM` | 12 |
| `IMPORT-RET` | 22 |
| `INT` | 21 |
| `INT-HIST` | 5 |
| `KPI` | 19 |
| `LIFE-PAYLOAD` | 12 |
| `LINE` | 3 |
| `LINK-HIST` | 8 |
| `OA-CAP` | 4 |
| `OA-RO` | 9 |
| `OA-RO-PROV` | 2 |
| `PRV` | 4 |
| `PURGE-EDGE` | 4 |
| `REASON-OWN` | 10 |
| `RET` | 20 |
| `RULE` | 14 |
| `SCOPE` | 10 |
| `SRC` | 31 |
| `STATE` | 17 |
| `WWC` | 9 |

## Rules


- Do not preserve `312`, `425`, or any successor count artificially.
- Every ID and selector in the implemented registry must be collected by the real test runner.
- Table-driven parameter IDs must be stable, unique, and referenced exactly.
- Reserved identity examples are not executable tests.
- Historical records are never synthetic fixture targets.
