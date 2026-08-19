
# Approved Product Decisions

These semantic decisions are binding for the synthetic implementation.

## R01

```text
R01_QUANTITY_POLICY =
INTEGER_ONLY_ALL_FOUR_FIELDS_MAX_9_DIGITS

R01_FINDING_PRESENCE_POLICY =
DIRECT_FOUR_MEMBER_V2

R01_IDENTIFIER_TRIM_POLICY =
ASCII_FOUR

R01_ES_NORMALIZATION_POLICY =
ES_NUMERIC_CORE

R01_MFG_OE_NORMALIZATION_POLICY =
MFG_SEPARATOR_PRESERVING_UPPER
```

## R02

```text
R02_FAILED_SOURCE_ATTEMPT_FINALIZATION =
EXPLICIT_ACCEPTED_NO_RETRY_FINALIZATION
```

There is no timeout, background finalizer, retry-window expiry, or automatic run failure after a
failed source attempt.

## Audit-authorized implementation clarifications

- Terminal disposition subjects are a subset of work items; systemic pre-read failure work is not
  forced into an order-disposition class.
- Extraction reservation and systemic terminalization share one serializable run-control boundary.
- RC-084 retains one code identity and has both evaluation-level and pre-extraction run-level legal
  emission sites.
