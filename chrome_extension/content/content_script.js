/* SYNTHETIC-SALES-ASSIST-AUTHORED-M6 */
"use strict";

(() => {
  const canonical = globalThis.SSA.Canonical;
  const contracts = globalThis.SSA.Contracts;
  const extractionModule = globalThis.SSA.Extraction;
  const originPolicy = globalThis.SSA.Origin;
  const HEALTH_TIMEOUT_MS = 4000;
  const HANDSHAKE_TIMEOUT_MS = 4000;
  const EVALUATION_TIMEOUT_MS = 10000;
  const API_ENVELOPE_MEMBERS = Object.freeze(["data", "schema_version"]);
  const ERROR_ENVELOPE_MEMBERS = Object.freeze(["error", "schema_version"]);
  const ERROR_MEMBERS = Object.freeze(["code", "message"]);
  const HEALTH_MEMBERS = Object.freeze([
    "app_version", "build_version", "database_schema_version", "database_status",
    "evaluated_count", "expected_schema_version", "integrity_check", "migration_status",
    "projection_status", "quick_check", "registry_capacity", "registry_count",
    "safety_counters", "schema_version", "status"
  ]);
  const HANDSHAKE_MEMBERS = Object.freeze([
    "expected_extension_version", "last_seen_at", "observed_extension_version",
    "stale_after_seconds", "status"
  ]);
  const EVALUATION_MEMBERS = Object.freeze([
    "aggregate_potential_status", "aggregate_potential_value", "case_id", "closure_state",
    "command_id", "conflict", "evaluation_id", "explanation", "fired_rules",
    "handling_flags", "human_review_required", "opportunities", "order_id",
    "processing_duration_ns", "processing_stages", "reasons", "replayed", "rule_pack",
    "rule_pack_version", "run_id", "scenario_alias", "schema_version", "snapshot_id",
    "top_level_result", "value", "value_status", "workflow_state"
  ]);
  const OPPORTUNITY_MEMBERS = Object.freeze(["line_ids", "opportunity_type", "potential_value"]);
  const MONEY_MEMBERS = Object.freeze(["amount", "currency_code", "currency_registry_version", "currency_scale"]);
  const EXPLANATION_MEMBERS = Object.freeze([
    "normalized_facts", "precedence_decision", "reason_ownership", "rules_evaluated",
    "supplied_facts", "unavailable_facts"
  ]);
  const PROCESSING_STAGE_MEMBERS = Object.freeze(["duration_ns", "stage", "status"]);
  const CURRENCY_SCALES = Object.freeze({EUR: 2, JPY: 0, KWD: 3, USD: 2});
  const TOKEN = /^[A-Z][A-Z0-9_.:/-]{0,255}(?![\s\S])/;
  const ALIAS = /^[a-z][a-z0-9-]{0,62}[a-z0-9](?![\s\S])/;
  const EVALUATION_PATH =
    /^\/api\/v1\/orders\/(SYN-ORDER-[A-Z0-9]+(?:-[A-Z0-9]+)*)\/evaluate(?![\s\S])/;
  const HANDSHAKE_PATH = "/api/v1/system/extension/handshake";
  const CONTENT_LENGTH = /^(?:0|[1-9][0-9]*)(?![\s\S])/;
  const INTEGER_AMOUNT = /^-?(?:0|[1-9][0-9]*)(?![\s\S])/;
  const NEGATIVE_ZERO = /^-0(?:\.0+)?(?![\s\S])/;
  const DOI_REASON = /^RC-([0-9]{3})(?![\s\S])/;
  const LOWER_SHA256 = /^[0-9a-f]{64}(?![\s\S])/;
  const SALES_CREDIT_RESULTS = Object.freeze([
    "AWAITING_SOURCE_REVIEW", "CHECKED_NO_ORDER_WINDOW_ACTIVE", "REVIEW_WINDOW_CLOSED_NO_ORDER",
    "CREDIT_CONFIRMED_TARGET_REP", "EVIDENCE_NEEDED", "VERIFIED_PREORDER_EVIDENCE",
    "OUTBOUND_EVIDENCE_HUMAN_REVIEW", "INBOUND_EVIDENCE_HUMAN_REVIEW",
    "TIMING_UNCERTAIN_HUMAN_REVIEW", "OTHER_REP_HUMAN_REVIEW", "ORDER_CHANGED_HUMAN_REVIEW",
    "CANCELED_REPLACEMENT_WINDOW_ACTIVE", "POSSIBLE_REPLACEMENT_HUMAN_REVIEW",
    "CANCELED_NO_REPLACEMENT", "MANUAL_REVIEW_REQUIRED", "CLOSED"
  ]);
  const SALES_CREDIT_HUMAN_REVIEW_WORKFLOWS = Object.freeze([
    "INBOUND_EVIDENCE_HUMAN_REVIEW", "MANUAL_REVIEW_REQUIRED",
    "ORDER_CHANGED_HUMAN_REVIEW", "OTHER_REP_HUMAN_REVIEW",
    "OUTBOUND_EVIDENCE_HUMAN_REVIEW", "POSSIBLE_REPLACEMENT_HUMAN_REVIEW",
    "TIMING_UNCERTAIN_HUMAN_REVIEW"
  ]);
  const DOI_RESULTS = Object.freeze(["DOI_OPPORTUNITY", "DOI_MANUAL_REVIEW", "DOI_EXCLUDED", "DOI_MONITOR"]);
  const DOI_WORKFLOW_STATES = Object.freeze(["ACTIVE", "CLOSED_HARD", "CLOSED_REVERSIBLE"]);
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

  function safeCode(error, fallback = "SAFE_ERROR") {
    return contracts.validateSafeCode(error && error.code, fallback);
  }

  function transportError(code) {
    const error = new Error(code);
    error.code = code;
    error.transport = true;
    return error;
  }

  function backendHealthFailureState(error) {
    return error && ["BACKEND_OFFLINE", "REQUEST_TIMEOUT"].includes(error.code)
      ? "BACKEND_OFFLINE"
      : "BACKEND_UNHEALTHY";
  }

  function validateErrorEnvelope(error) {
    canonical.exactMembers(error, ERROR_MEMBERS, "ERROR_ENVELOPE_INVALID");
    if (
      contracts.validateSafeCode(error.code, null) !== error.code ||
      typeof error.message !== "string" || error.message.length === 0 ||
      error.message.length > 512 || /[\u0000-\u001f\u007f]/.test(error.message)
    ) contracts.contractError("ERROR_ENVELOPE_INVALID");
  }

  function closedRequestUrl(origin, path) {
    const normalizedOrigin = originPolicy.normalizeServiceOrigin(`${origin}/`);
    if (path !== "/health" && path !== HANDSHAKE_PATH) {
      const match = EVALUATION_PATH.exec(path);
      if (match === null) contracts.contractError("REQUEST_PATH_INVALID");
      contracts.validateSyntheticId(match[1], "ORDER");
    }
    const requestUrl = `${normalizedOrigin}${path}`;
    const parsed = new URL(requestUrl);
    const parsedPath = `${parsed.pathname}${parsed.search}${parsed.hash}`;
    if (parsed.origin !== normalizedOrigin || parsedPath !== path) {
      contracts.contractError("REQUEST_URL_INVALID");
    }
    return requestUrl;
  }

  async function rejectResponseBody(reader, controller, code) {
    controller.abort();
    try {
      await reader.cancel(code);
    } catch (_error) {
      // The abort may close the reader before cancellation settles.
    }
    contracts.contractError(code);
  }

  async function readBoundedResponseText(response, controller) {
    const contentLength = response.headers.get("Content-Length");
    if (response.body === null || typeof response.body.getReader !== "function") {
      contracts.contractError("RESPONSE_BODY_STREAM_REQUIRED");
    }
    const reader = response.body.getReader();
    if (contentLength !== null) {
      const declared = Number(contentLength);
      if (
        !CONTENT_LENGTH.test(contentLength) ||
        !Number.isSafeInteger(declared) || declared > canonical.MAX_DOCUMENT_BYTES
      ) await rejectResponseBody(reader, controller, "RESPONSE_BODY_TOO_LARGE");
    }
    const decoder = new TextDecoder("utf-8", {fatal: true});
    const chunks = [];
    let total = 0;
    while (true) {
      const item = await reader.read();
      if (item.done) break;
      if (!(item.value instanceof Uint8Array)) {
        await rejectResponseBody(reader, controller, "RESPONSE_BODY_STREAM_INVALID");
      }
      total += item.value.byteLength;
      if (total > canonical.MAX_DOCUMENT_BYTES) {
        await rejectResponseBody(reader, controller, "RESPONSE_BODY_TOO_LARGE");
      }
      try {
        chunks.push(decoder.decode(item.value, {stream: true}));
      } catch (_error) {
        await rejectResponseBody(reader, controller, "RESPONSE_BODY_ENCODING_INVALID");
      }
    }
    try {
      chunks.push(decoder.decode());
    } catch (_error) {
      contracts.contractError("RESPONSE_BODY_ENCODING_INVALID");
    }
    return chunks.join("");
  }

  async function fetchClosedJson(origin, path, options, timeoutMs) {
    const requestUrl = closedRequestUrl(origin, path);
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);
    let response;
    try {
      response = await fetch(requestUrl, {
        ...options,
        cache: "no-store",
        credentials: "omit",
        redirect: "manual",
        referrerPolicy: "no-referrer",
        signal: controller.signal
      });
      contracts.validateNoRedirectResponse(response);
      if (response.headers.get("content-type") !== "application/json; charset=utf-8") {
        throw transportError("RESPONSE_MEDIA_TYPE_INVALID");
      }
      const text = await readBoundedResponseText(response, controller);
      const expected = response.ok || path === "/health" ? API_ENVELOPE_MEMBERS : ERROR_ENVELOPE_MEMBERS;
      const envelope = canonical.parseCanonicalJson(text, expected);
      if (envelope.schema_version !== contracts.API_SCHEMA_VERSION) {
        contracts.contractError("API_SCHEMA_VERSION_UNSUPPORTED");
      }
      if (!response.ok && path !== "/health") {
        validateErrorEnvelope(envelope.error);
      }
      return Object.freeze({envelope, status: response.status});
    } catch (error) {
      if (error && error.name === "AbortError") {
        throw transportError("REQUEST_TIMEOUT");
      }
      if (error instanceof TypeError) throw transportError("BACKEND_OFFLINE");
      throw error;
    } finally {
      clearTimeout(timeout);
    }
  }

  function validateHealth(data, status) {
    canonical.exactMembers(data, HEALTH_MEMBERS, "HEALTH_MEMBERS_INVALID");
    if (
      data.schema_version !== contracts.APPLICATION_SCHEMA_VERSION ||
      data.app_version !== "0.1.0" ||
      data.build_version !== "synthetic-sales-assist-m5/v1" ||
      data.database_schema_version !== 4 || data.expected_schema_version !== 4 ||
      !["PASS", "FAIL"].includes(data.status) ||
      !["PASS", "FAIL"].includes(data.database_status) ||
      !["CURRENT", "UNSUPPORTED"].includes(data.migration_status) ||
      !["PASS", "FAIL"].includes(data.projection_status) ||
      data.quick_check !== "ok" || data.integrity_check !== "not_run" ||
      !Number.isSafeInteger(data.evaluated_count) || data.evaluated_count < 0 ||
      !Number.isSafeInteger(data.registry_count) || data.registry_count < 0 ||
      !Number.isSafeInteger(data.registry_capacity) || data.registry_capacity < 1 ||
      data.registry_capacity > 256 || data.evaluated_count > data.registry_count ||
      data.registry_count > data.registry_capacity
    ) contracts.contractError("HEALTH_CONTRACT_INVALID");
    canonical.exactMembers(data.safety_counters, contracts.SAFETY_COUNTER_NAMES, "SAFETY_COUNTERS_INVALID");
    if (!contracts.SAFETY_COUNTER_NAMES.every((name) => (
      Number.isSafeInteger(data.safety_counters[name]) && data.safety_counters[name] >= 0
    ))) contracts.contractError("SAFETY_COUNTER_VALUES_INVALID");
    const safetyZero = contracts.SAFETY_COUNTER_NAMES.every((name) => data.safety_counters[name] === 0);
    const healthy =
      status === 200 && data.status === "PASS" && data.database_status === "PASS" &&
      data.migration_status === "CURRENT" && data.projection_status === "PASS" && safetyZero;
    return Object.freeze({
      app_version: data.app_version,
      build_version: data.build_version,
      database_schema_version: data.database_schema_version,
      healthy,
      safety_counters_zero: safetyZero,
      status: healthy ? "PASS" : "FAIL"
    });
  }

  async function backendHealth(origin) {
    const result = await fetchClosedJson(origin, "/health", {method: "GET"}, HEALTH_TIMEOUT_MS);
    return validateHealth(result.envelope.data, result.status);
  }

  function localCsrfHeaders() {
    const metas = document.querySelectorAll('meta[name="ssa-csrf-token"]');
    if (metas.length !== 1 || !LOWER_SHA256.test(metas[0].content)) {
      contracts.contractError("CSRF_TOKEN_UNAVAILABLE");
    }
    return Object.freeze({
      "Content-Type": "application/json",
      "X-SSA-CSRF-Token": metas[0].content
    });
  }

  function validateHandshake(data, status) {
    canonical.exactMembers(data, HANDSHAKE_MEMBERS, "HANDSHAKE_MEMBERS_INVALID");
    if (
      status !== 200 ||
      !["LAST_SEEN_HEALTHY", "VERSION_MISMATCH"].includes(data.status) ||
      data.expected_extension_version !== contracts.EXTENSION_VERSION ||
      data.observed_extension_version !== contracts.EXTENSION_VERSION ||
      data.stale_after_seconds !== 300
    ) contracts.contractError("HANDSHAKE_CONTRACT_INVALID");
    extractionModule.validateTimestamp(data.last_seen_at, "HANDSHAKE_TIMESTAMP_INVALID");
    return data;
  }

  async function extensionHandshake(origin) {
    const body = canonical.canonicalStringify({
      extension_version: contracts.EXTENSION_VERSION,
      schema_version: contracts.HANDSHAKE_SCHEMA_VERSION
    });
    const result = await fetchClosedJson(
      origin,
      HANDSHAKE_PATH,
      {body, headers: localCsrfHeaders(), method: "POST"},
      HANDSHAKE_TIMEOUT_MS
    );
    return validateHandshake(result.envelope.data, result.status);
  }

  function validateMoney(value, code) {
    if (value === null) return null;
    canonical.exactMembers(value, MONEY_MEMBERS, code);
    if (typeof value.currency_code !== "string") contracts.contractError(code);
    const scale = CURRENCY_SCALES[value.currency_code];
    const amountPattern = scale === 0
      ? INTEGER_AMOUNT
      : new RegExp(`^-?(?:0|[1-9][0-9]*)\\.[0-9]{${scale}}(?![\\s\\S])`);
    if (
      scale === undefined || typeof value.amount !== "string" || !amountPattern.test(value.amount) ||
      value.currency_registry_version !== "synthetic-iso-style-currency-registry/v1" ||
      value.currency_scale !== scale || NEGATIVE_ZERO.test(value.amount)
    ) contracts.contractError(code);
    return value;
  }

  function validateToken(value, code) {
    if (typeof value !== "string" || !TOKEN.test(value)) contracts.contractError(code);
    return value;
  }

  function validateStringList(value, code, tokens = false) {
    if (!Array.isArray(value) || !value.every((item) => (
      typeof item === "string" && item.length > 0 && item.length <= 4096 && (!tokens || TOKEN.test(item))
    ))) contracts.contractError(code);
    return value;
  }

  function validateExactList(value, allowed, code) {
    if (
      !Array.isArray(value) || !value.every((item) => allowed.includes(item)) ||
      new Set(value).size !== value.length
    ) contracts.contractError(code);
    return value;
  }

  function isDoiReason(value) {
    if (typeof value !== "string") return false;
    const match = DOI_REASON.exec(value);
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

  function salesCreditDisplayIsCoherent(data) {
    const canceled = data.reasons.includes("CANCELED_ORDER_ZERO_ACTIVE_VALUE");
    const valueMatchesStatus = data.value_status === "PLACED_VALUE_VERIFIED"
      ? data.value !== null && data.aggregate_potential_value !== null &&
        sameMoneyDefinition(data.value, data.aggregate_potential_value) &&
        (canceled
          ? /^0(?:\.0+)?(?![\s\S])/.test(data.value.amount)
          : canonical.canonicalStringify(data.value) ===
            canonical.canonicalStringify(data.aggregate_potential_value))
      : data.value_status === "CHANGED_REVIEW"
        ? canonical.canonicalStringify(data.value) ===
          canonical.canonicalStringify(data.aggregate_potential_value)
        : data.value === null && data.aggregate_potential_value === null;
    const flags = new Set(data.handling_flags);
    const expectedHumanReview = SALES_CREDIT_HUMAN_REVIEW_WORKFLOWS.includes(
      data.workflow_state
    );
    return (
      valueMatchesStatus && data.human_review_required === expectedHumanReview &&
      (data.closure_state === "CANCELED") === canceled &&
      flags.has("NO_PERSISTENCE_MILESTONE_2") &&
      flags.has("HUMAN_REVIEW_REQUIRED") === data.human_review_required &&
      flags.has("ACTIVE_CASE_CLASSIFICATION") === !data.human_review_required &&
      flags.has("ZERO_ACTIVE_VALUE") === canceled
    );
  }

  function doiDisplayIsCoherent(data) {
    const expectedWorkflow = data.closure_state === "NONE"
      ? "ACTIVE"
      : ["SHIPPED", "CANCELED"].includes(data.closure_state)
        ? "CLOSED_HARD"
        : "CLOSED_REVERSIBLE";
    const isOpportunity = data.top_level_result === "DOI_OPPORTUNITY";
    return (
      (isOpportunity || (
        data.value_status === "UNAVAILABLE" && data.value === null &&
        data.aggregate_potential_value === null
      )) &&
      data.workflow_state === expectedWorkflow &&
      (data.closure_state === "NONE" || data.top_level_result === "DOI_EXCLUDED") &&
      (data.top_level_result !== "DOI_MANUAL_REVIEW" || data.human_review_required)
    );
  }

  function validateEvaluationSemantics(data) {
    if (data.rule_pack === "SALES_CREDIT") {
      if (
        !SALES_CREDIT_VALUE_STATUSES.includes(data.value_status) ||
        data.aggregate_potential_status !== data.value_status ||
        !SALES_CREDIT_CLOSURES.includes(data.closure_state) ||
        data.opportunities.length !== 0 || !salesCreditDisplayIsCoherent(data)
      ) contracts.contractError("SALES_CREDIT_RESULT_SEMANTICS_INVALID");
      validateExactList(data.reasons, SALES_CREDIT_REASONS, "SALES_CREDIT_REASONS_INVALID");
      validateExactList(
        data.handling_flags,
        SALES_CREDIT_EFFECTS,
        "SALES_CREDIT_EFFECTS_INVALID"
      );
      return;
    }
    const valueAvailable = data.value_status === "AVAILABLE";
    if (
      !DOI_VALUE_STATUSES.includes(data.value_status) ||
      data.aggregate_potential_status !== data.value_status ||
      !DOI_CLOSURES.includes(data.closure_state) ||
      (data.value !== null) !== valueAvailable ||
      (data.aggregate_potential_value !== null) !== valueAvailable ||
      canonical.canonicalStringify(data.value) !==
        canonical.canonicalStringify(data.aggregate_potential_value) ||
      (data.top_level_result === "DOI_OPPORTUNITY") !== (data.opportunities.length > 0) ||
      !doiDisplayIsCoherent(data) ||
      !data.reasons.every(isDoiReason) || new Set(data.reasons).size !== data.reasons.length
    ) contracts.contractError("DOI_RESULT_SEMANTICS_INVALID");
    validateExactList(data.handling_flags, DOI_HANDLING_FLAGS, "DOI_HANDLING_FLAGS_INVALID");
    if (!data.opportunities.every((item) => DOI_OPPORTUNITY_TYPES.includes(item.opportunity_type))) {
      contracts.contractError("DOI_OPPORTUNITY_TYPE_INVALID");
    }
  }

  function validateEvaluation(
    data,
    expectedOrderId,
    expectedScenarioAlias,
    expectedRulePack,
    lineUniverse
  ) {
    canonical.exactMembers(data, EVALUATION_MEMBERS, "EVALUATION_MEMBERS_INVALID");
    if (
      data.schema_version !== contracts.APPLICATION_SCHEMA_VERSION ||
      data.order_id !== expectedOrderId ||
      data.scenario_alias !== expectedScenarioAlias || !ALIAS.test(data.scenario_alias) ||
      data.rule_pack !== expectedRulePack ||
      typeof data.rule_pack_version !== "string" || typeof data.human_review_required !== "boolean" ||
      typeof data.replayed !== "boolean" || data.conflict !== false ||
      !Number.isSafeInteger(data.processing_duration_ns) || data.processing_duration_ns < 0 ||
      !Array.isArray(data.opportunities)
    ) contracts.contractError("EVALUATION_CONTRACT_INVALID");
    contracts.validateSyntheticId(data.order_id, "ORDER");
    for (const member of ["aggregate_potential_status", "top_level_result", "value_status", "workflow_state"]) {
      validateToken(data[member], "EVALUATION_STATE_INVALID");
    }
    if (data.closure_state !== null) validateToken(data.closure_state, "EVALUATION_CLOSURE_INVALID");
    validateStringList(data.reasons, "EVALUATION_REASONS_INVALID", true);
    validateStringList(data.fired_rules, "EVALUATION_RULES_INVALID", true);
    validateStringList(data.handling_flags, "EVALUATION_FLAGS_INVALID", true);
    const expectedVersion = data.rule_pack === "SALES_CREDIT"
      ? "synthetic-sales-credit-rules/v1"
      : "synthetic-doi-rule-pack/v1";
    const allowedResults = data.rule_pack === "SALES_CREDIT" ? SALES_CREDIT_RESULTS : DOI_RESULTS;
    if (data.rule_pack_version !== expectedVersion || !allowedResults.includes(data.top_level_result)) {
      contracts.contractError("EVALUATION_RESULT_PARTITION_INVALID");
    }
    if (
      data.rule_pack === "SALES_CREDIT" && data.workflow_state !== data.top_level_result ||
      data.rule_pack === "DOI" && !DOI_WORKFLOW_STATES.includes(data.workflow_state)
    ) contracts.contractError("EVALUATION_WORKFLOW_PARTITION_INVALID");
    canonical.exactMembers(data.explanation, EXPLANATION_MEMBERS, "EXPLANATION_MEMBERS_INVALID");
    for (const member of ["normalized_facts", "reason_ownership", "rules_evaluated", "supplied_facts", "unavailable_facts"]) {
      validateStringList(data.explanation[member], "EXPLANATION_LIST_INVALID");
    }
    if (typeof data.explanation.precedence_decision !== "string" || !data.explanation.precedence_decision) {
      contracts.contractError("EXPLANATION_PRECEDENCE_INVALID");
    }
    if (!Array.isArray(data.processing_stages)) contracts.contractError("PROCESSING_STAGES_INVALID");
    for (const stage of data.processing_stages) {
      canonical.exactMembers(stage, PROCESSING_STAGE_MEMBERS, "PROCESSING_STAGE_MEMBERS_INVALID");
      validateToken(stage.stage, "PROCESSING_STAGE_INVALID");
      validateToken(stage.status, "PROCESSING_STAGE_STATUS_INVALID");
      if (!Number.isSafeInteger(stage.duration_ns) || stage.duration_ns < 0) {
        contracts.contractError("PROCESSING_STAGE_DURATION_INVALID");
      }
    }
    validateMoney(data.value, "EVALUATION_VALUE_INVALID");
    validateMoney(data.aggregate_potential_value, "EVALUATION_AGGREGATE_VALUE_INVALID");
    if (data.command_id === null || data.evaluation_id === null || data.snapshot_id === null) {
      contracts.contractError("EVALUATION_PERSISTED_IDS_REQUIRED");
    }
    contracts.validateSyntheticId(data.command_id, "EVIDENCE");
    contracts.validateSyntheticId(data.evaluation_id, "EVALUATION");
    if (data.run_id !== null) contracts.validateSyntheticId(data.run_id, "RUN");
    contracts.validateSyntheticId(data.snapshot_id, "SNAPSHOT");
    if (data.rule_pack === "SALES_CREDIT") {
      if (data.case_id !== expectedOrderId) contracts.contractError("SALES_CREDIT_CASE_BINDING_INVALID");
    } else if (data.case_id === null || data.run_id === null) {
      contracts.contractError("DOI_PERSISTED_IDS_REQUIRED");
    } else {
      contracts.validateSyntheticId(data.case_id, "EVIDENCE");
    }
    for (const item of data.opportunities) {
      canonical.exactMembers(item, OPPORTUNITY_MEMBERS, "OPPORTUNITY_MEMBERS_INVALID");
      if (
        !Array.isArray(item.line_ids) || item.line_ids.length === 0 ||
        !item.line_ids.every((lineId) => {
        try { contracts.validateSyntheticId(lineId, "EVIDENCE"); return true; } catch (_error) { return false; }
        }) || !item.line_ids.every((lineId) => lineUniverse.has(lineId))
      ) {
        contracts.contractError("OPPORTUNITY_LINE_IDS_INVALID");
      }
      if (new Set(item.line_ids).size !== item.line_ids.length) {
        contracts.contractError("OPPORTUNITY_LINE_IDS_DUPLICATE");
      }
      validateToken(item.opportunity_type, "OPPORTUNITY_TYPE_INVALID");
      validateMoney(item.potential_value, "OPPORTUNITY_VALUE_INVALID");
    }
    validateEvaluationSemantics(data);
    return data;
  }

  function projectEvaluation(data) {
    return Object.freeze({
      aggregate_potential_status: data.aggregate_potential_status,
      aggregate_potential_value: data.aggregate_potential_value,
      case_id: data.case_id,
      closure_state: data.closure_state,
      command_id: data.command_id,
      conflict: data.conflict,
      evaluation_id: data.evaluation_id,
      handling_flags: data.handling_flags,
      human_review_required: data.human_review_required,
      opportunities: data.opportunities,
      order_id: data.order_id,
      processing_duration_ns: data.processing_duration_ns,
      reasons: data.reasons,
      replayed: data.replayed,
      rule_pack: data.rule_pack,
      rule_pack_version: data.rule_pack_version,
      run_id: data.run_id,
      scenario_alias: data.scenario_alias,
      snapshot_id: data.snapshot_id,
      top_level_result: data.top_level_result,
      value: data.value,
      value_status: data.value_status,
      workflow_state: data.workflow_state
    });
  }

  function withBackend(summary, backend) {
    return Object.freeze({...summary, backend});
  }

  function withEvaluation(summary, backend, evaluation) {
    return Object.freeze({...summary, backend, evaluation});
  }

  async function currentExtraction() {
    return extractionModule.extractPage(document, globalThis.location.href);
  }

  function sourceChanged(observer, mutationState, initialHref) {
    if (observer.takeRecords().length > 0) mutationState.changed = true;
    return mutationState.changed || globalThis.location.href !== initialHref;
  }

  async function pageState() {
    let extraction;
    try {
      extraction = await currentExtraction();
    } catch (error) {
      return contracts.response(error.panelState || "SAFE_ERROR", null, safeCode(error, "EXTRACTION_FAILED_CLOSED"));
    }
    if (!["SUPPORTED_READY"].includes(extraction.panel_state)) {
      return contracts.response(
        extraction.panel_state,
        extractionModule.panelSummary(extraction),
        null
      );
    }
    let sourceFingerprint = null;
    if (extraction.can_evaluate) {
      try {
        sourceFingerprint = await canonical.sha256Hex(canonical.canonicalStringify(extraction));
      } catch (_error) {
        return contracts.response("DOM_PAYLOAD_MISMATCH", null, "SOURCE_FINGERPRINT_INVALID");
      }
    }
    const summary = extractionModule.panelSummary(extraction, sourceFingerprint);
    try {
      const backend = await backendHealth(extraction.origin);
      if (!backend.healthy) return contracts.response("BACKEND_UNHEALTHY", withBackend(summary, backend), "BACKEND_UNHEALTHY");
      try {
        await extensionHandshake(extraction.origin);
      } catch (_error) {
        // Status registration is maintenance-only; evaluation readiness remains health-derived.
      }
      return contracts.response("SUPPORTED_READY", withBackend(summary, backend), null);
    } catch (error) {
      const state = backendHealthFailureState(error);
      return contracts.response(state, summary, safeCode(error, state));
    }
  }

  async function evaluateObserved(message, observer, mutationState, initialHref) {
    let extraction;
    try {
      extraction = await currentExtraction();
    } catch (error) {
      return contracts.response(error.panelState || "SAFE_ERROR", null, safeCode(error, "EXTRACTION_FAILED_CLOSED"));
    }
    let summary = extractionModule.panelSummary(extraction);
    if (extraction.panel_state !== "SUPPORTED_READY" || !extraction.can_evaluate || extraction.order === null) {
      const state = extraction.panel_state === "SUPPORTED_READY" ? "UNSUPPORTED_PAGE" : extraction.panel_state;
      const data = state === "UNSUPPORTED_PAGE" ? null : summary;
      return contracts.response(state, data, "EVALUATION_PAGE_NOT_READY");
    }
    let extractionMaterial;
    let sourceFingerprint;
    try {
      extractionMaterial = canonical.canonicalStringify(extraction);
      sourceFingerprint = await canonical.sha256Hex(extractionMaterial);
    } catch (_error) {
      return contracts.response("DOM_PAYLOAD_MISMATCH", null, "EXTRACTION_FINGERPRINT_INVALID");
    }
    summary = extractionModule.panelSummary(extraction, sourceFingerprint);
    if (sourceChanged(observer, mutationState, initialHref)) {
      return contracts.response("DOM_PAYLOAD_MISMATCH", summary, "PAGE_CHANGED_DURING_EXTRACTION");
    }
    if (
      message.expected_origin !== extraction.origin ||
      message.expected_order_id !== extraction.order.order_id ||
      message.expected_order_id !== extraction.page_identity ||
      message.expected_source_fingerprint !== sourceFingerprint
    ) {
      return contracts.response(
        "DOM_PAYLOAD_MISMATCH",
        summary,
        "ACTIVE_PAGE_BINDING_MISMATCH"
      );
    }
    let backend;
    try {
      backend = await backendHealth(extraction.origin);
    } catch (error) {
      const state = backendHealthFailureState(error);
      return contracts.response(state, summary, safeCode(error, state));
    }
    if (!backend.healthy) return contracts.response("BACKEND_UNHEALTHY", withBackend(summary, backend), "BACKEND_UNHEALTHY");
    if (sourceChanged(observer, mutationState, initialHref)) {
      return contracts.response(
        "DOM_PAYLOAD_MISMATCH",
        withBackend(summary, backend),
        "PAGE_CHANGED_DURING_HEALTH"
      );
    }
    let verifiedExtraction;
    try {
      verifiedExtraction = await currentExtraction();
    } catch (error) {
      const state = error.panelState === "UNSUPPORTED_PAGE"
        ? "UNSUPPORTED_PAGE"
        : "DOM_PAYLOAD_MISMATCH";
      const data = state === "UNSUPPORTED_PAGE" ? null : withBackend(summary, backend);
      return contracts.response(state, data, "PAGE_RECHECK_FAILED_CLOSED");
    }
    let verifiedMaterial;
    try {
      verifiedMaterial = canonical.canonicalStringify(verifiedExtraction);
    } catch (_error) {
      return contracts.response(
        "DOM_PAYLOAD_MISMATCH",
        withBackend(summary, backend),
        "EXTRACTION_RECHECK_FINGERPRINT_INVALID"
      );
    }
    if (
      sourceChanged(observer, mutationState, initialHref) ||
      verifiedExtraction.panel_state !== "SUPPORTED_READY" ||
      !verifiedExtraction.can_evaluate || verifiedExtraction.order === null ||
      verifiedMaterial !== extractionMaterial
    ) {
      const state = verifiedExtraction.panel_state === "UNSUPPORTED_PAGE"
        ? "UNSUPPORTED_PAGE"
        : "DOM_PAYLOAD_MISMATCH";
      const data = state === "UNSUPPORTED_PAGE" ? null : withBackend(summary, backend);
      return contracts.response(state, data, "PAGE_CHANGED_DURING_HEALTH");
    }
    extraction = verifiedExtraction;
    let headers;
    try {
      headers = localCsrfHeaders();
    } catch (_error) {
      return contracts.response("SAFE_ERROR", withBackend(summary, backend), "CSRF_TOKEN_UNAVAILABLE");
    }
    const orderId = extraction.order.order_id;
    const body = canonical.canonicalStringify({
      request_key: contracts.validateRequestKey(message.request_key),
      schema_version: contracts.API_REQUEST_SCHEMA_VERSION
    });
    if (sourceChanged(observer, mutationState, initialHref)) {
      return contracts.response(
        "DOM_PAYLOAD_MISMATCH",
        withBackend(summary, backend),
        "PAGE_CHANGED_BEFORE_EVALUATION"
      );
    }
    try {
      const resultPromise = fetchClosedJson(
        extraction.origin,
        `/api/v1/orders/${encodeURIComponent(orderId)}/evaluate`,
        {
          body,
          headers,
          method: "POST"
        },
        EVALUATION_TIMEOUT_MS
      );
      observer.disconnect();
      const result = await resultPromise;
      if (result.status === 409) {
        if (result.envelope.error.code !== "IDEMPOTENCY_KEY_MATERIAL_CONFLICT") {
          return contracts.response(
            "SAFE_ERROR",
            withBackend(summary, backend),
            "EVALUATION_CONFLICT_CODE_INVALID"
          );
        }
        return contracts.response("REQUEST_CONFLICT", withBackend(summary, backend), result.envelope.error.code);
      }
      if (result.status !== 200) {
        return contracts.response("SAFE_ERROR", withBackend(summary, backend), result.envelope.error.code);
      }
      const lineUniverse = new Set(extraction.order.lines.map((line) => line.line_id));
      const evaluation = projectEvaluation(validateEvaluation(
        result.envelope.data,
        orderId,
        extraction.order.scenario_alias,
        extraction.order.rule_pack,
        lineUniverse
      ));
      return contracts.response(
        contracts.panelStateForResult(evaluation),
        withEvaluation(summary, backend, evaluation),
        null
      );
    } catch (error) {
      const state = error && error.code === "BACKEND_OFFLINE"
        ? "BACKEND_OFFLINE"
        : "SAFE_ERROR";
      const data = state === "BACKEND_OFFLINE"
        ? summary
        : withBackend(summary, backend);
      return contracts.response(
        state,
        data,
        safeCode(error, "EVALUATION_REQUEST_FAILED")
      );
    }
  }

  async function evaluate(message) {
    if (document.documentElement === null) {
      return contracts.response("UNSUPPORTED_PAGE", null, "DOCUMENT_ROOT_UNAVAILABLE");
    }
    const initialHref = globalThis.location.href;
    const mutationState = {changed: false};
    const observer = new MutationObserver(() => {
      mutationState.changed = true;
    });
    observer.observe(document.documentElement, {
      attributes: true,
      characterData: true,
      childList: true,
      subtree: true
    });
    try {
      return await evaluateObserved(message, observer, mutationState, initialHref);
    } finally {
      observer.disconnect();
    }
  }

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (sender.id !== chrome.runtime.id) return false;
    let validated;
    try {
      validated = contracts.validateMessage(message);
    } catch (error) {
      sendResponse(contracts.response("SAFE_ERROR", null, safeCode(error, "MESSAGE_INVALID")));
      return false;
    }
    const operation = validated.kind === "GET_PAGE_STATE" ? pageState() : evaluate(validated);
    operation.then(sendResponse).catch((error) => {
      sendResponse(contracts.response("SAFE_ERROR", null, safeCode(error, "CONTENT_OPERATION_FAILED")));
    });
    return true;
  });
})();
