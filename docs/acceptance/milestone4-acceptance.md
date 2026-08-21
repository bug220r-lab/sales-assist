# Milestone 4 acceptance evidence

This repository-authored evidence binds the user-visible and automated acceptance of the exact
Milestone 4 commit. It does not modify or supersede any supplied specification.

| Item | Accepted value |
|---|---|
| Commit | `52b9a241d5ae7f3227c519dad18c2b3e9eab66ac` |
| Tree | `af0e8f165a743a3c09ee20fbc84db900fbfbee20` |
| Parent commit | `e302b21bedbf1bc8c59861ec735d8fbd164a4db3` |
| Schema version | `4` |
| Complete regression | `1,327/1,327 PASS` |
| Markdown operator report SHA-256 | `aa8d0b76e1a95d39524a0471bd919f6858e8f68cf057a8d471afb10d635215d8` |
| JSON operator report SHA-256 | `8978bf2d3b3e7124555e44f988aa8628ccac7fc01ba707a4e130aaa3789257df` |

```text
M4_MANUAL_ACCEPTANCE = PASS
M4_OPERATOR_ACCEPTANCE_AUTOMATED = PASS
```

The user visibly initialized and deeply verified an isolated schema-version-4 database, listed
the synthetic scenario catalog, ran the canonical Sales Credit and DOI demonstrations, observed
exact replay, inspected privacy-safe persisted metrics, and confirmed all safety counters were
zero.

The checksum-bound automated session independently proved exact replay, changed-material
conflict, online backup, atomic restore, persistence across a fresh process, and the complete
1,327-test regression. The exact committed tree remained clean. All nine safety counters were
zero and runtime network calls were zero throughout the accepted evidence.
