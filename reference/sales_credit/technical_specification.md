
> **Sanitized supporting reference.** This file is a mechanically sanitized derivative of
> source material supplied for the synthetic proof of concept. Historical status/freeze
> language is nonbinding. The curated files under `specs/` govern. No production-system
> access or real-data use is authorized by this reference.

Synthetic Sales Assist — Sales Credit Technical Specification v0.1
Frozen implementation contract for the personal Sales Credit proof of concept
Permanent safety invariant. Synthetic Order Portal is 100% read-only for the lifetime of Synthetic Sales Assist. The application may search, navigate, read, and extract approved facts. It must never create, modify, submit, or delete Synthetic Order Portal data. This rule is architectural, testable, and not eligible for later relaxation.
1. Document Status and Normative Language
This document is the governing v0.1 contract for Codex implementation. “Must” and “must not” are release-blocking requirements. “Should” describes the preferred implementation unless a documented constraint requires another approach. “May” describes optional behavior that cannot weaken a must-level requirement.
The frozen implementation scope is the offline core, Synthetic Interaction Queue intake and timestamp handling, local workflow storage, deterministic Sales Credit rules, test fixtures, and a read-only Chrome extension skeleton. Live Synthetic Order Portal selectors and production navigation remain intentionally deferred until supervised reconnaissance supplies the real page structure.
2. Purpose, Scope, and Success Criteria
Synthetic Sales Assist v0.1 is a personal productivity system for TARGET_REP’s Sales Credit workflow. It begins with manually logged Synthetic Interaction Queue interactions, discovers matching orders through read-only Synthetic Order Portal access, applies deterministic rules, preserves evidence and uncertainty, and records manager outcomes.
2.1 Included
* Synthetic Interaction Queue intake and immutable Recorded At handling.
* Historical timestamp migration with explicit precision and provenance.
* Email and phone normalization and parallel Synthetic Order Portal search.
* Fourteen-day review windows and daily recheck throttling.
* OrderSnapshot extraction contracts and fail-closed validation.
* Sales-rep, cancellation, replacement, material-change, and evidence classifications.
* One case per Order Number with multiple qualifying interactions attached.
* SQLite workflow state, manager outcome tracking, minimized closure records, and 90-day purge.
* Historical regression tests, synthetic fixtures, fake Synthetic Order Portal pages, and shadow-mode comparison.
2.2 Excluded from v0.1
* DOI Review and automatic Synthetic Message Source follow-up workflows.
* Customer messaging, credit-request submission, or manager decision automation.
* Any Synthetic Order Portal mutation, form submission, note entry, sales-rep change, product change, status change, or shipping change.
* Persistent Synthetic Email Source credentials in the local application.
* Production Synthetic Order Portal selectors or navigation assumptions before reconnaissance.
Primary success question: can the system complete Sales Credit checks faster while maintaining or improving accuracy, consistency, privacy, and traceability?
3. Permanent Synthetic Order Portal Safety Invariant
3.1 Allowed behavior
* Open the known Synthetic Order Portal origin, execute approved searches, navigate to results, open orders, read fields, read notes, inspect line items, and emit factual snapshots.
* Use only read-oriented browser actions and network requests required to obtain approved data.
* Display workflow output outside the Synthetic Order Portal document, such as an extension popup, side panel, or local application.
3.2 Forbidden behavior
* POST, PUT, PATCH, DELETE, or semantically equivalent mutation requests to Synthetic Order Portal.
* Programmatic clicks on Save, Submit, Add, Remove, Change, Update, Cancel, or any other write-capable control.
* Order edits, sales-rep changes, Notes entry, status changes, product or quantity changes, shipping changes, price changes, refunds, returns, or form submission.
* DOM mutation intended to alter Synthetic Order Portal state or simulate a user write.
* Collection or storage of passwords, cookies, session tokens, 2FA codes, payment-card data, or unrelated customer data.
3.3 Architectural enforcement
* The extension must not contain Synthetic Order Portal write functions. Safety is established by absence of capability, not by a runtime “read-only mode” switch.
* The production adapter interface exposes search, navigation, and extraction only. It exposes no generic request method and no arbitrary click helper.
* Unknown page layouts, missing required fields, partial notes scans, or selector ambiguity fail closed and stop automated classification.
* Tests must replace browser/network primitives with spies and fail if any non-read request or write-capable control activation occurs.
* Future scope changes cannot waive this invariant; a separate product would be required for any write-capable workflow.
4. System Boundaries and Architecture
Synthetic Interaction Queue (facts)
       ↓
Intake + normalization
       ↓
Local workflow database (active cases)
       ↓ intentional run
Read-only Chrome Synthetic Order Portal adapter
       ↓ OrderSnapshot facts
Deterministic Sales Credit rules engine
       ↓
Human-review queues / manager outcome
       ↓ closure transaction
Minimized audit record → purge after 90 days
Observed facts and derived decisions must remain separate. Synthetic Interaction Queue and the Synthetic Order Portal extractor produce factual records. The Python rules engine produces classifications and workflow states. Extractors must never emit conclusions such as “TARGET_REP deserves credit” or “unassigned_web should be reassigned.”
4.1 Technology choices
* Python backend with typed domain models and a deterministic rules package.
* SQLite for local workflow state and minimized audit retention.
* Chrome Manifest V3 extension with content extraction and no mutation capability.
* Fake Synthetic Order Portal HTML fixtures for development before live selectors exist.
* Chrome-to-Python transport through Native Messaging if workstation policy permits; otherwise an approved local transport that preserves the same message contracts.
4.2 Adapter boundary
class OrderAdminAdapter(Protocol):
   def search(self, identifiers: list[SearchIdentifier]) -> OrderSearchResult: ...
   def extract_order_snapshot(self, document: ReadOnlyDocument) -> OrderSnapshot: ...

# No write(), submit(), click_control(), update_order(), or generic request method.
5. Time Model and Precision
All stored timestamps are timezone-aware. Business windows are evaluated in America/New_York calendar time. Raw source timestamps may also retain their original timezone and offset for auditability.
Concept
	Definition
	Constraint
	Recorded At
	When a Synthetic Interaction Queue row was first created or first observed by the system.
	Immutable after first trusted assignment. Revision history may provide an approximate upper bound.
	Interaction At
	When the customer interaction actually occurred.
	May be exact, manually corrected, or unknown. Revision time alone never establishes it.
	Recorded At window start
	Time of the immediately prior sampled revision in which the row was absent.
	Provides the lower bound of the insertion interval; it is not the interaction time.
	Review window
	Interaction local date through fourteen full calendar days after that date, inclusive.
	Only orders on or after the interaction can qualify.
	Replacement window
	Cancellation local date through fourteen full calendar days after that date, inclusive.
	May extend beyond the original interaction window.
	

5.1 Timestamp precision enums
Value
	Meaning
	EXACT
	Direct timestamp from an exact communication or system event, such as a Synthetic Chat Source transcript.
	CORRECTED
	Human-corrected Interaction At value with correction provenance.
	REVISION_DERIVED
	Recorded At approximation equal to the first sampled revision where the row is present.
	HISTORICAL_APPROXIMATION
	The source supports only a coarse historical statement, or the row cannot be isolated safely. An exact timestamp must not be written.
	

Same-day cases with no reliable time ordering between interaction and order are classified Timing Uncertain — Human Review. Date-only evidence must never be silently treated as pre-order proof.
6. Data Model
Identifiers use UUIDs unless a source supplies a stable native identifier. Monetary values use decimal types, never binary floating point. Every schema carries schema_version. Optional raw strings are preserved when needed for audit and normalized values are stored separately.
6.1 InteractionRecord
Field
	Type / Nullability
	Rule
	interaction_id
	UUID, required
	Internal primary key.
	schema_version
	string, required
	Versioned contract.
	source_spreadsheet_id
	string, required
	Synthetic Interaction Queue workbook reference.
	source_sheet
	string, required
	Exact visible weekly tab name.
	source_row
	integer, required
	Original one-based row number.
	recorded_at
	timezone-aware timestamp, nullable during migration
	Immutable once established.
	recorded_at_window_start
	timezone-aware timestamp, nullable
	Prior sampled revision boundary.
	recorded_at_precision
	TimestampPrecision, required
	Never claim EXACT from revision history.
	interaction_at
	timezone-aware timestamp, nullable
	Exact or corrected interaction time when known.
	interaction_at_precision
	TimestampPrecision, nullable
	EXACT or CORRECTED when interaction_at is populated.
	email_raw / email_normalized
	string, nullable
	Trim and compare case-insensitively; never guess corrections.
	phone_raw / phone_normalized
	string, nullable
	Normalize valid North American input to ten digits for Synthetic Order Portal search.
	vin
	string, nullable
	Reference only; not an Synthetic Order Portal search key in v0.1.
	part_request
	string, nullable
	Temporary active-case context.
	notes
	string, nullable
	Temporary active-case context; minimized at closure.
	processing_state
	WorkflowState, required
	Current workflow state.
	review_window_start / end
	local dates, required when interaction date known
	Derived once from Interaction At or approved historical date basis.
	last_oa_check_at / next_check_eligible_at
	timestamps, nullable
	Daily throttle metadata.
	

At least one usable normalized email or phone is required for automated Synthetic Order Portal processing. A row without either identifier remains valid Synthetic Interaction Queue history but is routed to cleanup or manual review.
6.2 OrderSearchRun
Field
	Type
	Rule
	search_run_id
	UUID
	Primary key.
	interaction_ids
	list[UUID]
	Interactions included in the run.
	triggered_at
	timestamp
	Run start time.
	trigger_type
	NORMAL or FORCE_RECHECK
	Force Recheck bypasses the calendar-day throttle for selected cases only.
	searched_identifiers
	list[SearchIdentifier]
	Every valid email and phone available.
	result_sets_complete
	boolean
	False blocks claims that all matching orders were reviewed.
	candidate_order_numbers
	list[string]
	Combined and deduplicated by Order Number.
	adapter_version
	string
	Synthetic Order Portal adapter build.
	warnings
	list[string]
	Partial or recoverable issues.
	

6.3 OrderSnapshot
Field
	Requirement
	Rule
	schema_version, snapshot_id
	Required
	Snapshot identity and contract version.
	order_number, order_url
	Required
	Stable order reference and read-only source URL.
	captured_at, parser_version
	Required
	Extraction provenance.
	extraction_status
	Required
	VALID, PARTIAL, or INVALID.
	order_timestamp
	Required
	Timezone-aware placed-order time.
	order_status_raw
	Required
	Unmodified Synthetic Order Portal value.
	order_sales_rep_raw
	Required
	Unmodified order-level sales-rep value.
	current_order_total
	Required
	Current observed total; not automatically the placed total.
	sold_ship_date, expected_ship_date
	Optional
	Warnings only when absent.
	payment_status
	Optional
	Raw value.
	current_subtotal, shipping, tax, total_due
	Optional
	Decimal values when present.
	customer_identifiers
	Conditional
	Only approved identifiers needed for match verification.
	line_items
	Conditional
	Required for replacement/product-continuity workflows.
	notes_scan_status
	Required
	COMPLETE, INCOMPLETE, or UNAVAILABLE.
	notes_events
	Temporary / conditional
	Structured observations derived from read-only notes scanning.
	

A missing required field yields INVALID — Automated Processing Stopped. Incomplete line items or incomplete notes yield PARTIAL and block only the decisions that depend on the missing facts. The rules engine never fills absent facts by inference.
6.4 LineItemSnapshot
Field
	Type
	Rule
	line_id
	string or derived stable key
	Unique within the order snapshot.
	es_number_raw / normalized
	string, nullable
	Exact normalized ES# supports deterministic product continuity.
	manufacturer_part_number_raw / normalized
	string, nullable
	Exact normalized MFG# supports deterministic product continuity.
	description
	string, nullable
	Observed description only.
	quantity
	decimal or integer, nullable
	Preserve source precision.
	line_total
	decimal, nullable
	Observed line value.
	line_sales_rep_raw
	string, nullable
	Preserve when Synthetic Order Portal exposes it.
	product_eta
	string or timestamp, nullable
	Observed value.
	extraction_warnings
	list[string]
	Missing or ambiguous line facts.
	

6.5 EvidenceEvent
Field
	Type
	Rule
	evidence_event_id
	UUID
	Primary key.
	source_type
	enum
	Synthetic Email Source, Synthetic Chat Source, HELP_SCOUT, Synthetic Call Source, CUSTOMER_FOLLOWUP, or MANUAL.
	source_reference
	string
	Reference sufficient to relocate evidence; no full content after closure.
	occurred_at
	timestamp, nullable
	Exact when the source proves it.
	direction
	enum
	INBOUND, OUTBOUND, TWO_WAY, or UNKNOWN.
	TARGET_REP_participated
	boolean or unknown
	Explicit evidence property.
	connected_or_two_way
	boolean or unknown
	Required for deterministic verified pre-order contact.
	matched_identifier_type
	EMAIL, PHONE, or OTHER
	How identity was matched.
	timing_relation
	PRE_ORDER, POST_ORDER, SAME_DAY_UNCERTAIN, or UNKNOWN
	Never infer PRE_ORDER from date-only ambiguity.
	classification
	EvidenceClassification
	Derived by the rules engine.
	temporary_excerpt
	string, nullable
	Deleted at closure.
	

6.6 SalesCreditCase
Field
	Type
	Rule
	case_id
	UUID
	Primary key.
	order_number
	string
	Uniqueness key for an active logical case.
	interaction_ids
	list[UUID]
	All qualifying Synthetic Interaction Queue interactions attached as history.
	snapshot_ids
	list[UUID]
	Observed order versions.
	attribution_classification
	enum
	TARGET_REP confirmed, evidence needed, other rep review, or unknown.
	order_value_status
	enum
	PLACED_VALUE_VERIFIED, CURRENT_ONLY, CHANGED_REVIEW, or UNKNOWN.
	placed_order_total
	decimal, nullable
	Must be reconstructed or human-verified; never estimated.
	workflow_state
	WorkflowState
	Operational state.
	evidence_event_ids
	list[UUID]
	Relevant evidence.
	replacement_parent_case_id
	UUID, nullable
	Links cancelled order to replacement review.
	manager_outcome_id
	UUID, nullable
	Human result.
	created_at / updated_at / closed_at
	timestamps
	Lifecycle metadata.
	human_notes
	string, nullable
	Concise operational notes only.
	

Duplicate-interaction rule: one Order Number produces one SalesCreditCase. Every qualifying Synthetic Interaction Queue interaction is attached to that case. The system must not create duplicate totals, duplicate manager outcomes, or duplicate audit records for the same order.
6.7 ManagerOutcome
Field
	Type
	Rule
	manager_outcome_id
	UUID
	Primary key.
	case_id
	UUID
	Exactly one case.
	outcome
	enum
	APPROVED, DENIED, PARTIAL, OTHER_REP, or NOT_PURSUED.
	decided_at
	timestamp
	Human decision time.
	decided_by
	string, nullable
	Manager identifier when appropriate.
	approved_amount
	decimal, nullable
	Required only when tracked and applicable.
	reason_code
	string, nullable
	Optional controlled vocabulary.
	notes
	string, nullable
	Concise human explanation; no unnecessary customer data.
	recorded_at
	timestamp
	When the outcome was entered.
	

6.8 ClosedAuditRecord
ClosedAuditRecord is the only long-lived case representation. It contains the minimum needed to understand what happened without preserving a customer database.
* Case ID and Synthetic Interaction Queue source references.
* Order Number; interaction and order timestamps with precision.
* Raw order-level Sales Rep tag and relevant Placed Order Total.
* Final classifications, evidence source types/classifications, workflow outcome, and manager outcome.
* Check timestamps, parser version, rules version, closure time, and concise human notes.
* No customer email, phone, persistent hashed identity, full OrderSnapshot, full line items, raw Synthetic Order Portal notes, or full communication content.
7. Synthetic Interaction Queue Intake and Normalization
Synthetic Interaction Queue is the authoritative starting point. One row represents one logged interaction; repeat customers may have multiple rows across weekly tabs.
* Future intake fields are Interaction Date, Interaction Time, Email, Phone, VIN, Part / Request, and Notes.
* When the first usable email or phone is entered, the intake layer stamps immutable Recorded At and, unless a later-entry correction is indicated, initializes Interaction At.
* Manual Interaction At corrections preserve the original Recorded At and add correction provenance.
* Email is trimmed and case-folded. The system never guesses misspellings or alternate addresses.
* Phone normalization removes formatting and accepts only values that can safely become the ten-digit Synthetic Order Portal search form.
* VIN is reference context only; email and phone are the supported Synthetic Order Portal search keys.
* Malformed or missing identifiers route to cleanup and do not trigger automated Synthetic Order Portal searching.
8. Order Discovery and Matching
* Search every valid email and phone for the interaction. When both exist, both searches are mandatory.
* Combine the complete native result sets and deduplicate by Order Number.
* Evaluate every candidate order independently. Finding one order never stops evaluation of additional orders.
* A different displayed customer name does not invalidate a match when a valid searched identifier establishes the relationship.
* Record whether each native result set was complete. Incomplete result enumeration prevents a “no order found” conclusion.
* An interaction with no qualifying order may be checked automatically at most once per local calendar day while the review window remains active.
* Force Recheck bypasses the throttle only for explicitly selected cases and is logged.
9. Deterministic Rules Engine
9.1 Decision precedence
1. Validate the snapshot. INVALID stops automated processing; PARTIAL blocks only dependent decisions.
2. Capture every matching order before evaluating status.
3. Evaluate cancellation and replacement-window behavior.
4. Evaluate material commercial changes and ability to establish Placed Order Total.
5. Classify attribution from the raw order-level Sales Rep value.
6. If evidence is required, classify exact pre-order contact evidence and timing.
7. Route every ambiguity to a named human-review state; never guess.
9.2 Sales-rep classification
Raw value
	Attribution result
	Workflow effect
	target_rep or target_rep_web
	CREDIT_CONFIRMED_TARGET_REP
	No further attribution investigation. Material-change review may still be required for order value.
	unassigned_web
	EVIDENCE_NEEDED
	Evaluate pre-order contact evidence.
	Any other known rep
	OTHER_REP_HUMAN_REVIEW
	Preserve raw value and relevant evidence.
	Missing or unrecognized
	MANUAL_REVIEW_REQUIRED
	Never silently remap.
	

9.3 Contact evidence classification
Evidence
	Classification
	Verified two-way pre-order interaction or connected pre-order Synthetic Call Source call
	VERIFIED_PREORDER_EVIDENCE
	Inbound-only pre-order contact with no documented TARGET_REP response
	INBOUND_EVIDENCE_HUMAN_REVIEW
	Outbound-only pre-order contact with no customer response
	OUTBOUND_EVIDENCE_HUMAN_REVIEW
	Missed or unanswered inbound call before purchase
	INBOUND_EVIDENCE_HUMAN_REVIEW
	Post-order contact only
	Does not establish attribution; human review if otherwise relevant.
	Same-day evidence without reliable time ordering
	TIMING_UNCERTAIN_HUMAN_REVIEW
	

10. Cancellation, Replacement, and Product Continuity
* Cancelled matching orders remain in the audit trail but do not count as active Sales Credit value.
* A cancelled qualifying order opens a replacement-search window through fourteen full calendar days after the cancellation date.
* The replacement window may extend beyond the original interaction review window.
* A replacement requires customer continuity plus product continuity with the cancelled order.
* Exact normalized ES# or exact normalized manufacturer part number establishes deterministic product continuity.
* Similar, equivalent, superseding, bundled, or substitute products require human review.
* One exact matching product is enough to make the replacement order relevant, but the manager decides whether credit applies to that line, related lines, or the entire replacement order.
* No relevant product continuity means the new order is not treated as a continuation of the cancelled opportunity.
11. Original Order Value and Material Changes
Sales Credit uses the value of the order when originally placed. Current Order Total is an observed fact, not a substitute for Placed Order Total.
* Material changes include added or removed products, quantity changes, substitutions, partial cancellations, shipping-charge changes, discounts, price adjustments, refunds, and returns that alter commercial value.
* Routine warehouse, inventory, shipment-tracking, and administrative events are not material solely because order lifecycle status changed.
* Material changes set order_value_status to CHANGED_REVIEW and workflow_state to ORDER_CHANGED_HUMAN_REVIEW until Placed Order Total is reconstructed or verified.
* Synthetic Order Portal Notes may be read to detect or reconstruct change history, but notes remain temporary and are never written.
* If the placed value cannot be established reliably, the system requires human verification and must not estimate.
12. Workflow States and Transitions
State
	Entry condition
	Exit
	AWAITING_OA_REVIEW
	Usable interaction has not been checked.
	Intentional Sales Credit Check run.
	CHECKED_NO_ORDER_WINDOW_ACTIVE
	Complete searches found no qualifying order; window remains active.
	Next eligible daily check, Force Recheck, or window close.
	REVIEW_WINDOW_CLOSED_NO_ORDER
	No qualifying order by review-window end.
	CLOSED.
	CREDIT_CONFIRMED_TARGET_REP
	Attribution tag is target_rep or target_rep_web and no blocking value issue.
	Manager outcome or closure.
	EVIDENCE_NEEDED
	unassigned_web or another evidence-dependent state.
	Evidence classification.
	VERIFIED_PREORDER_EVIDENCE
	Deterministic two-way/connected pre-order evidence.
	Manager outcome or closure.
	OUTBOUND_EVIDENCE_HUMAN_REVIEW
	Outbound-only evidence.
	Human decision.
	INBOUND_EVIDENCE_HUMAN_REVIEW
	Inbound-only, missed, or unanswered evidence.
	Human decision.
	OTHER_REP_HUMAN_REVIEW
	Another rep appears on the order.
	Human decision.
	ORDER_CHANGED_HUMAN_REVIEW
	Material change or placed value uncertainty.
	Human verification.
	CANCELLED_REPLACEMENT_WINDOW_ACTIVE
	Qualifying order cancelled; replacement window open.
	Replacement found or window expires.
	POSSIBLE_REPLACEMENT_HUMAN_REVIEW
	Potential replacement requires non-deterministic continuity review.
	Human decision.
	CANCELLED_NO_REPLACEMENT
	Replacement window expired without relevant order.
	CLOSED.
	MANUAL_REVIEW_REQUIRED
	Missing, invalid, unsupported, or contradictory facts.
	Human resolution.
	CLOSED
	Manager outcome or terminal no-order/no-replacement result recorded.
	Minimize active data and start retention clock.
	

13. Persistence, Minimization, and 90-Day Retention
* The local database is workflow state, not a second copy of Synthetic Order Portal and not a customer CRM.
* Full email, phone, snapshots, line items, notes, and evidence excerpts may exist only while a case is active and needed.
* Case closure is transactional: write the minimized ClosedAuditRecord, verify it, remove disallowed active data, and commit.
* Customer email and phone are removed at closure. v0.1 stores no persistent hashed customer identity.
* Full Synthetic Email Source, Synthetic Chat Source, Synthetic Message Source, Synthetic Call Source, and Synthetic Order Portal Notes content is removed at closure; retain only source references and structured evidence metadata.
* Minimized closed records expire 90 days after closed_at. Purge runs on startup and at least daily, is idempotent, and records only aggregate purge diagnostics.
* Exports, logs, temporary files, fixtures derived from real data, and local backups must follow the same minimization and retention policy.
* Purge tests use an injectable clock and prove that records are retained before expiry and deleted at or after expiry.
14. Historical Timestamp Migration
14.1 Migration policy
1. Create and verify a distinct rollback-safe copy of the workbook before any write.
2. Read spreadsheet metadata and exact target cells. Abort if any target audit cell is already populated unexpectedly.
3. For each row, choose a unique stable identifier in the order email, normalized phone, then VIN. Repeated or non-unique identifiers require stronger disambiguation or no timestamp.
4. Compare successive Drive revisions. The first revision where the identifier appears is the Recorded At upper-bound approximation; the immediately prior revision is the lower-bound window start.
5. Write REVISION_DERIVED for a safely isolated row. Write no timestamp for an unresolved row and label it HISTORICAL_APPROXIMATION with an explanation.
6. Search approved exact sources. Only exact source evidence may populate Interaction At as EXACT.
7. Never overwrite an existing exact value with revision-derived or approximate data.
8. Write provenance alongside each migrated value and verify every written range after the update.
14.2 Live migration result
The executed two-week migration reviewed 147 populated rows. It wrote revision-derived Recorded At upper bounds for 140 rows, left 7 rows without an invented timestamp because they could not be isolated safely, and added exact Synthetic Chat Source-backed Interaction At values for 3 rows. Original Synthetic Interaction Queue cells were not overwritten.
14.3 Audit columns used
* Recorded At (Approx)
* Recorded At Window Start
* Recorded At Precision
* Interaction At (Exact Only)
* Interaction At Precision
* Timestamp Evidence
15. Manager Outcome Tracking and Evaluation
The system records the manager’s decision as a human outcome; it does not automate or predict managerial authority. Outcomes support accuracy measurement, regression labels, and productivity analysis.
* Approved, Denied, Partial, Other Rep, and Not Pursued are the controlled outcome values.
* Outcome entry requires decided_at and recorded_at, plus approved amount when Partial or amount tracking is used.
* System classification and manager outcome remain separate fields so disagreement can be measured.
* Metrics may include case volume, time-to-review, percent requiring human review, agreement rate, and false automatic-confirmation count.
* Metrics must not reintroduce persistent customer identity or retain raw communication content.
16. Logging, Security, and Failure Behavior
* Use structured logs with event type, case or run ID, parser/rules version, status, and warning codes. Do not log raw email, phone, notes, message bodies, cookies, or session tokens.
* Redact approved identifiers from exception text before persistence.
* Treat selector mismatch, unknown DOM, partial result sets, missing required fields, parse disagreement, and notes-scan incompleteness as explicit errors or warnings—not silent defaults.
* The extension relies on the user’s existing authenticated browser session but never reads, exports, or stores authentication secrets.
* Development and tests use synthetic data. Any real-data fixture requires minimization, explicit justification, and the same retention policy.
17. Test Specification
Test family
	Required coverage
	Schema tests
	Required/optional/conditional fields; VALID/PARTIAL/INVALID; enum rejection; timezone awareness; decimal money.
	Normalization tests
	Email trimming/case folding; valid phone normalization; malformed phone rejection; no guessed emails.
	Window tests
	Interaction date included; fourteen full days after; DST boundaries; same-day uncertainty; replacement-window extension.
	Search tests
	Both identifiers searched; complete result-set combination; Order Number deduplication; no early exit.
	Rules tests
	All rep tags; missing tags; evidence classes; material changes; cancellations; replacements; exact ES#/MFG# continuity.
	Case dedup tests
	Multiple interactions attach to one order case; totals and outcomes are not duplicated.
	Retention tests
	Transactional closure minimization; no identity after closure; 90-day boundary; idempotent purge; backup/temp cleanup.
	Migration tests
	Revision intervals; unique-identifier selection; repeated identifiers; exact-value preservation; exact-source upgrade.
	Parser tests
	Normal, unassigned_web, cancelled, changed, multi-item, partial notes, and malformed fake pages.
	Safety tests
	No OA write API; no mutation request; no write-control activation; no DOM mutation for order state; unknown page fails closed.
	Historical regression
	Fifty to one hundred reviewed real cases converted to minimized expected outcomes.
	Shadow mode
	Compare system output with the existing human process before operational reliance.
	

17.1 Required safety assertions
* A static scan finds no Synthetic Order Portal mutation functions or generic arbitrary-request helper.
* A network spy records zero non-read Synthetic Order Portal requests across every extension test.
* Write-capable controls in fake pages are instrumented; activation count must remain zero.
* Malformed or changed DOM returns INVALID or MANUAL_REVIEW_REQUIRED and never guesses selectors.
* Authentication/session data intentionally written to disk equals zero.
* The read-only invariant is covered by tests that cannot be disabled through configuration.
18. Production-Readiness Gates
* Required-field extraction is 100% on every supported approved Synthetic Order Portal page type.
* Known deterministic classifications are 100% against the approved regression suite.
* False automatic confirmed-credit decisions are zero.
* Every ambiguous or unsupported case routes to human review.
* Unrecognized page structures fail closed.
* Synthetic Order Portal writes are zero by architecture, static review, and automated tests.
* Intentionally stored authentication or session secrets are zero.
* Closure minimization and 90-day purge tests pass at boundary conditions.
* Historical migration preserves every pre-existing exact value and exposes uncertainty.
* Shadow-mode results are reviewed against the existing human process before operational reliance.
* A rollback procedure, versioned parser/rules identifiers, and operator-facing error instructions are documented.
19. Implementation Sequence and Milestones
Milestone A — Offline Core
* Repository, linting, typed models, schema validation, rules engine, SQLite lifecycle, purge service, tests, fake OA HTML, and extension skeleton.
* No production OA selectors, no production navigation automation, no Native Messaging deployment on the work PC, and no automatic OA batch runs.
* Exit only when schema/rules/regression/minimization/purge/safety tests pass and no OA mutation capability exists.
Milestone B — Controlled OA Reconnaissance
* Supervised read-only mapping of search-result and order-detail DOM.
* Capture selector candidates, raw rep tags, order states, Notes patterns, line-item structure, match counts, and confidence.
* Confirm managed Chrome extension policy and Native Messaging availability.
* Do not modify orders or activate write controls.
Milestone C — Production OA Reader
* Implement only the real Synthetic Order Portal adapter behind the already-tested OrderSnapshot interface.
* Validate one order at a time, then run shadow mode.
* Operational reliance begins only after production-readiness gates pass.
20. Recommended Repository Layout
synthetic-sales-assist/
├── pyproject.toml
├── README.md
├── src/synthetic_sales_assist/
│   ├── domain/          # typed models and enums
│   ├── normalization/   # email, phone, part identifiers, time
│   ├── rules/           # deterministic classifications
│   ├── storage/         # SQLite repositories, closure, purge
│   ├── workflows/       # intake, search runs, case transitions
│   └── adapters/
│       ├── customer_followup/
│       ├── order_admin/ # protocol + fake adapter; real adapter deferred
│       └── evidence/
├── extension/           # Manifest V3 read-only reader skeleton
├── fixtures/order_admin/
├── tests/
│   ├── unit/
│   ├── rules/
│   ├── safety/
│   ├── parser/
│   ├── retention/
│   └── regression/
└── docs/
21. Deferred External Verifications
The specification is implementation-ready for Milestone A. The following facts remain intentionally deferred and must not be guessed:
* Real Synthetic Order Portal search-result row structure and production selectors.
* Real order-detail selectors for Order Number, Order Time, status, order-level Sales Rep, total, customer identifiers, line items, and Notes.
* The exact raw unassigned_web representation and other live rep-tag variants.
* Real cancelled-order and materially changed-order Notes wording.
* Managed Chrome permission to load the extension on the Synthetic Order Portal origin.
* Native Messaging availability and the approved fallback transport.
* Any special order statuses beyond Cancelled.
* The final future-week Synthetic Interaction Queue intake layout.
22. Codex Handoff Acceptance Checklist
* Treat this document as the governing v0.1 contract.
* Implement Milestone A only; stop before production OA selectors or live navigation.
* Keep Synthetic Order Portal 100% read-only with no mutation capability.
* Use synthetic fixtures and minimized regression data.
* Make ambiguous inputs fail closed and route to human review.
* Keep observed facts separate from derived decisions.
* Implement transactional closure minimization and tested 90-day purge.
* Report any specification ambiguity before inventing behavior.
* Do not cross into Milestone B or C without supervised reconnaissance evidence.
