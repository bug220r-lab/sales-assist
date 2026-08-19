
> **Sanitized supporting reference.** This file is a mechanically sanitized derivative of
> source material supplied for the synthetic proof of concept. Historical status/freeze
> language is nonbinding. The curated files under `specs/` govern. No production-system
> access or real-data use is authorized by this reference.

# Synthetic Sales Assist — Sales Credit v0.1 — Milestone A Specification

**Status:** Frozen bootstrap specification for Offline Core  
**Rules version:** `sales-credit-v0.1`  
**Governing source:** *Synthetic Sales Assist — Sales Credit v0.1 — Save Point*  
**Source document ID:** `SYNTHETIC-SOURCE-ID`  
**Source revision:** See `SOURCE_MANIFEST.json`  
**Frozen:** 2026-08-08

## 1. Interpretation and authority

The terms **MUST**, **MUST NOT**, **REQUIRED**, **SHALL**, and **SHALL NOT** are mandatory. **SHOULD** is a strong recommendation that may be changed only with a recorded rationale and without weakening a mandatory rule.

Rules labeled **Source-frozen** directly preserve the governing save point. Rules labeled **Conservative Milestone A resolution** make an underspecified behavior deterministic for offline implementation while choosing the outcome least likely to create a false automatic credit decision. A conservative resolution must not be broadened without explicit approval and a rules-version/test update.

Extraction is factual. Interpretation is a separate rules-engine step. Raw source values MUST be preserved when a classification is derived from them.

## 2. Purpose and scope

### 2.1 Included — Source-frozen

Milestone A establishes an offline proof of the Sales Credit workflow:

- Synthetic Interaction Queue intake modeling and timestamp behavior.
- Versioned data models and validation.
- Fourteen-calendar-day review and recheck logic.
- Phone/email order-search planning and result deduplication.
- Sales-rep classification.
- Cancellation, replacement, product-continuity, and material-change rules.
- Evidence-needed queues and deterministic evidence classification from synthetic inputs.
- SQLite active-case state, closure minimization, 90-day retention, and purge behavior.
- Synthetic regression fixtures and fake Synthetic Order Portal HTML.
- A Manifest V3 Chrome reader skeleton that works only against fake pages and emits the `OrderSnapshot` contract.
- Read-only architecture and automated safety tests.

Primary success question: can the system complete Sales Credit Checks faster while maintaining or improving accuracy, consistency, and traceability?

### 2.2 Excluded — Source-frozen

Milestone A MUST NOT include:

- DOI Review.
- Automatic Synthetic Message Source follow-ups or any Synthetic Message Source mutation.
- Customer messaging.
- Credit-request submission.
- Any Synthetic Order Portal write operation.
- Live Synthetic Order Portal DOM reconnaissance, live page capture, live selectors, or a production OA adapter.
- OA credentials, cookies, session tokens, 2FA handling, or production connectivity.
- Synthetic Queue Store mutation or historical timestamp backfill execution.
- Live Synthetic Email Source/Synthetic Call Source evidence automation.
- Operational reliance or shadow-mode deployment.

## 3. Permanent Synthetic Order Portal safety invariant

### SAFE-001 — Source-frozen

Synthetic Order Portal is permanently 100% read-only for Synthetic Sales Assist. This is not a temporary v0.1 limitation and is not eligible for future relaxation.

### SAFE-002 — Source-frozen

The only permissible future live OA behaviors are search, navigation, opening an order, reading fields/notes/line items, and extracting approved factual information.

### SAFE-003 — Source-frozen

Order edits, sales-rep changes, notes, status changes, product changes, shipping changes, form submissions, write requests, and programmatic activation of any state-changing control are forbidden.

### SAFE-004 — Source-frozen

The architecture MUST omit OA write functions entirely. A dormant, feature-flagged, inaccessible, or unused write path still fails this rule.

### SAFE-005 — Source-frozen

Unknown page layouts or missing required data MUST fail closed. The system MUST NOT guess a selector, field value, order identity, attribution, value, or page type.

### SAFE-006 — Milestone A boundary

Milestone A MUST contain no production OA hostname, permission, selector, page sample, network request, authentication material, or live browser dependency. All OA-like inputs MUST be synthetic.

## 4. Common representation rules

### DATA-001 — Conservative Milestone A resolution

All persisted objects MUST have a stable internal identifier and `schema_version`. Identifiers are opaque and MUST NOT encode email, phone, customer name, or other customer identity.

### DATA-002 — Conservative Milestone A resolution

Timestamps MUST be RFC 3339 strings with an explicit UTC offset. A calculation that depends on calendar dates MUST receive an explicit IANA `business_timezone`; tests use `America/New_York`. The production business-timezone default remains a live-work-system confirmation and MUST NOT be silently inferred.

### DATA-003 — Conservative Milestone A resolution

Currency values MUST use decimal-safe representation, preferably fixed-scale decimal strings plus an explicit currency code. Binary floating point MUST NOT be used for business decisions or persisted totals.

### DATA-004 — Source-frozen

Raw Synthetic Order Portal values MUST be retained alongside derived classifications. Missing or unrecognized raw values MUST NOT be silently remapped.

### DATA-005 — Conservative Milestone A resolution

External JSON MUST reject duplicate keys, non-finite numbers, wrong types, and unknown enum values. Unknown non-security extension fields may be retained separately only if they cannot influence a decision. Malformed decision inputs MUST fail closed.

## 5. Data contracts

The examples under `fixtures/examples/` are synthetic and illustrative. Normative requirements are defined here.

### 5.1 `InteractionRecord`

#### Source-frozen source fields

- Interaction Date.
- Interaction Time.
- Email.
- Phone.
- VIN.
- Part / Request.
- Notes.

`Recorded At` is an immutable backend timestamp. `Interaction At` may be manually corrected when the row was entered later than the actual interaction. No Channel field is required.

#### Milestone A model

| Field | Requirement | Rule |
| --- | --- | --- |
| `schema_version` | REQUIRED | Model schema version. |
| `interaction_id` | REQUIRED | Opaque, non-identifying internal ID. |
| `source_ref` | REQUIRED | Synthetic Interaction Queue workbook/tab/row reference. |
| `interaction_date` | REQUIRED | Local calendar date as recorded. |
| `interaction_time` | REQUIRED for exact/corrected precision | Local time as recorded. |
| `interaction_at` | REQUIRED for automated timing decisions | Timezone-aware combined timestamp. |
| `recorded_at` | REQUIRED | Immutable timezone-aware backend timestamp. |
| `timestamp_precision` | REQUIRED | `EXACT`, `CORRECTED`, `REVISION_DERIVED`, or `HISTORICAL_APPROXIMATION`. |
| `email` | CONDITIONAL | At least one usable email or phone is required for automatic OA search planning. |
| `phone` | CONDITIONAL | At least one usable phone or email is required for automatic OA search planning. |
| `vin` | OPTIONAL | Working data only unless separately justified. |
| `part_request` | OPTIONAL | Intake context; not required for routine attribution. |
| `notes` | OPTIONAL | Active-case working data only. |

INT-001 — The sheet is the authoritative starting point; one row is one interaction. Repeat customers may have multiple independent rows and review windows.

INT-002 — Date/time SHOULD be stamped when the first usable phone or email is entered.

INT-003 — `recorded_at` MUST be immutable. A correction creates/updates `interaction_at`, sets precision to `CORRECTED`, and leaves the original recorded timestamp intact.

INT-004 — Downstream normalization MUST keep intake low-friction. The system MUST NOT rewrite the source into guessed contact data.

INT-005 — An interaction with no usable email or phone cannot be searched automatically and MUST route to `MANUAL_REVIEW_REQUIRED` with a structured reason.

### 5.2 `OrderSearchRun`

This active-case audit object records an intentional initial check or a permitted recheck.

| Field | Requirement | Rule |
| --- | --- | --- |
| `schema_version` | REQUIRED | Model schema version. |
| `search_run_id` | REQUIRED | Opaque run ID. |
| `case_id` | REQUIRED | Owning Sales Credit case. |
| `interaction_id` | REQUIRED | Exactly one source interaction. |
| `trigger_type` | REQUIRED | `MANUAL_INITIAL`, `AUTOMATIC_DAILY_RECHECK`, `FORCE_RECHECK`, or `MANUAL_REPLACEMENT_CHECK`. |
| `triggered_at` | REQUIRED | Timezone-aware timestamp. |
| `force_reason` | CONDITIONAL | Required only for `FORCE_RECHECK`. |
| `identifier_attempts` | REQUIRED | One entry per available identifier, including invalid attempts. |
| `combined_order_numbers` | REQUIRED | Exact Order Numbers after complete-set union/deduplication. |
| `search_completeness` | REQUIRED | `COMPLETE` or `INCOMPLETE`. |
| `run_outcome` | REQUIRED | `CANDIDATES_FOUND`, `NO_ORDER`, `INCOMPLETE`, or `BLOCKED`. |
| `completed_at` | CONDITIONAL | Required when the run finishes. |
| `reason_codes`, `warnings` | REQUIRED | Arrays; empty when none. |

Each `identifier_attempts` entry MUST contain `identifier_type` (`EMAIL` or `PHONE`), active-only normalized search value, and `attempt_status` (`COMPLETE`, `FAILED`, or `SKIPPED_INVALID`). A `COMPLETE` entry also records the exact Order Numbers returned. Normalized email/phone search values MUST be removed during closure.

SEARCH-001 — Intake may accumulate continuously, but OA browsing begins only when TARGET_REP intentionally runs a Sales Credit Check.

SEARCH-002 — A run MUST plan a search for every valid identifier available. Failure of one identifier search MUST NOT be represented as a complete combined result.

SEARCH-003 — Search-run details are active working data and MUST be minimized at closure to the check timestamps and concise audit facts allowed in `ClosedAuditRecord`.

### 5.3 `OrderSnapshot`

`OrderSnapshot` is the factual interface between the Chrome OA reader and the Python rules engine. The extractor MUST NOT assign Sales Credit outcomes.

#### Required extraction metadata — Source-frozen

- `schema_version`
- `snapshot_id`
- `order_number`
- `order_url`
- `captured_at`
- `parser_version`
- `extraction_status`

`extraction_status` is exactly `VALID`, `PARTIAL`, or `INVALID`.

#### Required transaction fields — Source-frozen

- `order_timestamp`
- `order_status_raw`
- `order_sales_rep_raw`
- `current_order_total`

Missing required metadata or transaction fields MUST produce `INVALID` and stop automated processing of that snapshot.

#### Optional transaction fields — Source-frozen

- `sold_ship_date`
- `current_expected_ship_date`
- `payment_status`
- `current_subtotal`
- `current_shipping`
- `current_tax`
- `current_total_due`

Missing optional transaction fields produce warnings but do not stop routine Sales Credit processing.

#### Milestone A extension fields — Conservative resolution

| Field | Requirement | Rule |
| --- | --- | --- |
| `currency` | CONDITIONAL | Required before interpreting any monetary value; do not silently assume currency. |
| `customer_identifiers` | OPTIONAL / CONDITIONAL | Active-only raw email/phone arrays; required only for a deterministic customer-continuity decision. |
| `line_items_complete` | REQUIRED when line items are supported | Boolean scan-completeness flag. |
| `line_items` | REQUIRED when line items are supported | Array of `LineItemSnapshot`; may be empty only when the page proves there are no lines. |
| `notes_scan_status` | REQUIRED | `COMPLETE`, `INCOMPLETE`, or `UNAVAILABLE`. |
| `notes` | OPTIONAL | Raw active-only note strings; never required to be retained after classification/closure. |
| `warnings` | REQUIRED | Array; empty when none. |

Missing/invalid `currency` blocks money-dependent decisions. Missing customer identifiers does not invalidate the source-frozen transaction core, but it blocks deterministic replacement customer continuity. These gaps produce `PARTIAL` when the dependent data was expected from a supported fake page.

#### Line items — Source-frozen

Each `LineItemSnapshot` SHOULD capture:

- ES#.
- Quantity.
- Line total.
- MFG/part number when available.
- Line-level sales rep when available.
- Description.
- Product ETA.

Incomplete line-item extraction MUST produce `PARTIAL` and block any workflow that requires product continuity. It does not automatically block a rule that depends only on complete required transaction fields.

#### `LineItemSnapshot` envelope — Conservative Milestone A resolution

| Field | Requirement | Rule |
| --- | --- | --- |
| `line_index` | REQUIRED | Stable zero- or one-based position documented by the schema. |
| `quantity` | REQUIRED when extracted | Strict numeric value; no guessed default. |
| `line_total` | REQUIRED when extracted | Decimal-safe monetary string. |
| `description` | REQUIRED when extracted | Factual synthetic/OA text. |
| `es_number` | OPTIONAL | Raw ES#; deterministic matching uses `ORDER-008`. |
| `mfg_part_number` | OPTIONAL | Raw MFG/part number; deterministic matching uses `ORDER-008`. |
| `line_sales_rep_raw` | OPTIONAL | Never copied from order-level data when absent. |
| `product_eta` | OPTIONAL | Date/text exactly as extracted. |
| `extraction_complete` | REQUIRED | Boolean stating whether all supported line fields/lines were scanned. |

At least one of `es_number` or `mfg_part_number` is CONDITIONAL for a deterministic product-continuity decision. Missing both does not invent a value and blocks that decision.

#### Notes — Source-frozen

`notes_scan_status` is `COMPLETE`, `INCOMPLETE`, or `UNAVAILABLE`. If notes are not fully scanned, the system MUST NOT claim that the order is free of commercial changes. Raw notes are temporary active-case working data and are never written to OA.

#### Status precedence — Conservative Milestone A resolution

1. Any missing/invalid required field or unsupported page structure => `INVALID`.
2. Otherwise, incomplete line-item extraction, `notes_scan_status != COMPLETE`, or another declared conditional extraction gap => `PARTIAL`.
3. Otherwise => `VALID`.

`INVALID` overrides `PARTIAL`; `PARTIAL` overrides `VALID`. Warnings for optional fields do not lower status by themselves.

### 5.4 `EvidenceEvent`

Evidence events MUST preserve the following typed contract:

| Field | Requirement | Rule |
| --- | --- | --- |
| `schema_version` | REQUIRED | Model schema version. |
| `evidence_event_id` | REQUIRED | Opaque, non-identifying ID. |
| `case_id`, `interaction_id` | REQUIRED | Owning case and exact interaction. |
| `source` | REQUIRED | `SNAPENGAGE_GMAIL`, `HELP_SCOUT_GMAIL`, or `Synthetic Call Source`. |
| `source_reference` | REQUIRED | Active locator; minimized at closure under §5.6. |
| `occurred_at` | REQUIRED for timing classification | Timezone-aware timestamp. |
| `timestamp_precision` | REQUIRED | Frozen precision vocabulary in §14. |
| `direction` | REQUIRED | `INBOUND`, `OUTBOUND`, `TWO_WAY`, or `UNKNOWN`. |
| `TARGET_REP_participated` | REQUIRED | Boolean or explicit unknown validation failure; never inferred from direction alone. |
| `two_way` | REQUIRED | Boolean. |
| `connected_call` | REQUIRED | Boolean. |
| `matched_identifier_type` | REQUIRED | `EMAIL` or `PHONE`. |
| `order_number` | REQUIRED | Exact related Order Number. |
| `relationship_to_order` | REQUIRED | `PRE_ORDER`, `POST_ORDER`, or `TIMING_UNCERTAIN`. |
| `classification` | REQUIRED | Evidence classification below. |
| `reason_code` | REQUIRED | Value from the versioned rules reason-code registry. |

Frozen/conservative evidence classification vocabulary and workflow mapping:

| Evidence classification | Workflow state | Meaning |
| --- | --- | --- |
| `VERIFIED_PREORDER_CONTACT` | `VERIFIED_PREORDER_EVIDENCE` | Two-way pre-order interaction or connected pre-order call with identity/timing proof. |
| `INBOUND_ONLY_PREORDER_CONTACT` | `INBOUND_EVIDENCE_HUMAN_REVIEW` | Inbound-only, no documented TARGET_REP response. |
| `OUTBOUND_ONLY_PREORDER_CONTACT` | `OUTBOUND_EVIDENCE_HUMAN_REVIEW` | Outbound-only, no two-way response. |
| `MISSED_OR_UNANSWERED_INBOUND_CALL` | `INBOUND_EVIDENCE_HUMAN_REVIEW` | Pre-order missed/unanswered inbound call. |
| `POST_ORDER_CONTACT_ONLY` | `MANUAL_REVIEW_REQUIRED` or continued `EVIDENCE_NEEDED` | Does not independently establish attribution; never automatic credit. |
| `TIMING_UNCERTAIN_HUMAN_REVIEW` | `MANUAL_REVIEW_REQUIRED` | Ordering cannot be established. |
| `INSUFFICIENT_IDENTITY_OR_TIMING` | `MANUAL_REVIEW_REQUIRED` or continued `EVIDENCE_NEEDED` | Identity/timing proof is incomplete; never automatic credit. |

`POST_ORDER_CONTACT_ONLY` and `INSUFFICIENT_IDENTITY_OR_TIMING` may remain `EVIDENCE_NEEDED` only while an explicit evidence-search queue is still active; once a decision is required, they route to `MANUAL_REVIEW_REQUIRED`. The transition and reason MUST be recorded.

The minimum reason-code registry includes `TWO_WAY_PREORDER_INTERACTION`, `CONNECTED_PREORDER_CALL`, `INBOUND_ONLY_PREORDER_CONTACT`, `OUTBOUND_ONLY_PREORDER_CONTACT`, `MISSED_INBOUND_CALL`, `POST_ORDER_ONLY`, `TIMING_UNCERTAIN`, `IDENTITY_NOT_ESTABLISHED`, `MISSING_REQUIRED_FIELD`, `UNRECOGNIZED_REP_TAG`, and `MULTIPLE_CANDIDATE_OUTCOMES`. New codes require a rules-version/test update.

Full message/call content or excerpts may exist only as active-case working data and MUST be removed at closure.

### 5.5 `SalesCreditCase`

The active aggregate MUST associate exactly one logged interaction with zero or more independently evaluated candidate orders. It MUST NOT merge distinct interactions merely because identifiers overlap.

| Field | Requirement | Rule |
| --- | --- | --- |
| `schema_version`, `case_id` | REQUIRED | Version and opaque case ID. |
| `interaction_id` | REQUIRED | Exactly one interaction. |
| `workflow_state` | REQUIRED | Frozen state in §12.1. |
| `candidate_decisions` | REQUIRED | Array; one entry per exact candidate Order Number. |
| `search_run_ids` | REQUIRED | Ordered run references. |
| `snapshot_ids`, `evidence_event_ids` | REQUIRED | Arrays; empty when none. |
| `last_automatic_check_date` | OPTIONAL | Local date in the explicit business timezone. |
| `replacement_window` | OPTIONAL | Trusted cancellation anchor and end date when applicable. |
| `reason_codes`, `warnings` | REQUIRED | Arrays; empty when none. |
| `rules_version` | REQUIRED | `sales-credit-v0.1` for this package. |
| `created_at`, `updated_at` | REQUIRED | Timezone-aware timestamps. |
| `final_outcome`, `closed_at` | CONDITIONAL | Required as applicable when closed. |

Each candidate decision MUST contain exact `order_number`, `snapshot_id`, extraction status, derived order-level workflow state/classification, applicable evidence IDs, reason codes, warnings, and whether evaluation is complete. All candidates MUST be evaluated before case aggregation.

CASE-001 — Conservative Milestone A resolution: if all completely evaluated candidates produce the same workflow state, the case MAY expose that state. If candidate states differ, or any candidate is incomplete/blocked, case-level state MUST be `MANUAL_REVIEW_REQUIRED` with reason `MULTIPLE_CANDIDATE_OUTCOMES` (or a more specific blocking reason). Per-candidate decisions remain intact; no favorable or unfavorable result is erased.

CASE-002 — No-order states apply only after every required identifier search is complete and the candidate list is empty.

### 5.6 `ClosedAuditRecord`

A closed record is one minimized decision row per `case_id` plus exact `order_number`; a no-order closure uses `order_number: null`. This preserves multi-order decisions without retaining full snapshots. It MUST contain only the minimum needed to understand the decision:

- Case ID.
- Synthetic Interaction Queue source reference.
- Order Number when applicable.
- Interaction and order timestamps.
- Raw Sales Rep Tag.
- Relevant reliably established Placed Order Total when applicable.
- Classification.
- Evidence source, minimized source reference, and evidence classification.
- Final human outcome.
- Check timestamps, including `closed_at`.
- Parser version.
- Rules version.
- Concise human notes.

A closed record MUST NOT contain customer email, phone, persistent hashed customer identity, full OrderSnapshot data, line items, raw OA notes, full communication content, evidence excerpts, VIN, unnecessary addresses, authentication/session material, or payment-card data.

An evidence source reference MAY be retained only as the smallest stable opaque locator needed to audit the decision, such as a synthetic/thread record ID. It MUST NOT embed a customer email/phone, message subject/body, transcript excerpt, URL query containing identity, or other communication content.

Required envelope: `schema_version`, opaque `audit_record_id`, `case_id`, `customer_followup_source_ref`, nullable `order_number`, `interaction_at`, nullable `order_timestamp`, nullable `order_sales_rep_raw`, nullable decimal-safe `placed_order_total` plus currency, frozen classification/workflow state, minimized evidence metadata, frozen/null final human outcome, check timestamps including `closed_at`, parser version, rules version, and concise human notes. Null is permitted only when the field is genuinely not applicable (for example, no-order closure), never to hide an extraction failure.

## 6. Intake time and review windows

TIME-001 — Source-frozen: Every interaction has its own window. The interaction date is included and the automated review horizon runs through 14 full calendar days after that date.

TIME-002 — Conservative Milestone A resolution: for interaction date `D`, the calendar window ends at the end of local date `D + 14` in the explicit business timezone. This is a calendar rule, not a 336-hour duration.

TIME-003 — Source-frozen: Only orders placed on or after the logged interaction can qualify.

TIME-004 — Conservative Milestone A resolution: when exact/corrected timestamps are available, require `order_timestamp >= interaction_at`. When same-day ordering cannot be proven because either timestamp is approximate, classify `TIMING_UNCERTAIN_HUMAN_REVIEW`; do not auto-qualify. An order on a later calendar date may continue through other rules if it lies within the calendar window.

TIME-005 — Source-frozen: the 14-day horizon is an operational review horizon tied to pay-period cadence; it is not a claim that older SyntheticCo credit requests are prohibited.

TIME-006 — Source-frozen: a no-order interaction may be automatically rechecked at most once per calendar day while the window remains active.

TIME-007 — Source-frozen: `Force Recheck` may override the daily throttle for a specific case. The override MUST be explicit and audited.

TIME-008 — After the window closes with no qualifying order, transition to `REVIEW_WINDOW_CLOSED_NO_ORDER`; do not continue automatic daily rechecks.

## 7. Customer-to-order matching

MATCH-001 — Source-frozen: email and phone are parallel OA search keys. Search every valid identifier and combine the complete native result sets.

MATCH-002 — Source-frozen: when both valid identifiers exist, both searches MUST run. Results are deduplicated by exact Order Number.

MATCH-003 — Source-frozen: every candidate order is evaluated independently. Finding one order MUST NOT stop evaluation of later candidates.

MATCH-004 — Source-frozen: a different displayed customer name does not invalidate a relationship established by phone and/or email.

MATCH-005 — Conservative Milestone A resolution: phone normalization removes formatting characters, accepts ten digits, and may remove exactly one leading US country-code digit `1` from an eleven-digit value. Any other result is invalid and MUST NOT be guessed or padded.

MATCH-006 — Source-frozen: email comparison trims outer whitespace and compares case-insensitively. The system MUST NOT guess corrections or alternate addresses.

MATCH-007 — Conservative Milestone A resolution: an email is usable only if it has exactly one `@`, nonempty local/domain portions, and no whitespace. This is an intake/search safety check, not a guarantee that the mailbox exists.

MATCH-008 — A partial identifier-search failure makes the combined search incomplete. The system MUST preserve any candidates found but MUST NOT claim that all matching orders were reviewed.

## 8. Sales-rep classification

**Conservative Milestone A resolution:** comparison may trim outer whitespace, but otherwise MUST use the exact case-sensitive raw tag. `order_sales_rep_raw` MUST remain unchanged in the audit data. Case variants and fuzzy variants are unrecognized because the governing source freezes only the lowercase values shown below.

| Normalized value | Classification/state | Required behavior |
| --- | --- | --- |
| `target_rep` | `CREDIT_CONFIRMED_TARGET_REP` | Credit Confirmed — TARGET_REP; no further attribution investigation. |
| `target_rep_web` | `CREDIT_CONFIRMED_TARGET_REP` | Credit Confirmed — TARGET_REP; no further attribution investigation. |
| `unassigned_web` | `EVIDENCE_NEEDED` | Evaluate pre-order contact evidence; never auto-confirm solely from tag. |
| Configured known other-rep tag | `OTHER_REP_HUMAN_REVIEW` | Evaluate evidence and route to Other Rep — Human Review. |
| Missing or unrecognized | `MANUAL_REVIEW_REQUIRED` | Preserve raw value; no silent remapping. |

REP-001 — Only the two explicit TARGET_REP values above are automatic TARGET_REP confirmations.

REP-002 — The list of actual other-rep raw tags remains unverified. Milestone A tests MAY inject a synthetic configured allowlist; values not on it remain unrecognized/manual review.

REP-003 — A rep-tag classification does not override an `INVALID` snapshot, uncertain timing, a material change, or another blocking rule.

## 9. Order state, cancellation, and replacement

ORDER-001 — Source-frozen: capture every matching order before classifying order state.

ORDER-002 — Source-frozen: cancelled orders remain in the audit trail but do not represent active Sales Credit value.

ORDER-003 — Source-frozen: a cancelled qualifying order opens a replacement-search window through 14 full calendar days after the cancellation date. It may extend beyond the original interaction window.

ORDER-004 — A missing or unreliable cancellation date prevents automatic replacement-window calculation and routes to human review.

ORDER-005 — Source-frozen: a replacement requires both customer continuity and product continuity with the cancelled order.

ORDER-006 — Conservative Milestone A resolution: deterministic customer continuity requires overlap of at least one valid normalized email or phone identifier. A differing displayed name does not negate that overlap. No overlap or incomplete identifier evidence routes to human review rather than a guessed match.

ORDER-007 — Source-frozen: exact ES# or exact normalized MFG# establishes deterministic product continuity. Similar/equivalent products require human review.

ORDER-008 — Conservative Milestone A resolution: ES# comparison trims outer whitespace and otherwise requires exact case-sensitive equality; it performs no fuzzy match. MFG# comparison performs Unicode NFKC, trims outer whitespace, and uppercases; it preserves internal punctuation and spacing. Variants requiring punctuation deletion, spacing collapse, substitution, vendor equivalence, or semantic similarity are not deterministic matches.

ORDER-009 — Source-frozen: one matching ES#/MFG# is enough to make the replacement order relevant for review, but it does not decide whether credit applies to one line, related lines, or the whole order. That scope is a sales-manager decision.

ORDER-010 — A deterministic replacement candidate transitions to `POSSIBLE_REPLACEMENT_HUMAN_REVIEW`, not automatic credit.

ORDER-011 — Source-frozen: a replacement without relevant product continuity is not a continuation of the cancelled opportunity.

ORDER-012 — The exact raw OA value(s) for Cancelled and special treatment of other statuses remain live-verification items. Milestone A uses explicit synthetic status mappings and routes unrecognized potentially material states to human review.

ORDER-013 — Conservative Milestone A resolution: the source does not authorize automatic daily replacement-window rechecks. While `CANCELLED_REPLACEMENT_WINDOW_ACTIVE`, a new search requires an explicit manual Sales Credit Check. Future automatic replacement scheduling remains a specification decision; it MUST NOT be inferred from the original no-order daily recheck rule.

## 10. Original order value and material changes

VALUE-001 — Source-frozen: Sales Credit uses the value when the order was originally placed, not a later modified current total.

VALUE-002 — Source-frozen material changes include:

- Products added or removed.
- Quantity changes.
- Substitutions.
- Partial cancellations.
- Shipping-charge changes.
- Discounts or price adjustments.
- Refunds.
- Returns that alter commercial value.

VALUE-003 — Source-frozen: routine warehouse, inventory, shipment-tracking, and administrative events are not material merely because the lifecycle changed.

VALUE-004 — Source-frozen: detected material change => `ORDER_CHANGED_HUMAN_REVIEW`.

VALUE-005 — Source-frozen: notes may be read to detect/reconstruct changes. If `notes_scan_status` is not `COMPLETE`, the system MUST NOT claim the order is free of commercial changes.

VALUE-006 — Source-frozen: if Placed Order Total cannot be established reliably, require human verification rather than estimate.

VALUE-007 — Conservative Milestone A resolution: `current_order_total` MUST NOT automatically substitute for `placed_order_total`. A reliable placed value needs explicit evidence or a separately tested rule proving equivalence; that proof is not frozen in the governing source.

## 11. Contact evidence

EVID-001 — Source-frozen: routine evidence needs identity plus timing proof; product-level continuity between the interaction and purchase is not required.

EVID-002 — Verified two-way pre-order interaction or connected pre-order Synthetic Call Source call => `VERIFIED_PREORDER_EVIDENCE` / Verified Pre-Order Contact.

EVID-003 — Inbound-only pre-order contact with no documented TARGET_REP response before purchase => `INBOUND_EVIDENCE_HUMAN_REVIEW`.

EVID-004 — Outbound-only pre-order communication with no two-way response before purchase => `OUTBOUND_EVIDENCE_HUMAN_REVIEW`; preserve it as evidence.

EVID-005 — Missed/unanswered inbound call before purchase => evidence exists, but human review is required.

EVID-006 — Post-order contact does not independently establish attribution and MUST NOT produce an automatic confirmed-credit classification.

EVID-007 — If same-day timing cannot establish contact before order, use decision classification `TIMING_UNCERTAIN_HUMAN_REVIEW` and workflow state `MANUAL_REVIEW_REQUIRED`.

EVID-008 — Evidence automation is modular. Milestone A may stop at `EVIDENCE_NEEDED` while testing the classifier from synthetic events.

EVID-009 — Synthetic Email Source evidence should be checked before Synthetic Call Source in a later authorized evidence milestone. The v0.1 local Python application MUST NOT embed Synthetic Email Source credentials.

## 12. Workflow states and human outcomes

### 12.1 Frozen workflow-state vocabulary

- `AWAITING_OA_REVIEW`
- `CHECKED_NO_ORDER_WINDOW_ACTIVE`
- `REVIEW_WINDOW_CLOSED_NO_ORDER`
- `CREDIT_CONFIRMED_TARGET_REP`
- `EVIDENCE_NEEDED`
- `VERIFIED_PREORDER_EVIDENCE`
- `OUTBOUND_EVIDENCE_HUMAN_REVIEW`
- `INBOUND_EVIDENCE_HUMAN_REVIEW`
- `OTHER_REP_HUMAN_REVIEW`
- `ORDER_CHANGED_HUMAN_REVIEW`
- `CANCELLED_REPLACEMENT_WINDOW_ACTIVE`
- `POSSIBLE_REPLACEMENT_HUMAN_REVIEW`
- `CANCELLED_NO_REPLACEMENT`
- `MANUAL_REVIEW_REQUIRED`
- `CLOSED`

Unknown states MUST be rejected. `CLOSED` is terminal except for retention purge; reopening requires an explicit future rule and is not part of v0.1.

### 12.2 Minimum transition rules

- New processable interaction => `AWAITING_OA_REVIEW`.
- Complete run with no order while window active => `CHECKED_NO_ORDER_WINDOW_ACTIVE`.
- No order after window end => `REVIEW_WINDOW_CLOSED_NO_ORDER`.
- Cancelled qualifying order with active replacement window => `CANCELLED_REPLACEMENT_WINDOW_ACTIVE`.
- Replacement window closes without qualifying replacement => `CANCELLED_NO_REPLACEMENT`.
- Any ambiguity that lacks a more specific frozen human-review state => `MANUAL_REVIEW_REQUIRED`.
- Closure is explicit and MUST record a final human outcome where the case was brought to the sales manager.

### 12.3 Manager outcomes

Conservative schema canonicalization of the source labels:

- Approved => `APPROVED`
- Denied => `DENIED`
- Partial => `PARTIAL`
- Other Rep => `OTHER_REP`
- Not Pursued => `NOT_PURSUED`

The system records these human outcomes; it MUST NOT pretend to automate the manager decision.

## 13. Data minimization, closure, and retention

PRIV-001 — Source-frozen: the local application is a workflow-state and audit system, not a second OA copy or permanent customer database.

PRIV-002 — Source-frozen: full email, phone, snapshots, line items, notes, and evidence excerpts may exist temporarily while a case is active.

PRIV-003 — Source-frozen: after closure, email and phone are removed. v0.1 MUST NOT retain persistent hashed customer identities.

PRIV-004 — Source-frozen: full Synthetic Chat Source, Synthetic Message Source, Synthetic Email Source, or Synthetic Call Source content is not retained after closure; structured metadata and references are sufficient.

PRIV-005 — Source-frozen: minimized closed audit records are retained for 90 days, then purged.

PRIV-006 — Conservative Milestone A resolution: purge eligibility begins when `now >= closed_at + 90 days`. Tests MUST freeze time and avoid DST ambiguity. Purge MUST be idempotent and transactional.

PRIV-007 — Closure MUST atomically write the minimized closed record and remove disallowed active-case persistent data, or roll back without reporting closure.

PRIV-008 — Purge MUST remove eligible closed rows and dependent audit/index rows that could reconstruct the purged record. Documentation MUST address SQLite WAL/journal files and backups so retention is not silently defeated.

PRIV-009 — Source-frozen prohibited collection: passwords, cookies, session tokens, 2FA codes, payment-card data, unnecessary addresses, and unrelated customer information.

PRIV-010 — Logs and exceptions MUST redact or omit active-case PII and all prohibited data.

## 14. Historical timestamp precision

TS-001 — Frozen precision values are `EXACT`, `CORRECTED`, `REVISION_DERIVED`, and `HISTORICAL_APPROXIMATION`.

TS-002 — Revision time MUST NOT be presented as exact customer interaction time unless corroborated by a communication source.

TS-003 — Synthetic Email Source/Synthetic Chat Source/Synthetic Message Source or Synthetic Call Source evidence may upgrade a revision-derived timestamp to exact when it actually proves the interaction time.

TS-004 — Existing exact values MUST never be overwritten by lower-confidence backfill.

TS-005 — Milestone A may implement and test a pure timestamp-resolution function, but MUST NOT read Drive revisions or mutate Synthetic Interaction Queue.

## 15. Fake OA and extension contract

FAKE-001 — Provide synthetic fake pages for at least: normal order, `unassigned_web`, cancelled order, materially changed order, multi-item order, incomplete line items, incomplete/unavailable notes, missing required field, and unknown page layout.

FAKE-002 — Fake fixtures MUST contain no real customer information, live OA HTML, production selector, OA hostname, credential, cookie, or session token.

FAKE-003 — The Manifest V3 skeleton MUST have no production OA host permission and no capability to mutate OA-like pages.

FAKE-004 — The fake reader emits factual `OrderSnapshot` JSON only. The Python core owns validation and interpretation.

FAKE-005 — Recon Mode, if scaffolded, may produce a local, synthetic, read-only page-shape inventory. It MUST NOT infer or ship production selectors and MUST NOT activate page controls.

## 16. Production-readiness standards applied to Milestone A

TEST-001 — Required-field extraction is 100% on supported fake page shapes.

TEST-002 — Known deterministic classifications are 100% against the approved synthetic regression suite.

TEST-003 — False automatic confirmed-credit decisions are zero.

TEST-004 — Ambiguous cases always route to human review.

TEST-005 — Unrecognized page structure fails closed.

TEST-006 — OA writes are zero by architecture and automated safety test.

TEST-007 — Intentionally stored authentication/session data are zero.

TEST-008 — The safety suite explicitly proves there is no OA mutation path, write request, or synthetic activation of a write control.

These gates prove only the offline core. They do not prove live OA compatibility or authorize live use.

## 17. Deferred verifications and non-claims

The following remain outside Milestone A and MUST be reported as unresolved rather than guessed:

- Live search-results and order-detail DOM mapping.
- Managed Chrome extension policy.
- Native Messaging permission or alternate approved local transport.
- Exact production OA selectors and raw status/tag variants.
- Real cancellation/material-change Notes wording.
- Special order statuses beyond Cancelled.
- Systemwide production business timezone.
- Broad historical timestamp backfill validation and Synthetic Interaction Queue layout decision.
- First 50–100 real historical regression cases and shadow-mode comparison.

No Milestone A result may be presented as proof that live OA extraction works, a specific credit request should be submitted, or operational reliance is safe.
