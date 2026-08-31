# Milestone 5 acceptance evidence

This repository-authored record binds the user-visible and automated acceptance of the exact
Milestone 5 launcher-remediation tree. It does not modify or supersede the protected specification
bundle.

| Item | Accepted value |
|---|---|
| Feature commit | `1dd40ea9ec782e376cb154c5aa59ccf23bc6dade` |
| Launcher-remediation commit | `28909059cc1ef8a77e3a4bf428782dbf0280d7c4` |
| Accepted tree | `27ec8ddccb4d2428af5a6b92d5420f1bbb1a18e7` |
| Launcher-remediation parent | `1dd40ea9ec782e376cb154c5aa59ccf23bc6dade` |
| Complete regression | `1,446/1,446 PASS` |
| M5 scoped regression | `110/110 PASS` |
| Safety regression | `46/46 PASS` |
| `M5_OPERATOR_ACCEPTANCE_REPORT.md` SHA-256 | `4d01127af51bb46990a5a9d3c5269419f678a232e5461913106b4b1f06051d52` |
| `M5_OPERATOR_ACCEPTANCE_REPORT.json` SHA-256 | `e66f39cda51ccf6261ddd1dc91e0d4830cd3c33734a80ad6f250058ffa51e4e5` |
| Runtime external network requests | `0` |
| Non-blocking discrepancies | `7`, all documented and resolved |

```text
M5_VISIBLE_BROWSER_SMOKE = PASS
M5_OPERATOR_ACCEPTANCE_AUTOMATED = PASS
M5_MANUAL_ACCEPTANCE = PASS
```

## Evidence provenance

The checksum-bound automated report was finalized before the user supplied the authoritative
manual-acceptance declaration. Its JSON therefore truthfully records
`manual_acceptance_declared: false` and does not claim that automation replaced personal visual
inspection. In the later Milestone 6 authorization, the user separately and authoritatively
declared `M5_MANUAL_ACCEPTANCE = PASS` and identified the visible checks performed. These are two
different evidence events, not conflicting assertions.

The accepted launcher lineage is the original M5 implementation commit
`1dd40ea9ec782e376cb154c5aa59ccf23bc6dade`, followed by the narrow launcher compatibility child
`28909059cc1ef8a77e3a4bf428782dbf0280d7c4`. The child preserves a normal local, non-reparse
CPython 3.12.x as the preferred interpreter. The verified Codex-runtime exception remains explicit
`SSA_PYTHON`-only, DEVELOPMENT / NONPORTABLE, final-path checked, and unavailable to arbitrary
reparse-point paths. It makes no portable-release claim.

## Accepted versions

| Contract or component | Exact version |
|---|---|
| API envelope | `synthetic-sales-assist-api/v1` |
| API request | `synthetic-sales-assist-api-request/v1` |
| DOM | `synthetic-sales-assist-dom/v1` |
| Application view | `synthetic-sales-assist-application/v1` |
| Application | `0.1.0` |
| Build | `synthetic-sales-assist-m5/v1` |
| Runtime receipt | `synthetic-sales-assist-runtime-receipt/v1` |
| Database schema | `4` |
| Default origin | `http://127.0.0.1:8765/` |

## Zero safety ledger

Every accepted live, lifecycle, persistence, and final-gate observation contained the exact nine
counter names below, all at integer zero:

| Counter | Value |
|---|---:|
| `PRODUCTION_SYSTEM_ACCESS_COUNT` | 0 |
| `PRODUCTION_MUTATION_REQUEST_COUNT` | 0 |
| `REAL_CUSTOMER_IDENTITY_COUNT` | 0 |
| `NON_SYNTHETIC_FIXTURE_COUNT` | 0 |
| `SECRET_MATERIAL_COUNT` | 0 |
| `EXTERNAL_PRODUCTION_SYSTEM_ACCESS_COUNT` | 0 |
| `EXTERNAL_MUTATION_REQUEST_COUNT` | 0 |
| `NON_LOCALHOST_RUNTIME_REQUEST_COUNT` | 0 |
| `REAL_CUSTOMER_DATA_COUNT` | 0 |

The accepted operator session additionally proved zero external runtime network requests,
loopback-only listening, exact replay and changed-material conflict behavior, fail-closed malformed
representations, persistence across restart, owned stop/reset, protected-file integrity, and a
clean accepted commit/tree. Seven automation-harness or timing discrepancies were recorded in the
checksum-bound reports; each was corrected or independently rerun, none changed application
behavior, and the final same-tree gates passed.

This document records M5 evidence only. It does not authorize production connectivity or implement
Milestone 7.
