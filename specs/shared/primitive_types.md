
# Shared Primitive Types

## Canonical JSON

Hash-bearing objects use one deterministic canonical JSON implementation. Duplicate keys,
non-finite numbers, invalid UTF-8, unknown closed-object members, and noncanonical aliases
are rejected before hashing or persistence.

## IDs

Internal IDs are opaque, bounded, non-customer-derived strings. They do not encode email,
phone, name, address, order content, or product content. Referential IDs must resolve to
exactly one retained owning object when their contract requires it.

## Hashes

SHA-256 values are lowercase 64-character hexadecimal strings. Each hash-bearing object has
a versioned domain prefix, exactly one LF separator, and a closed preimage definition.
Digest equality never substitutes for canonical-byte comparison when collision protection is
required.

## Money

Money is exact decimal plus an explicit ISO-style currency code and registry/version binding.
Binary floating point is forbidden. Mixed currencies are segmented and never silently summed.
No FX conversion is inferred.

## Safe integers

JSON counters are nonnegative integers within the exact safe range required by their
contract. Counts and business quantities are distinct types.

## Observations versus decisions

Source adapters emit observations only. They must not emit business conclusions, credit
decisions, opportunities, interventions, or human outcomes.
