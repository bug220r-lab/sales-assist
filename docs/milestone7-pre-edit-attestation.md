# Milestone 7 pre-edit attestation

This is the repository record of the mandatory read-only checks completed before the first
Milestone 7 file was created. The prompt arrived through direct chat, so
`tasks/milestone7_control_center_dashboard.txt` was absent during this attestation and was created
only after every check below passed.

## Exact repository state

| Item | Observed value |
|---|---|
| Branch | `main` |
| `HEAD` | `1ff8198e19af7cbcf9f153c36a66bcfef1c5a45f` |
| `HEAD^{tree}` | `d07f75737eb6a5e891d002cea8a89c6d0d146c67` |
| Parent | `16d1fa2a0b369c257c0e90428785f82efe12fd5f` |
| Tracked paths represented by the tree | `320` |
| `git status --porcelain` | empty |
| Index diff | empty |
| Worktree diff | empty |
| Untracked inventory | empty |
| M7 task file | absent, as permitted for direct-chat delivery |
| M7 implementation artifacts | zero |
| M8 implementation/release artifacts | zero |

The exact Git tree above is the cryptographic pre-edit inventory. Protected `specs/`,
`reference/`, `BUNDLE_MANIFEST.json`, `SHA256SUMS.txt`, the checksummed root `README.md`, and all
four migration files matched their committed bytes. No external or pre-existing workspace change
was admitted.

## Accepted regression, runtime, and safety observations

- Complete repository suite: `1,522/1,522 PASS`; only the documented Windows directory-symlink
  capability skip occurred, with the equivalent reparse-point canaries passing.
- M6 scoped: `80/80 PASS`.
- The explicit validated `SSA_PYTHON` DEVELOPMENT / NONPORTABLE fallback started the portal,
  health returned PASS at `http://127.0.0.1:8765/`, status retained exact application/runtime
  identity, owned stop succeeded, and listener count before and after was zero.
- API response `synthetic-sales-assist-api/v1`, request
  `synthetic-sales-assist-api-request/v1`, DOM `synthetic-sales-assist-dom/v1`, application view
  `synthetic-sales-assist-application/v1`, application `0.1.0`, build
  `synthetic-sales-assist-m5/v1`, runtime receipt
  `synthetic-sales-assist-runtime-receipt/v1`, and database schema `4` all matched.
- Runtime external network requests, real-data records, production-system accesses, external
  mutations, and all nine safety counters were zero.

## Committed M5 route registry

This exact method/path inventory was derived from
`src/synthetic_sales_assist/portal/server.py` at the accepted base before any M7 route was added.
The closed identifier expressions are the ones recorded in
`docs/milestone6-route-contract.md`.

| Method | Exact path or closed expression |
|---|---|
| `GET` | `/` |
| `GET` | `/health` |
| `GET` | `/api/v1/scenarios` |
| `POST` | `/api/v1/scenarios/{alias}/instantiate` |
| `GET` | `/api/v1/orders` |
| `GET` | `/api/v1/orders/{order_id}` |
| `POST` | `/api/v1/orders/{order_id}/evaluate` |
| `GET` | `/api/v1/orders/{order_id}/history` |
| `GET` | `/api/v1/interactions/{interaction_id}` |
| `GET` | `/api/v1/runs/{run_id}` |
| `GET` | `/api/v1/metrics/summary` |
| `GET` | `/api/v1/system/status` |
| `POST` | `/api/v1/system/shutdown` |
| `GET` | `/scenarios` |
| `GET` | `/orders` |
| `GET` | `/orders/{order_id}` |
| `GET` | `/interactions/{interaction_id}` |
| `GET` | `/runs/{run_id}` |
| `GET` | `/static/ssa.css` |
| `GET` | `/static/ssa.js` |

## Database and migration inventory

Schema was exactly version `4`; quick check was `ok`, foreign-key violations were zero, and the
projection verifiers passed.

| Version | Migration | Bytes | SHA-256 |
|---:|---|---:|---|
| 1 | `0001_foundation.sql` | 1,287 | `5693cfe9868f10868d134bd042ccc26271126be9eae847a214c26f57216d6638` |
| 2 | `0002_shared_persistence.sql` | 10,137 | `5e6f5ea08a4cfd5ec6241da60c49721d99c246fa1e4251d44293a1487e749e31` |
| 3 | `0003_sales_credit_persistence.sql` | 20,824 | `fd22b13f73d389422405bf222313e34a4aa5995f6b28610a222108a3da813395` |
| 4 | `0004_doi_persistence.sql` | 36,268 | `5799e5fe3b0e1c9ffae948f6c6b0a820556a9a0d200b29d7c5751e80c475b09d` |

## Accepted extension package inventory

- Manifest: Chrome MV3, version `0.1.0`.
- Permissions: exactly `sidePanel`.
- Host permissions: exactly `http://127.0.0.1/*` and `http://localhost/*`.
- Checked-in inventory: `chrome_extension/package_inventory.json`, 11 packaged files,
  SHA-256 `366bc639e2be6c9be2ff349ce0995d76a4e574af101ef28b00c4aa7b376ce65a`.
- Deterministic ZIP SHA-256:
  `acb0ff977e24d69a7d4fab0d1426ef5eba30c0d8ec9b86a1ab744a6b9319210d`.

The inventory bound these exact file records:

| Path | Bytes | SHA-256 |
|---|---:|---|
| `content/content_script.js` | 34,417 | `5d5240e74b2d0bc85a36c0b18a2d99ca4f6bc1064942543a783296af80f349d1` |
| `manifest.json` | 1,170 | `81e29390b08d19db4a29934be0f1b983fba0fa9808d0eabc3c34ff1e26ede53f` |
| `README.md` | 7,082 | `2b022f22a17b2aefaf804a368409eb866b04bfb8fcfc954358b896b6852b69c6` |
| `service_worker.js` | 1,457 | `4d7f471720d6a1d22e67ab6e944abe6ab6138f4c52f06004f37497a84d1ae7b0` |
| `shared/canonical.js` | 4,057 | `3937612403f1e021d877fab047ecd44524c27ce854fd7354a6398599e1e7a8d7` |
| `shared/contracts.js` | 30,436 | `50f445072a954d4d87845409bf43adec07df2f49c9bdcc3e5fba35c65581f101` |
| `shared/extraction.js` | 28,739 | `f4dde4464a764a4bfedb20a4c091033e6af228bcde16ae08ac8ab8d9e85f2e9c` |
| `shared/origin.js` | 2,135 | `44188f68a56e9c9498fc808d14a3a2216c38f3defcac7ef92cff9a9d87da081b` |
| `side_panel/index.html` | 3,119 | `c7aa21231076a78cf7fa437fdd27e893b6fecd2a57770e1b51a4616da52304b2` |
| `side_panel/panel.css` | 2,470 | `14833b5012c8989ecc143e478d967ddb4e01dd59f5121af71e23a0f81eed35e7` |
| `side_panel/panel.js` | 11,320 | `ed3312cf24615634e04415eccf19bd3a375e8904886d3c71adaa646dce6ded36` |

## Acceptance-evidence binding

The successful successor reports were readable and their recomputed SHA-256 values matched:

| Report | SHA-256 |
|---|---|
| `M6_OPERATOR_ACCEPTANCE_RERUN_REPORT.md` | `cdaf4de076e5ef5fab92287af09d653a130c1c9731908343161df6745c12aecd` |
| `M6_OPERATOR_ACCEPTANCE_RERUN_REPORT.json` | `ad194987fd60a23694085ca7756b813f52301216e470874ecdfb6e21530ae4ba` |
| `M6_OPERATOR_ACCEPTANCE_RERUN_REPORT.sha256` | `8cb7fae3e1f5551a15e315890d41cbcc0f39fd4dbb812c403dd22d6a68e09291` |

The accepted extension bytes, package, service, database, safety ledger, and stopped/listener-zero
terminal state therefore authorized Milestone 7 work. They did not authorize Milestone 8.
