# Milestone 4 migration verification

Generated from the immutable migration bytes and a fresh in-memory database.
Executable tests reject any document or migration drift.

- Latest schema version: 4
- Migration files: 4
- Fresh applied versions: 1, 2, 3, 4
- Exact replay applied versions: []
- SQLite quick check: `ok`
- Foreign-key violations: 0
- Tables: 79
- Indexes: 20
- Triggers: 61

| Version | Migration | Bytes | SHA-256 |
|---:|---|---:|---|
| 1 | `0001_foundation.sql` | 1287 | `5693cfe9868f10868d134bd042ccc26271126be9eae847a214c26f57216d6638` |
| 2 | `0002_shared_persistence.sql` | 10137 | `5e6f5ea08a4cfd5ec6241da60c49721d99c246fa1e4251d44293a1487e749e31` |
| 3 | `0003_sales_credit_persistence.sql` | 20824 | `fd22b13f73d389422405bf222313e34a4aa5995f6b28610a222108a3da813395` |
| 4 | `0004_doi_persistence.sql` | 36268 | `5799e5fe3b0e1c9ffae948f6c6b0a820556a9a0d200b29d7c5751e80c475b09d` |
