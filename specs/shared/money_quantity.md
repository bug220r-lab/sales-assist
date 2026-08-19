
# Money and Quantity Contract

## Quantity decision

The four governed source quantity fields are integer-only:

- ordered quantity;
- active quantity;
- canceled quantity;
- explicitly available quantity.

Domain:

```text
minimum = 0
maximum = 999999999
scale = 0
canonical grammar = 0|[1-9][0-9]{0,8}
```

Immutable JSON stores Quantity as a string. SQLite logical storage is `TEXT COLLATE BINARY`.
JSON numeric values, SQLite REAL, binary floating point, signs, exponents, commas, nonzero
fractions, rounding, truncation, and ambiguous provider numerics are forbidden.

Exact decimal source text may normalize to an integer only when every fractional digit is zero
and the source proves exactness. A parsed nonzero fractional quantity fails before snapshot
or rule construction; it is not converted to UNKNOWN.

Scoped/moved quantities require `1..999999999`.

## Money

Money uses exact decimal arithmetic and an explicit currency. Business decisions never use
binary float. Quantity × unit price is exact and may not silently round. If exact input or
currency validity is unavailable, the calculated value is UNAVAILABLE and the relevant reason
set is emitted.

## Value coherence

The implementation must define and test one exact source-of-truth policy for:

- order total;
- line extended value;
- quantity × unit price;
- available-to-ship value;
- opportunity potential;
- realized intervention value.

Any mismatch follows the governed fail-closed or human-review route and is never hidden.
