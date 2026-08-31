/* SYNTHETIC-SALES-ASSIST-AUTHORED-M6 */
"use strict";

(() => {
  const EXTENSION_VERSION = "0.1.0";
  const API_SCHEMA_VERSION = "synthetic-sales-assist-api/v1";
  const API_REQUEST_SCHEMA_VERSION = "synthetic-sales-assist-api-request/v1";
  const APPLICATION_SCHEMA_VERSION = "synthetic-sales-assist-application/v1";
  const DOM_SCHEMA_VERSION = "synthetic-sales-assist-dom/v1";
  const EXTRACTION_SCHEMA_VERSION = "synthetic-sales-assist-extension-extraction/v1";
  const MESSAGE_SCHEMA_VERSION = "synthetic-sales-assist-extension-message/v1";
  const ORDER_BINDING_SCHEMA_VERSION =
    "synthetic-sales-assist-extension-order-binding/v1";
  const LINE_MANIFEST_SCHEMA_VERSION = "synthetic-sales-assist-line-manifest/v1";
  const LINE_MANIFEST_DOMAIN = "m5-rendered-line-manifest/v1";
  const SERVICE_PORT = "8765";

  const PANEL_STATES = Object.freeze([
    "UNSUPPORTED_PAGE",
    "SUPPORTED_READY",
    "INCOMPLETE_PAGE",
    "MALFORMED_PAGE",
    "DOM_PAYLOAD_MISMATCH",
    "BACKEND_OFFLINE",
    "BACKEND_UNHEALTHY",
    "EVALUATING",
    "SALES_CREDIT_RESULT",
    "DOI_OPPORTUNITY",
    "DOI_MANUAL_REVIEW",
    "DOI_EXCLUDED",
    "DOI_MONITOR",
    "EXACT_REPLAY",
    "REQUEST_CONFLICT",
    "SAFE_ERROR"
  ]);

  const MESSAGE_KINDS = Object.freeze(["GET_PAGE_STATE", "EVALUATE"]);
  const REQUEST_KEY_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}(?![\s\S])/;
  const SAFE_CODE_PATTERN = /^[A-Z][A-Z0-9_]{0,95}(?![\s\S])/;
  const TOKEN_PATTERN = /^[A-Z][A-Z0-9_.:/-]{0,255}(?![\s\S])/;
  const ALIAS_PATTERN = /^[a-z][a-z0-9-]{0,62}[a-z0-9](?![\s\S])/;
  const LOOPBACK_ORIGIN_PATTERN =
    /^http:\/\/(?:127\.0\.0\.1|localhost):8765(?![\s\S])/;
  const LOWER_SHA256_PATTERN = /^[0-9a-f]{64}(?![\s\S])/;
  const ASCII_PATTERN = /^[\x00-\x7f]+(?![\s\S])/;
  const INTEGER_AMOUNT_PATTERN = /^-?(?:0|[1-9][0-9]*)(?![\s\S])/;
  const NEGATIVE_ZERO_PATTERN = /^-0(?:\.0+)?(?![\s\S])/;
  const DOI_REASON_PATTERN = /^RC-([0-9]{3})(?![\s\S])/;
  const RESPONSE_MEMBERS = Object.freeze(["data", "error_code", "panel_state", "schema_version"]);
  const SUMMARY_MEMBERS = Object.freeze([
    "backend", "can_evaluate", "completeness_state", "evaluation", "interaction_id",
    "order_id", "origin", "page_identity", "page_kind", "rule_pack", "scenario_alias",
    "source_fingerprint"
  ]);
  const BACKEND_MEMBERS = Object.freeze([
    "app_version", "build_version", "database_schema_version", "healthy",
    "safety_counters_zero", "status"
  ]);
  const PROJECTED_EVALUATION_MEMBERS = Object.freeze([
    "aggregate_potential_status", "aggregate_potential_value", "case_id", "closure_state",
    "command_id", "conflict", "evaluation_id", "handling_flags", "human_review_required",
    "opportunities", "order_id", "processing_duration_ns", "reasons", "replayed",
    "rule_pack", "rule_pack_version", "run_id", "scenario_alias", "snapshot_id",
    "top_level_result", "value", "value_status", "workflow_state"
  ]);
  const OPPORTUNITY_MEMBERS = Object.freeze(["line_ids", "opportunity_type", "potential_value"]);
  const MONEY_MEMBERS = Object.freeze([
    "amount", "currency_code", "currency_registry_version", "currency_scale"
  ]);
  const CURRENCY_SCALES = Object.freeze({EUR: 2, JPY: 0, KWD: 3, USD: 2});
  const SALES_CREDIT_RESULTS = Object.freeze([
    "AWAITING_SOURCE_REVIEW", "CHECKED_NO_ORDER_WINDOW_ACTIVE", "REVIEW_WINDOW_CLOSED_NO_ORDER",
    "CREDIT_CONFIRMED_TARGET_REP", "EVIDENCE_NEEDED", "VERIFIED_PREORDER_EVIDENCE",
    "OUTBOUND_EVIDENCE_HUMAN_REVIEW", "INBOUND_EVIDENCE_HUMAN_REVIEW",
    "TIMING_UNCERTAIN_HUMAN_REVIEW", "OTHER_REP_HUMAN_REVIEW",
    "ORDER_CHANGED_HUMAN_REVIEW", "CANCELED_REPLACEMENT_WINDOW_ACTIVE",
    "POSSIBLE_REPLACEMENT_HUMAN_REVIEW", "CANCELED_NO_REPLACEMENT",
    "MANUAL_REVIEW_REQUIRED", "CLOSED"
  ]);
  const SALES_CREDIT_HUMAN_REVIEW_WORKFLOWS = Object.freeze([
    "INBOUND_EVIDENCE_HUMAN_REVIEW", "MANUAL_REVIEW_REQUIRED",
    "ORDER_CHANGED_HUMAN_REVIEW", "OTHER_REP_HUMAN_REVIEW",
    "OUTBOUND_EVIDENCE_HUMAN_REVIEW", "POSSIBLE_REPLACEMENT_HUMAN_REVIEW",
    "TIMING_UNCERTAIN_HUMAN_REVIEW"
  ]);
  const DOI_RESULTS = Object.freeze([
    "DOI_OPPORTUNITY", "DOI_MANUAL_REVIEW", "DOI_EXCLUDED", "DOI_MONITOR"
  ]);
  const DOI_WORKFLOW_STATES = Object.freeze(["ACTIVE", "CLOSED_HARD", "CLOSED_REVERSIBLE"]);
  const RULE_PACKS = Object.freeze(["SALES_CREDIT", "DOI"]);
  const SALES_CREDIT_VALUE_STATUSES = Object.freeze([
    "PLACED_VALUE_VERIFIED", "CURRENT_ONLY", "CHANGED_REVIEW", "UNKNOWN"
  ]);
  const SALES_CREDIT_CLOSURES = Object.freeze(["ACTIVE", "CANCELED", "UNKNOWN"]);
  const SALES_CREDIT_EFFECTS = Object.freeze([
    "NO_PERSISTENCE_MILESTONE_2", "HUMAN_REVIEW_REQUIRED", "ZERO_ACTIVE_VALUE",
    "ACTIVE_CASE_CLASSIFICATION"
  ]);
  const SALES_CREDIT_REASONS = Object.freeze([
    "NO_USABLE_SEARCH_IDENTIFIER", "IDENTIFIER_SEARCH_INCOMPLETE", "NO_ORDER_WINDOW_ACTIVE",
    "NO_ORDER_WINDOW_CLOSED", "ORDER_BEFORE_INTERACTION", "ORDER_AFTER_REVIEW_WINDOW",
    "ORDER_BEFORE_CANCELLATION", "ORDER_AFTER_REPLACEMENT_WINDOW", "ORDER_TIMING_UNCERTAIN",
    "AUTOMATIC_RECHECK_THROTTLED_LOCAL_DAY", "FORCE_RECHECK_ACCEPTED", "SNAPSHOT_INVALID",
    "SNAPSHOT_PARTIAL_DEPENDENCY_BLOCKED", "MISSING_REQUIRED_FIELD",
    "UNSUPPORTED_SCHEMA_OR_SNAPSHOT", "CONTRADICTORY_FACTS", "TARGET_REP", "TARGET_REP_WEB",
    "UNASSIGNED_WEB", "OTHER_KNOWN_REP", "REP_MISSING", "REP_UNRECOGNIZED",
    "TWO_WAY_PREORDER_INTERACTION", "CONNECTED_PREORDER_CALL",
    "INBOUND_ONLY_PREORDER_CONTACT", "OUTBOUND_ONLY_PREORDER_CONTACT",
    "MISSED_OR_UNANSWERED_INBOUND_CALL", "POST_ORDER_CONTACT_ONLY",
    "EVIDENCE_TIMING_UNCERTAIN", "EVIDENCE_IDENTITY_UNPROVED",
    "NO_QUALIFYING_PREORDER_EVIDENCE", "CANCELED_ORDER_ZERO_ACTIVE_VALUE",
    "REPLACEMENT_WINDOW_ACTIVE", "EXACT_ES_PRODUCT_CONTINUITY",
    "EXACT_MFG_OE_PRODUCT_CONTINUITY", "NONEXACT_PRODUCT_CONTINUITY_REQUIRES_REVIEW",
    "CUSTOMER_CONTINUITY_UNPROVED", "CUSTOMER_CONTINUITY_MISMATCH", "NO_PRODUCT_CONTINUITY",
    "REPLACEMENT_WINDOW_EXPIRED", "PLACED_VALUE_PROVED", "PLACED_VALUE_UNAVAILABLE",
    "MATERIAL_CHANGE_DETECTED", "ROUTINE_LIFECYCLE_CHANGE_NONMATERIAL",
    "AMBIGUOUS_FACTS_REQUIRE_HUMAN_REVIEW"
  ]);
  const DOI_VALUE_STATUSES = Object.freeze(["AVAILABLE", "UNAVAILABLE"]);
  const DOI_CLOSURES = Object.freeze([
    "NONE", "SHIPPED", "CANCELED", "REP_TRANSFERRED", "DEDUPE_CONFIRMED",
    "HUMAN_OUT_OF_SCOPE"
  ]);
  const DOI_OPPORTUNITY_TYPES = Object.freeze([
    "FULFILLMENT_SPLIT", "DS_SEPARATION", "EXACT_SKU_RECHECK", "EXACT_MFG_ALTERNATE",
    "MFG_CROSS_REFERENCE", "MFG_SUPERSESSION", "FUNCTIONAL_ALTERNATE",
    "PARTIAL_QUANTITY_REVIEW"
  ]);
  const DOI_HANDLING_FLAGS = Object.freeze([
    "PAYMENT_BEFORE_ACTION", "AK_HI_SHIPPING_REVIEW", "INTERNATIONAL_REVIEW",
    "GEOGRAPHY_ACTION_READINESS_REVIEW_REQUIRED", "CUSTOMER_CONTACT_BEFORE_SPLIT",
    "CUSTOMER_APPROVAL_REQUIRED", "COMPATIBILITY_REVIEW_REQUIRED",
    "HUMAN_SCENARIO_SELECTION_REQUIRED", "ETA_RANKING_UNAVAILABLE", "OUTREACH_SUPPRESSED",
    "SOURCE_ABSENCE_RECHECK_REQUIRED"
  ]);
  const SYNTHETIC_ID_PATTERNS = Object.freeze({
    ORDER: /^SYN-ORDER-[A-Z0-9]+(?:-[A-Z0-9]+)*(?![\s\S])/,
    INTERACTION: /^SYN-INTERACTION-[A-Z0-9]+(?:-[A-Z0-9]+)*(?![\s\S])/,
    EVIDENCE: /^SYN-EVIDENCE-[A-Z0-9]+(?:-[A-Z0-9]+)*(?![\s\S])/,
    SKU: /^SYN-SKU-[A-Z0-9]+(?:-[A-Z0-9]+)*(?![\s\S])/,
    RUN: /^SYN-RUN-[A-Z0-9]+(?:-[A-Z0-9]+)*(?![\s\S])/,
    SNAPSHOT: /^SYN-SNAPSHOT-[A-Z0-9]+(?:-[A-Z0-9]+)*(?![\s\S])/,
    EVALUATION: /^SYN-EVALUATION-[A-Z0-9]+(?:-[A-Z0-9]+)*(?![\s\S])/
  });
  const RESERVED_NAMESPACES = Object.freeze(Object.keys(SYNTHETIC_ID_PATTERNS));

  const SAFETY_COUNTER_NAMES = Object.freeze([
    "EXTERNAL_MUTATION_REQUEST_COUNT",
    "EXTERNAL_PRODUCTION_SYSTEM_ACCESS_COUNT",
    "NON_LOCALHOST_RUNTIME_REQUEST_COUNT",
    "NON_SYNTHETIC_FIXTURE_COUNT",
    "PRODUCTION_MUTATION_REQUEST_COUNT",
    "PRODUCTION_SYSTEM_ACCESS_COUNT",
    "REAL_CUSTOMER_DATA_COUNT",
    "REAL_CUSTOMER_IDENTITY_COUNT",
    "SECRET_MATERIAL_COUNT"
  ]);

  const EXTRACTION_ALLOWLIST = Object.freeze({
    order: Object.freeze(["completeness", "lines", "mode", "order_id", "scenario_alias", "schema_version", "source_status"]),
    order_binding: Object.freeze(["order_id", "rule_pack", "schema_version"]),
    completeness: Object.freeze(["declared_relevant_line_count", "fixture_version", "observed_order_id", "ordered_line_manifest_digest", "rendered_relevant_line_count", "requested_order_id", "source_observed_at", "source_schema_version", "state"]),
    line: Object.freeze(["activity", "availability", "drop_ship_state", "eta", "line_id", "line_index", "line_value", "product_id", "quantity"]),
    fact: Object.freeze(["reason_code", "tag", "value"]),
    money: Object.freeze(["amount", "currency_code", "currency_registry_version", "currency_scale"]),
    interaction: Object.freeze(["direction", "evidence_classification", "identifier_kind", "interaction_id", "order_id", "schema_version", "target_rep_participation", "timestamp", "timestamp_precision"])
  });

  function contractError(code) {
    const error = new Error(code);
    error.name = "ExtensionContractError";
    error.code = code;
    throw error;
  }

  function validateRequestKey(value) {
    if (value === null) return null;
    if (typeof value !== "string" || !REQUEST_KEY_PATTERN.test(value)) {
      contractError("REQUEST_KEY_INVALID");
    }
    return value;
  }

  function validateMessage(value) {
    const canonical = globalThis.SSA.Canonical;
    canonical.exactMembers(value, [
      "expected_order_id", "expected_origin", "expected_source_fingerprint", "kind",
      "request_key", "schema_version"
    ], "MESSAGE_MEMBERS_INVALID");
    if (value.schema_version !== MESSAGE_SCHEMA_VERSION || !MESSAGE_KINDS.includes(value.kind)) {
      contractError("MESSAGE_CONTRACT_INVALID");
    }
    validateRequestKey(value.request_key);
    if (value.kind === "GET_PAGE_STATE") {
      if (
        value.request_key !== null || value.expected_order_id !== null ||
        value.expected_origin !== null || value.expected_source_fingerprint !== null
      ) contractError("MESSAGE_PAGE_BINDING_PROHIBITED");
    } else {
      if (
        value.request_key === null ||
        typeof value.expected_origin !== "string" ||
        !LOOPBACK_ORIGIN_PATTERN.test(value.expected_origin) ||
        typeof value.expected_source_fingerprint !== "string" ||
        !LOWER_SHA256_PATTERN.test(value.expected_source_fingerprint)
      ) contractError("MESSAGE_PAGE_BINDING_REQUIRED");
      validateSyntheticId(value.expected_order_id, "ORDER");
    }
    return value;
  }

  function validateSyntheticId(value, namespace) {
    const pattern = SYNTHETIC_ID_PATTERNS[namespace];
    if (
      typeof value !== "string" || value.length === 0 || value.length > 128 ||
      !ASCII_PATTERN.test(value) || !pattern || !pattern.test(value)
    ) {
      contractError(`${namespace}_ID_INVALID`);
    }
    return value;
  }

  function validateAnySyntheticId(value) {
    if (typeof value !== "string") contractError("SYNTHETIC_ID_INVALID");
    const namespace = RESERVED_NAMESPACES.find((candidate) => value.startsWith(`SYN-${candidate}-`));
    if (!namespace) contractError("SYNTHETIC_ID_INVALID");
    return validateSyntheticId(value, namespace);
  }

  function validateSafeCode(value, fallback = "SAFE_ERROR") {
    return typeof value === "string" && SAFE_CODE_PATTERN.test(value) ? value : fallback;
  }

  function validateNoRedirectResponse(responseValue) {
    if (
      responseValue !== null && typeof responseValue === "object" && (
        responseValue.type === "opaqueredirect" ||
        Number.isInteger(responseValue.status) &&
          responseValue.status >= 300 && responseValue.status <= 399
      )
    ) contractError("RESPONSE_REDIRECT_INVALID");
    return responseValue;
  }

  function validateAlias(value, code = "ALIAS_INVALID") {
    if (typeof value !== "string" || !ALIAS_PATTERN.test(value)) contractError(code);
    return value;
  }

  function validateToken(value, code) {
    if (typeof value !== "string" || !TOKEN_PATTERN.test(value)) contractError(code);
    return value;
  }

  function validateMoney(value, code) {
    if (value === null) return null;
    const canonical = globalThis.SSA.Canonical;
    canonical.exactMembers(value, MONEY_MEMBERS, code);
    if (typeof value.currency_code !== "string") contractError(code);
    const scale = CURRENCY_SCALES[value.currency_code];
    const amountPattern = scale === 0
      ? INTEGER_AMOUNT_PATTERN
      : new RegExp(`^-?(?:0|[1-9][0-9]*)\\.[0-9]{${scale}}(?![\\s\\S])`);
    if (
      scale === undefined || typeof value.amount !== "string" ||
      !amountPattern.test(value.amount) ||
      value.currency_registry_version !== "synthetic-iso-style-currency-registry/v1" ||
      value.currency_scale !== scale || NEGATIVE_ZERO_PATTERN.test(value.amount)
    ) contractError(code);
    return value;
  }

  function validateTokenList(value, code) {
    if (!Array.isArray(value) || !value.every((item) => (
      typeof item === "string" && TOKEN_PATTERN.test(item)
    ))) contractError(code);
    return value;
  }

  function validateExactList(value, allowed, code) {
    if (
      !Array.isArray(value) || !value.every((item) => allowed.includes(item)) ||
      new Set(value).size !== value.length
    ) contractError(code);
    return value;
  }

  function isDoiReason(value) {
    if (typeof value !== "string") return false;
    const match = DOI_REASON_PATTERN.exec(value);
    if (match === null) return false;
    const number = Number(match[1]);
    return number >= 1 && number <= 138;
  }

  function sameMoneyDefinition(left, right) {
    return (
      left.currency_code === right.currency_code &&
      left.currency_registry_version === right.currency_registry_version &&
      left.currency_scale === right.currency_scale
    );
  }

  function salesCreditDisplayIsCoherent(value) {
    const canonical = globalThis.SSA.Canonical;
    const canceled = value.reasons.includes("CANCELED_ORDER_ZERO_ACTIVE_VALUE");
    const valueMatchesStatus = value.value_status === "PLACED_VALUE_VERIFIED"
      ? value.value !== null && value.aggregate_potential_value !== null &&
        sameMoneyDefinition(value.value, value.aggregate_potential_value) &&
        (canceled
          ? /^0(?:\.0+)?(?![\s\S])/.test(value.value.amount)
          : canonical.canonicalStringify(value.value) ===
            canonical.canonicalStringify(value.aggregate_potential_value))
      : value.value_status === "CHANGED_REVIEW"
        ? canonical.canonicalStringify(value.value) ===
          canonical.canonicalStringify(value.aggregate_potential_value)
        : value.value === null && value.aggregate_potential_value === null;
    const flags = new Set(value.handling_flags);
    const expectedHumanReview = SALES_CREDIT_HUMAN_REVIEW_WORKFLOWS.includes(
      value.workflow_state
    );
    return (
      valueMatchesStatus && value.human_review_required === expectedHumanReview &&
      (value.closure_state === "CANCELED") === canceled &&
      flags.has("NO_PERSISTENCE_MILESTONE_2") &&
      flags.has("HUMAN_REVIEW_REQUIRED") === value.human_review_required &&
      flags.has("ACTIVE_CASE_CLASSIFICATION") === !value.human_review_required &&
      flags.has("ZERO_ACTIVE_VALUE") === canceled
    );
  }

  function doiDisplayIsCoherent(value) {
    const expectedWorkflow = value.closure_state === "NONE"
      ? "ACTIVE"
      : ["SHIPPED", "CANCELED"].includes(value.closure_state)
        ? "CLOSED_HARD"
        : "CLOSED_REVERSIBLE";
    const isOpportunity = value.top_level_result === "DOI_OPPORTUNITY";
    return (
      (isOpportunity || (
        value.value_status === "UNAVAILABLE" && value.value === null &&
        value.aggregate_potential_value === null
      )) &&
      value.workflow_state === expectedWorkflow &&
      (value.closure_state === "NONE" || value.top_level_result === "DOI_EXCLUDED") &&
      (value.top_level_result !== "DOI_MANUAL_REVIEW" || value.human_review_required)
    );
  }

  function validateBackend(value) {
    const canonical = globalThis.SSA.Canonical;
    canonical.exactMembers(value, BACKEND_MEMBERS, "BACKEND_MEMBERS_INVALID");
    if (
      value.app_version !== "0.1.0" ||
      value.build_version !== "synthetic-sales-assist-m5/v1" ||
      value.database_schema_version !== 4 || typeof value.healthy !== "boolean" ||
      typeof value.safety_counters_zero !== "boolean" ||
      !["PASS", "FAIL"].includes(value.status) ||
      value.status !== (value.healthy ? "PASS" : "FAIL") ||
      value.healthy && !value.safety_counters_zero
    ) contractError("BACKEND_PROJECTION_INVALID");
    return value;
  }

  function validateProjectedEvaluation(value) {
    const canonical = globalThis.SSA.Canonical;
    canonical.exactMembers(
      value,
      PROJECTED_EVALUATION_MEMBERS,
      "PROJECTED_EVALUATION_MEMBERS_INVALID"
    );
    validateSyntheticId(value.order_id, "ORDER");
    validateAlias(value.scenario_alias, "PROJECTED_EVALUATION_SCENARIO_INVALID");
    if (
      !["SALES_CREDIT", "DOI"].includes(value.rule_pack) ||
      typeof value.human_review_required !== "boolean" ||
      typeof value.replayed !== "boolean" || value.conflict !== false ||
      !Number.isSafeInteger(value.processing_duration_ns) ||
      value.processing_duration_ns < 0
    ) contractError("PROJECTED_EVALUATION_INVALID");
    for (const member of [
      "aggregate_potential_status", "top_level_result", "value_status", "workflow_state"
    ]) validateToken(value[member], "PROJECTED_EVALUATION_STATE_INVALID");
    if (value.closure_state !== null) {
      validateToken(value.closure_state, "PROJECTED_EVALUATION_CLOSURE_INVALID");
    }
    validateTokenList(value.reasons, "PROJECTED_EVALUATION_REASONS_INVALID");
    validateTokenList(value.handling_flags, "PROJECTED_EVALUATION_FLAGS_INVALID");
    validateMoney(value.value, "PROJECTED_EVALUATION_VALUE_INVALID");
    validateMoney(
      value.aggregate_potential_value,
      "PROJECTED_EVALUATION_AGGREGATE_VALUE_INVALID"
    );
    if (value.command_id === null || value.evaluation_id === null || value.snapshot_id === null) {
      contractError("PROJECTED_PERSISTED_IDS_REQUIRED");
    }
    validateSyntheticId(value.command_id, "EVIDENCE");
    validateSyntheticId(value.evaluation_id, "EVALUATION");
    if (value.run_id !== null) validateSyntheticId(value.run_id, "RUN");
    validateSyntheticId(value.snapshot_id, "SNAPSHOT");
    const results = value.rule_pack === "SALES_CREDIT" ? SALES_CREDIT_RESULTS : DOI_RESULTS;
    const expectedVersion = value.rule_pack === "SALES_CREDIT"
      ? "synthetic-sales-credit-rules/v1"
      : "synthetic-doi-rule-pack/v1";
    if (value.rule_pack_version !== expectedVersion || !results.includes(value.top_level_result)) {
      contractError("PROJECTED_EVALUATION_PARTITION_INVALID");
    }
    if (value.rule_pack === "SALES_CREDIT") {
      if (value.workflow_state !== value.top_level_result || value.case_id !== value.order_id) {
        contractError("PROJECTED_SALES_CREDIT_BINDING_INVALID");
      }
    } else {
      if (
        !DOI_WORKFLOW_STATES.includes(value.workflow_state) ||
        value.case_id === null || value.run_id === null
      ) {
        contractError("PROJECTED_DOI_WORKFLOW_INVALID");
      }
      validateSyntheticId(value.case_id, "EVIDENCE");
    }
    if (!Array.isArray(value.opportunities)) {
      contractError("PROJECTED_OPPORTUNITIES_INVALID");
    }
    for (const opportunity of value.opportunities) {
      canonical.exactMembers(
        opportunity,
        OPPORTUNITY_MEMBERS,
        "PROJECTED_OPPORTUNITY_MEMBERS_INVALID"
      );
      if (
        !Array.isArray(opportunity.line_ids) ||
        opportunity.line_ids.length === 0 ||
        !opportunity.line_ids.every((lineId) => {
          try {
            validateSyntheticId(lineId, "EVIDENCE");
            return true;
          } catch (_error) {
            return false;
          }
        }) || new Set(opportunity.line_ids).size !== opportunity.line_ids.length
      ) contractError("PROJECTED_OPPORTUNITY_LINES_INVALID");
      validateToken(opportunity.opportunity_type, "PROJECTED_OPPORTUNITY_TYPE_INVALID");
      validateMoney(opportunity.potential_value, "PROJECTED_OPPORTUNITY_VALUE_INVALID");
    }
    if (value.rule_pack === "SALES_CREDIT") {
      if (
        !SALES_CREDIT_VALUE_STATUSES.includes(value.value_status) ||
        value.aggregate_potential_status !== value.value_status ||
        !SALES_CREDIT_CLOSURES.includes(value.closure_state) ||
        value.opportunities.length !== 0 || !salesCreditDisplayIsCoherent(value)
      ) contractError("PROJECTED_SALES_CREDIT_SEMANTICS_INVALID");
      validateExactList(
        value.reasons,
        SALES_CREDIT_REASONS,
        "PROJECTED_SALES_CREDIT_REASONS_INVALID"
      );
      validateExactList(
        value.handling_flags,
        SALES_CREDIT_EFFECTS,
        "PROJECTED_SALES_CREDIT_EFFECTS_INVALID"
      );
    } else {
      const valueAvailable = value.value_status === "AVAILABLE";
      if (
        !DOI_VALUE_STATUSES.includes(value.value_status) ||
        value.aggregate_potential_status !== value.value_status ||
        !DOI_CLOSURES.includes(value.closure_state) ||
        (value.value !== null) !== valueAvailable ||
        (value.aggregate_potential_value !== null) !== valueAvailable ||
        canonical.canonicalStringify(value.value) !==
        canonical.canonicalStringify(value.aggregate_potential_value) ||
        (value.top_level_result === "DOI_OPPORTUNITY") !== (value.opportunities.length > 0) ||
        !doiDisplayIsCoherent(value) ||
        !value.reasons.every(isDoiReason) ||
        new Set(value.reasons).size !== value.reasons.length
      ) contractError("PROJECTED_DOI_SEMANTICS_INVALID");
      validateExactList(
        value.handling_flags,
        DOI_HANDLING_FLAGS,
        "PROJECTED_DOI_HANDLING_FLAGS_INVALID"
      );
      if (!value.opportunities.every((item) => (
        DOI_OPPORTUNITY_TYPES.includes(item.opportunity_type)
      ))) contractError("PROJECTED_DOI_OPPORTUNITY_TYPE_INVALID");
    }
    return value;
  }

  function validateSummary(value) {
    const canonical = globalThis.SSA.Canonical;
    canonical.exactMembers(value, SUMMARY_MEMBERS, "SUMMARY_MEMBERS_INVALID");
    if (
      typeof value.can_evaluate !== "boolean" ||
      ![null, "COMPLETE", "INCOMPLETE", "MALFORMED"].includes(value.completeness_state) ||
      typeof value.origin !== "string" ||
      !LOOPBACK_ORIGIN_PATTERN.test(value.origin) ||
      !["order-detail", "interaction-detail", "unsupported"].includes(value.page_kind) ||
      value.rule_pack !== null && !RULE_PACKS.includes(value.rule_pack)
    ) contractError("SUMMARY_CONTRACT_INVALID");
    if (
      value.source_fingerprint !== null && (
        typeof value.source_fingerprint !== "string" ||
        !LOWER_SHA256_PATTERN.test(value.source_fingerprint)
      )
    ) contractError("SUMMARY_SOURCE_FINGERPRINT_INVALID");
    if (value.backend !== null) validateBackend(value.backend);
    if (value.order_id !== null) validateSyntheticId(value.order_id, "ORDER");
    if (value.interaction_id !== null) validateSyntheticId(value.interaction_id, "INTERACTION");
    if (value.page_identity !== null) validateAnySyntheticId(value.page_identity);
    if (value.scenario_alias !== null) {
      validateAlias(value.scenario_alias, "SUMMARY_SCENARIO_INVALID");
    }
    if (value.page_kind === "order-detail") {
      if (
        value.order_id === null || value.page_identity !== value.order_id ||
        value.interaction_id !== null || value.scenario_alias === null ||
        !RULE_PACKS.includes(value.rule_pack) ||
        value.completeness_state === null ||
        !value.can_evaluate && value.source_fingerprint !== null ||
        value.can_evaluate && (
          value.completeness_state !== "COMPLETE" || value.source_fingerprint === null
        )
      ) contractError("ORDER_SUMMARY_BINDING_INVALID");
    } else if (value.page_kind === "interaction-detail") {
      if (
        value.interaction_id === null || value.page_identity !== value.interaction_id ||
        value.order_id === null || value.scenario_alias !== null ||
        value.rule_pack !== null ||
        value.completeness_state !== null || value.source_fingerprint !== null ||
        value.can_evaluate
      ) contractError("INTERACTION_SUMMARY_BINDING_INVALID");
    } else if (
      value.page_identity !== null || value.order_id !== null ||
      value.interaction_id !== null || value.scenario_alias !== null ||
      value.rule_pack !== null ||
      value.completeness_state !== null || value.source_fingerprint !== null ||
      value.can_evaluate
    ) contractError("UNSUPPORTED_SUMMARY_BINDING_INVALID");
    if (value.evaluation !== null) {
      validateProjectedEvaluation(value.evaluation);
      if (
        value.page_kind !== "order-detail" || !value.can_evaluate ||
        value.backend === null || !value.backend.healthy ||
        value.order_id !== value.evaluation.order_id ||
        value.scenario_alias !== value.evaluation.scenario_alias ||
        value.rule_pack !== value.evaluation.rule_pack
      ) contractError("SUMMARY_EVALUATION_BINDING_INVALID");
    }
    return value;
  }

  function panelStateForResult(result) {
    if (result.replayed === true) return "EXACT_REPLAY";
    if (result.conflict === true) return "REQUEST_CONFLICT";
    if (result.rule_pack === "SALES_CREDIT") return "SALES_CREDIT_RESULT";
    const doiStates = new Set(["DOI_OPPORTUNITY", "DOI_MANUAL_REVIEW", "DOI_EXCLUDED", "DOI_MONITOR"]);
    return doiStates.has(result.top_level_result) ? result.top_level_result : "SAFE_ERROR";
  }

  function response(panelState, data = null, errorCode = null) {
    if (!PANEL_STATES.includes(panelState)) contractError("PANEL_STATE_INVALID");
    const value = {
      data,
      error_code: errorCode === null ? null : validateSafeCode(errorCode),
      panel_state: panelState,
      schema_version: MESSAGE_SCHEMA_VERSION
    };
    validateResponse(value);
    return Object.freeze(value);
  }

  function validateResponse(value) {
    const canonical = globalThis.SSA.Canonical;
    canonical.canonicalStringify(value);
    canonical.exactMembers(value, RESPONSE_MEMBERS, "RESPONSE_MEMBERS_INVALID");
    if (
      value.schema_version !== MESSAGE_SCHEMA_VERSION ||
      !PANEL_STATES.includes(value.panel_state) ||
      value.error_code !== null && validateSafeCode(value.error_code, null) !== value.error_code
    ) contractError("RESPONSE_CONTRACT_INVALID");
    if (value.data !== null) validateSummary(value.data);
    const resultStates = new Set([
      "SALES_CREDIT_RESULT", "DOI_OPPORTUNITY", "DOI_MANUAL_REVIEW", "DOI_EXCLUDED",
      "DOI_MONITOR", "EXACT_REPLAY"
    ]);
    if (resultStates.has(value.panel_state)) {
      if (
        value.data === null || value.data.evaluation === null ||
        panelStateForResult(value.data.evaluation) !== value.panel_state ||
        value.error_code !== null
      ) contractError("RESPONSE_RESULT_BINDING_INVALID");
    } else if (value.data !== null && value.data.evaluation !== null) {
      contractError("RESPONSE_UNEXPECTED_EVALUATION");
    }
    const data = value.data;
    const backend = data === null ? null : data.backend;
    if (value.panel_state === "SUPPORTED_READY") {
      if (
        data === null || backend === null || !backend.healthy || value.error_code !== null ||
        data.page_kind === "order-detail" && !data.can_evaluate ||
        data.page_kind === "interaction-detail" && data.can_evaluate ||
        !["order-detail", "interaction-detail"].includes(data.page_kind)
      ) contractError("RESPONSE_READY_BINDING_INVALID");
    } else if (value.panel_state === "UNSUPPORTED_PAGE") {
      if (
        data === null && value.error_code === null ||
        data !== null && (
          data.page_kind !== "unsupported" || data.can_evaluate ||
          backend !== null || value.error_code !== null
        )
      ) contractError("RESPONSE_UNSUPPORTED_BINDING_INVALID");
    } else if (value.panel_state === "BACKEND_UNHEALTHY") {
      if (value.error_code === null || backend !== null && backend.healthy) {
        contractError("RESPONSE_UNHEALTHY_BINDING_INVALID");
      }
    } else if (value.panel_state === "BACKEND_OFFLINE") {
      if (value.error_code === null || backend !== null) {
        contractError("RESPONSE_OFFLINE_BINDING_INVALID");
      }
    } else if (value.panel_state === "REQUEST_CONFLICT") {
      if (
        value.error_code !== "IDEMPOTENCY_KEY_MATERIAL_CONFLICT" ||
        data === null || data.page_kind !== "order-detail" || !data.can_evaluate ||
        backend === null || !backend.healthy
      ) contractError("RESPONSE_CONFLICT_BINDING_INVALID");
    } else if (["INCOMPLETE_PAGE", "MALFORMED_PAGE"].includes(value.panel_state)) {
      const expectedCompleteness = value.panel_state === "INCOMPLETE_PAGE"
        ? "INCOMPLETE"
        : "MALFORMED";
      if (
        (data === null && value.error_code === null) ||
        (data !== null && (
          data.can_evaluate || backend !== null ||
          data.completeness_state !== expectedCompleteness
        ))
      ) {
        contractError("RESPONSE_SOURCE_FAILURE_BINDING_INVALID");
      }
    } else if (["DOM_PAYLOAD_MISMATCH", "SAFE_ERROR"].includes(value.panel_state)) {
      if (value.error_code === null) contractError("RESPONSE_ERROR_CODE_REQUIRED");
    } else if (value.panel_state === "EVALUATING") {
      contractError("RESPONSE_EVALUATING_PROHIBITED");
    }
    return value;
  }

  const root = globalThis.SSA || (globalThis.SSA = {});
  root.Contracts = Object.freeze({
    API_REQUEST_SCHEMA_VERSION,
    API_SCHEMA_VERSION,
    APPLICATION_SCHEMA_VERSION,
    DOM_SCHEMA_VERSION,
    EXTENSION_VERSION,
    EXTRACTION_ALLOWLIST,
    EXTRACTION_SCHEMA_VERSION,
    LINE_MANIFEST_DOMAIN,
    LINE_MANIFEST_SCHEMA_VERSION,
    MESSAGE_SCHEMA_VERSION,
    ORDER_BINDING_SCHEMA_VERSION,
    PANEL_STATES,
    SAFETY_COUNTER_NAMES,
    SERVICE_PORT,
    contractError,
    panelStateForResult,
    response,
    isDoiReason,
    validateAlias,
    validateAnySyntheticId,
    validateMessage,
    validateNoRedirectResponse,
    validateRequestKey,
    validateResponse,
    validateSafeCode,
    validateSyntheticId,
    validateToken
  });
})();
