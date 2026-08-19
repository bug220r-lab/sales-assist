
# Sales Credit Data Contracts

## InteractionRecord

Required logical fields:

- synthetic interaction ID;
- source reference;
- recorded-at timestamp and precision;
- optional corrected interaction-at timestamp and precision;
- active-only fictional email/phone values and normalized forms;
- optional VIN-like synthetic reference, part request, and active notes;
- review-window dates;
- workflow state;
- last check / next eligible check;
- schema version and provenance.

At least one usable email or phone is required for automated discovery. A record without either
remains valid history but routes to cleanup/manual review.

## OrderSearchRun

Records the intentional review invocation, trigger type, included interactions, attempted
identifiers, completeness, combined deduplicated Order Numbers, adapter version, warnings, and
terminal outcome.

Trigger types include normal review, automatic daily recheck, force recheck, and replacement
check.

## OrderSnapshot

Contains factual extraction metadata, synthetic Order Number, captured timestamp, parser
version, extraction status, placed-order time, status, raw order-level rep, current monetary
facts, customer-continuity identifiers where required, line items, and notes-scan status.

Missing required data yields INVALID. Incomplete line or notes data yields PARTIAL and blocks
only dependent decisions.

## LineItemSnapshot

Contains a stable synthetic line key, raw/canonical ES and MFG/OE identifiers, description,
integer quantity, exact line value, raw line rep, availability/ETA facts, and extraction warnings.

## EvidenceEvent

Contains source type, relocatable synthetic reference, occurred-at timestamp, direction,
target-rep participation, connected/two-way status, matched identifier type, timing relation,
classification, and temporary active-only excerpt.

## SalesCreditCase

Contains one synthetic Order Number, attached interactions/snapshots/evidence, attribution,
order-value status, exact placed value when proved, workflow state, replacement parent,
human outcome, timestamps, and concise human notes.

## ManagerOutcome

Contains outcome, decision time, actor, exact approved amount when applicable, optional
controlled reason, concise note, and record time.

## ClosedAuditRecord

The only long-lived case representation after closure. It retains minimum workflow and
classification evidence while removing contact values, full snapshots, line items, and message
content.
