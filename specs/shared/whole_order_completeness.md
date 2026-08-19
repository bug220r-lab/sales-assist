
# Whole-Order Completeness

A DOI snapshot may be created only when the extractor proves the complete relevant line
universe for one synthetic order.

## Proof requirements

The proof binds:

- requested synthetic Order Number;
- observed order identity;
- extractor and fixture versions;
- source-observed timestamp;
- required sections;
- declared and observed relevant-line counts;
- ordered line-manifest entries;
- duplicate/reordering rules;
- source references;
- coherence/change-detection state;
- manifest hash and proof hash.

## Failure behavior

No snapshot or evaluation is created when:

- order identity is missing or mismatched;
- a required section is unreadable;
- declared and observed line counts disagree;
- a relevant line is missing or duplicated;
- a hidden/paginated/collapsed region is not proved exhausted;
- the source changes during extraction;
- a required source timestamp is unnormalizable or disagrees with the order-level source time;
- the fixture or extractor version is unsupported.

A zero-relevant-line order is accepted only when the portal explicitly proves that the complete
relevant universe is empty.
