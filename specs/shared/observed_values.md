
# Observed Tagged Values

## Core union

Each observed field uses exactly one branch:

- `KNOWN`
- `UNKNOWN`
- `NOT_APPLICABLE`

The branch, value, reason, raw hint, and null/omission partition are closed and
field-specific.

## Rules

- `KNOWN` contains a valid canonical value and no UNKNOWN reason.
- `UNKNOWN` means the source value was successfully observed but could not be safely
  normalized. It contains the exact field-specific reason and no guessed value.
- `NOT_APPLICABLE` means the field is structurally inapplicable; it is not missing data.
- Missing, unreadable, inaccessible, or unobserved required data is extraction failure, not
  UNKNOWN.
- Raw hints are allowlisted, bounded, non-sensitive, and never arbitrary customer text.
- Unknown in one field blocks only conclusions whose complete basis depends on that field.
  Independent known conclusions remain available.

## Finding presence

Use direct `FindingPresenceV2`:

- `PRESENT`
- `NOT_PRESENT`
- `UNKNOWN`
- `NOT_APPLICABLE`

`ABSENT`, an outer presence wrapper, and dual encoding are forbidden.

## Required implementation closure

Every specialization must have accepted, null/inapplicable, conflict, missing/extra,
wrong-version, privacy, and boundary tests. DEDUPE PRESENT may not succeed when its required
observed timestamp is unnormalizable.
