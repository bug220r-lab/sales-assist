# Milestone 6 acceptance evidence

This repository-authored record binds the accepted Milestone 6 extension and lifecycle-remediation
state. It preserves the earlier failed operator reports as historical evidence and does not modify
or supersede the protected specification bundle.

| Item | Accepted value |
|---|---|
| Accepted commit | `1ff8198e19af7cbcf9f153c36a66bcfef1c5a45f` |
| Accepted tree | `d07f75737eb6a5e891d002cea8a89c6d0d146c67` |
| Parent commit | `16d1fa2a0b369c257c0e90428785f82efe12fd5f` |
| Complete regression | `1,522/1,522 PASS` |
| Lifecycle concurrency | `40/40 PASS` |
| M5 scoped regression | `116/116 PASS` |
| M6 scoped regression | `80/80 PASS` |
| Current-byte Chrome | `45/45 PASS` |
| Documented panel states | `16/16 PASS` |
| Extension version | `0.1.0` |
| Extension ZIP SHA-256 | `acb0ff977e24d69a7d4fab0d1426ef5eba30c0d8ec9b86a1ab744a6b9319210d` |
| Runtime external requests | `0` |
| Port `8765` listeners after acceptance | `0` |

```text
MILESTONE_6_LOCALHOST_CHROME_EXTENSION = PASS
M6_LIFECYCLE_CONCURRENCY_REMEDIATION = PASS
M6_VISIBLE_CHROME_SMOKE = PASS
M6_POST_REMEDIATION_VISIBLE_SMOKE = PASS
M6_OPERATOR_ACCEPTANCE_AUTOMATED = PASS
M6_MANUAL_ACCEPTANCE = PASS
```

## Successful successor acceptance reports

| Report | SHA-256 |
|---|---|
| `M6_OPERATOR_ACCEPTANCE_RERUN_REPORT.md` | `cdaf4de076e5ef5fab92287af09d653a130c1c9731908343161df6745c12aecd` |
| `M6_OPERATOR_ACCEPTANCE_RERUN_REPORT.json` | `ad194987fd60a23694085ca7756b813f52301216e470874ecdfb6e21530ae4ba` |
| `M6_OPERATOR_ACCEPTANCE_RERUN_REPORT.sha256` | `8cb7fae3e1f5551a15e315890d41cbcc0f39fd4dbb812c403dd22d6a68e09291` |

The prior failed operator-acceptance reports remain preserved as historical evidence. The narrow
lifecycle remediation classified the reproduced failure as a timing-dependent test defect and
closed the related failed-start cleanup-lock gap. The fresh successor acceptance reran the exact
accepted tree and produced the successful report set above. It did not rewrite the earlier record.

## Extension security identity

The accepted extension is Chrome Manifest V3, version `0.1.0`. Its complete permission authority
is exactly:

```text
permissions:
- sidePanel

host_permissions:
- http://127.0.0.1/*
- http://localhost/*
```

There are no optional permissions, wildcard internet hosts, remote assets, or production
capabilities. The accepted package SHA-256 is recorded above.

## Accepted service and data versions

| Contract or component | Exact version |
|---|---|
| API response | `synthetic-sales-assist-api/v1` |
| API request | `synthetic-sales-assist-api-request/v1` |
| DOM contract | `synthetic-sales-assist-dom/v1` |
| Application view | `synthetic-sales-assist-application/v1` |
| Application | `0.1.0` |
| Build | `synthetic-sales-assist-m5/v1` |
| Runtime receipt | `synthetic-sales-assist-runtime-receipt/v1` |
| Database schema | `4` |
| Service origin | `http://127.0.0.1:8765/` |

## Zero safety ledger and terminal state

Every accepted live and final-gate observation contained these exact nine counters at integer
zero:

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

The accepted successor session also proved zero runtime external requests, service stopped, zero
listeners on port `8765`, exact commit/tree, and a clean index, worktree, and untracked inventory.
This evidence authorizes Milestone 7 work only; it does not authorize production connectivity or
Milestone 8 packaging.
