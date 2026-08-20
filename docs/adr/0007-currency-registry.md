# ADR 0007: Closed currency registry and exact Money representation

- Status: accepted for Milestone 1
- Scope: shared currency metadata and exact Money mechanics only

## Decision

Money binds four explicit values: a `Decimal` amount, uppercase currency code, registry version,
and registry scale. The initial immutable registry is
`synthetic-iso-style-currency-registry/v1` with this closed inventory:

| Code | Scale |
|---|---:|
| `EUR` | 2 |
| `JPY` | 0 |
| `KWD` | 3 |
| `USD` | 2 |

This is a deliberately small ISO-style registry projection, not an assertion that unlisted codes
are invalid currencies generally. An unlisted code is unavailable to this implementation version
until an explicitly reviewed registry revision adds it. There is no default code, inferred USD,
base currency, exchange rate, or FX operation.

The constructor accepts `Decimal` exactly; strings, integers, floats, non-finite values, negative
zero, and amounts with an exponent different from the registered scale fail. JSON uses a closed
object with the amount as a canonical fixed-scale string plus explicit code, registry version,
and scale. It rejects signs on positive values, exponent notation, commas, whitespace, leading
integer zeroes, missing or extra members, and excess or missing precision.

Arithmetic converts the already validated Decimal coefficient to integer minor units and uses
integer addition, subtraction, and Quantity multiplication. This avoids ambient Decimal-context
rounding. A result is reconstructed at the same exact scale. Arithmetic requires identical code,
registry version, and scale; mixed bindings fail instead of being summed or converted. Generic
Money permits signed values because corrections and reversals may require them, while each owning
business field remains responsible for its narrower sign policy.

## Consequences

The registry is intentionally incomplete but deterministic and executable offline. Adding a code,
changing a scale, or changing representation requires a new registry version and compatibility
tests. Aggregation must remain segmented by the complete currency binding. Business value
coherence, availability outcomes, reason emission, and persistence remain outside this primitive
and belong to their authorized milestone components.
