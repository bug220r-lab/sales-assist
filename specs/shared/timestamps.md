
# Timestamp Contract

## Semantic requirements

- Every stored timestamp is timezone-aware.
- Business calendar calculations use `America/New_York` where the source specification
  requires that calendar.
- Input accepts the source-defined RFC-3339 subset with required `Z` or numeric offset.
- Canonical representation is UTC `Z`.
- Input may contain up to nine fractional digits.
- Canonical output removes unnecessary trailing fractional zeroes.
- Naive timestamps are rejected.
- Equivalent instants have identical canonical bytes.
- Immutable JSON stores a string; SQLite logical storage is `TEXT COLLATE BINARY`.
- Timestamp equality for hash-bearing objects is canonical-instant equality.

## Primitive hash

```text
SHA256(
  UTF8("doi-timestamp/r01-v1")
  || LF
  || UTF8(canonical_timestamp)
)
```

The implementation must independently reproduce the published primitive known-answer digest:

```text
ba8fc05dbdbba6fec52a3ed7b0a93a0d8dbb8512e9fe95c56d6d4bd4708d2112
```

## Required validation

Tests must cover valid offsets, UTC normalization, fractional boundaries, invalid dates,
naive input, excessive precision, noncanonical equivalents, SQLite round trip, and canonical
hash equality.

## Source-time coherence

When order-level and whole-order-proof source-observed timestamps coexist, their canonical
instants must be equal. Mismatch or an unnormalizable source timestamp fails extraction
before successful snapshot construction.
