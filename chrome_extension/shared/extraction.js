/* SYNTHETIC-SALES-ASSIST-AUTHORED-M6 */
"use strict";

(() => {
  const canonical = globalThis.SSA.Canonical;
  const contracts = globalThis.SSA.Contracts;
  const originPolicy = globalThis.SSA.Origin;
  const allowlist = contracts.EXTRACTION_ALLOWLIST;
  const LOWER_SHA256 = /^[0-9a-f]{64}(?![\s\S])/;
  const QUANTITY = /^(?:0|[1-9][0-9]{0,8})(?![\s\S])/;
  const TIMESTAMP =
    /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,9}))?Z(?![\s\S])/;
  const ALIAS = /^[a-z][a-z0-9-]{0,62}[a-z0-9](?![\s\S])/;
  const INTEGER_AMOUNT = /^-?(?:0|[1-9][0-9]*)(?![\s\S])/;
  const NEGATIVE_ZERO = /^-0(?:\.0+)?(?![\s\S])/;
  const MAX_SOURCE_VERSION_LENGTH = 128;
  const COMPLETENESS_STATES = Object.freeze(["COMPLETE", "INCOMPLETE", "MALFORMED"]);
  const ORDER_PAYLOAD_SCRIPT_IDS = Object.freeze([
    "ssa-synthetic-order-payload", "ssa-extension-order-binding"
  ]);
  const INTERACTION_PAYLOAD_SCRIPT_IDS = Object.freeze([
    "ssa-synthetic-interaction-payload"
  ]);
  const CURRENCY_SCALES = Object.freeze({EUR: 2, JPY: 0, KWD: 3, USD: 2});
  const SOURCE_VERSION_PAIRS = Object.freeze([
    "m5-malformed-fixture/v1\nsynthetic-malformed-input/v1",
    "sales-credit-m5-fixture/v1\nsynthetic-sales-credit-domain/v1",
    "shared-fixture/v1\nshared-whole-order-completeness/v1"
  ]);
  const MALFORMED_SOURCE_VERSION_PAIR =
    "m5-malformed-fixture/v1\nsynthetic-malformed-input/v1";
  const SALES_CREDIT_SOURCE_VERSION_PAIR =
    "sales-credit-m5-fixture/v1\nsynthetic-sales-credit-domain/v1";
  const DOI_SOURCE_VERSION_PAIR =
    "shared-fixture/v1\nshared-whole-order-completeness/v1";
  const FACT_POLICY = Object.freeze({
    activity: Object.freeze({known: Object.freeze(["ACTIVE", "CANCELED", "UNKNOWN"]), unknownReason: "RC-125"}),
    availability: Object.freeze({known: Object.freeze(["IN_STOCK", "DELAYED", "UNKNOWN"]), unknownReason: "RC-016"}),
    drop_ship_state: Object.freeze({known: Object.freeze(["DS", "NON_DS", "UNKNOWN"]), unknownReason: "RC-017"}),
    eta: Object.freeze({unknownReason: "RC-115"}),
    line_value: Object.freeze({unknownReason: "RC-134"}),
    quantity: Object.freeze({unknownReason: "RC-129"})
  });

  class ExtractionError extends Error {
    constructor(code, panelState = "SAFE_ERROR") {
      super(code);
      this.name = "ExtractionError";
      this.code = code;
      this.panelState = panelState;
    }
  }

  function fail(code, panelState = "SAFE_ERROR") {
    throw new ExtractionError(code, panelState);
  }

  function exactOne(root, selector, code, panelState = "DOM_PAYLOAD_MISMATCH") {
    const matches = root.querySelectorAll(selector);
    if (matches.length !== 1) fail(code, panelState);
    return matches[0];
  }

  function optionalString(value, code) {
    if (value === null) return null;
    if (typeof value !== "string" || value.length === 0 || value.length > 4096) fail(code);
    return value;
  }

  function nonnegativeInteger(value, code) {
    if (!Number.isSafeInteger(value) || value < 0) fail(code);
    return value;
  }

  function validateTimestamp(value, code) {
    if (typeof value !== "string") fail(code);
    const match = TIMESTAMP.exec(value);
    if (!match) fail(code);
    const [year, month, day, hour, minute, second] = match.slice(1, 7).map(Number);
    const fraction = match[7] || "";
    const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
    const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    if (
      year < 1 || month < 1 || month > 12 || day < 1 || day > days[month - 1] ||
      hour > 23 || minute > 59 || second > 59 || fraction.endsWith("0")
    ) fail(code);
    return value;
  }

  function sourceVersionPair(completeness) {
    for (const member of ["fixture_version", "source_schema_version"]) {
      const value = completeness[member];
      if (
        typeof value !== "string" || value.length === 0 ||
        value.length > MAX_SOURCE_VERSION_LENGTH
      ) fail("SOURCE_VERSION_BINDING_INVALID", "UNSUPPORTED_PAGE");
    }
    return `${completeness.fixture_version}\n${completeness.source_schema_version}`;
  }

  function canonicalAttribute(element, code) {
    const raw = element.getAttribute("data-ssa-value");
    if (raw === null) fail(code, "DOM_PAYLOAD_MISMATCH");
    try {
      return canonical.parseCanonicalJson(raw);
    } catch (_error) {
      fail(code, "DOM_PAYLOAD_MISMATCH");
    }
  }

  function fieldValue(root, name) {
    const element = exactOne(root, `[data-ssa-field="${name}"]`, "DOM_FIELD_CARDINALITY_INVALID");
    return canonicalAttribute(element, "DOM_FIELD_VALUE_INVALID");
  }

  function exactSections(documentValue, root, names) {
    const sections = Array.from(documentValue.querySelectorAll("[data-ssa-section]"));
    const result = {};
    for (const name of names) {
      const globalMatches = sections.filter(
        (section) => section.getAttribute("data-ssa-section") === name
      );
      if (globalMatches.length === 0) {
        fail("GOVERNED_SECTION_REQUIRED", "INCOMPLETE_PAGE");
      }
      if (globalMatches.length !== 1) {
        fail("GOVERNED_SECTION_CARDINALITY_INVALID", "DOM_PAYLOAD_MISMATCH");
      }
      const matches = root.querySelectorAll(`:scope > section[data-ssa-section="${name}"]`);
      if (matches.length !== 1 || !matches[0].classList.contains("panel")) {
        fail("GOVERNED_SECTION_MISPLACED", "DOM_PAYLOAD_MISMATCH");
      }
      result[name] = matches[0];
    }
    if (sections.length !== names.length) {
      fail("GOVERNED_SECTION_INVENTORY_INVALID", "DOM_PAYLOAD_MISMATCH");
    }
    if (!sections.every((section) => (
      root.contains(section) && names.includes(section.getAttribute("data-ssa-section"))
    ))) fail("GOVERNED_SECTION_MISPLACED", "DOM_PAYLOAD_MISMATCH");
    return Object.freeze(result);
  }

  function exactPayloadScript(
    documentValue,
    root,
    identifier,
    expectedIdentifiers,
    missingState
  ) {
    const governed = Array.from(documentValue.querySelectorAll(
      "script#ssa-synthetic-order-payload, " +
      "script#ssa-synthetic-interaction-payload, " +
      "script#ssa-extension-order-binding"
    ));
    const matches = documentValue.querySelectorAll(`script#${identifier}`);
    if (matches.length === 0) fail("CANONICAL_PAYLOAD_REQUIRED", missingState);
    if (
      matches.length !== 1 || governed.length !== expectedIdentifiers.length ||
      !governed.every((script) => expectedIdentifiers.includes(script.id))
    ) {
      fail("CANONICAL_PAYLOAD_CARDINALITY_INVALID", "MALFORMED_PAGE");
    }
    const script = matches[0];
    if (
      !governed.every((item) => (
        item.parentElement === root && item.getAttribute("type") === "application/json"
      ))
    ) fail("CANONICAL_PAYLOAD_MISPLACED", "MALFORMED_PAGE");
    return script;
  }

  function requireGovernedFieldOwnership(documentValue, ownership) {
    const fields = Array.from(documentValue.querySelectorAll("[data-ssa-field]"));
    for (const element of fields) {
      const name = element.getAttribute("data-ssa-field");
      const owner = ownership.find((item) => item.accepts(name));
      if (!owner || !owner.section.contains(element)) {
        fail("GOVERNED_FIELD_MISPLACED", "DOM_PAYLOAD_MISMATCH");
      }
    }
  }

  function validateMoney(value) {
    canonical.exactMembers(value, allowlist.money, "MONEY_MEMBERS_INVALID");
    if (typeof value.currency_code !== "string") fail("MONEY_VALUE_INVALID");
    const scale = CURRENCY_SCALES[value.currency_code];
    const amountPattern = scale === 0
      ? INTEGER_AMOUNT
      : new RegExp(`^-?(?:0|[1-9][0-9]*)\\.[0-9]{${scale}}(?![\\s\\S])`);
    if (
      scale === undefined || typeof value.amount !== "string" || !amountPattern.test(value.amount) ||
      value.currency_registry_version !== "synthetic-iso-style-currency-registry/v1" ||
      value.currency_scale !== scale || NEGATIVE_ZERO.test(value.amount)
    ) fail("MONEY_VALUE_INVALID");
    return value;
  }

  function validateFact(field, value, completenessState) {
    canonical.exactMembers(value, allowlist.fact, "FACT_MEMBERS_INVALID");
    const policy = FACT_POLICY[field];
    if (!policy) fail("FACT_FIELD_INVALID");
    if (value.tag === "UNKNOWN") {
      if (value.value !== null || value.reason_code !== policy.unknownReason) fail("FACT_UNKNOWN_INVALID");
      return value;
    }
    if (value.tag === "NOT_APPLICABLE") {
      if (value.value !== null || value.reason_code !== null) fail("FACT_NOT_APPLICABLE_INVALID");
      return value;
    }
    if (value.tag === "MALFORMED") {
      if (completenessState !== "MALFORMED" || value.value !== null || value.reason_code !== null) {
        fail("FACT_MALFORMED_INVALID");
      }
      return value;
    }
    if (value.tag !== "KNOWN" || value.reason_code !== null || value.value === null) {
      fail("FACT_KNOWN_INVALID");
    }
    if (field === "eta") {
      validateTimestamp(value.value, "ETA_VALUE_INVALID");
    } else if (field === "quantity") {
      if (typeof value.value !== "string" || !QUANTITY.test(value.value)) fail("QUANTITY_VALUE_INVALID");
    } else if (field === "line_value") {
      validateMoney(value.value);
    } else if (!policy.known.includes(value.value)) {
      fail("FACT_ENUM_INVALID");
    }
    return value;
  }

  function validateCompleteness(value, orderId) {
    canonical.exactMembers(value, allowlist.completeness, "COMPLETENESS_MEMBERS_INVALID");
    if (!COMPLETENESS_STATES.includes(value.state)) fail("COMPLETENESS_STATE_INVALID");
    contracts.validateSyntheticId(value.requested_order_id, "ORDER");
    if (value.observed_order_id !== null) contracts.validateSyntheticId(value.observed_order_id, "ORDER");
    if (value.requested_order_id !== orderId) fail("REQUESTED_ORDER_IDENTITY_INVALID");
    if (value.declared_relevant_line_count !== null) {
      nonnegativeInteger(value.declared_relevant_line_count, "DECLARED_LINE_COUNT_INVALID");
    }
    nonnegativeInteger(value.rendered_relevant_line_count, "RENDERED_LINE_COUNT_INVALID");
    if (!SOURCE_VERSION_PAIRS.includes(sourceVersionPair(value))) {
      fail("SOURCE_VERSION_BINDING_INVALID", "UNSUPPORTED_PAGE");
    }
    const timestamp = optionalString(value.source_observed_at, "SOURCE_TIME_INVALID");
    if (timestamp !== null) validateTimestamp(timestamp, "SOURCE_TIME_INVALID");
    if (value.ordered_line_manifest_digest !== null && (
      typeof value.ordered_line_manifest_digest !== "string" || !LOWER_SHA256.test(value.ordered_line_manifest_digest)
    )) fail("MANIFEST_DIGEST_INVALID");
    return value;
  }

  function validateLine(value, completenessState) {
    canonical.exactMembers(value, allowlist.line, "LINE_MEMBERS_INVALID");
    contracts.validateSyntheticId(value.line_id, "EVIDENCE");
    contracts.validateSyntheticId(value.product_id, "SKU");
    if (!Number.isSafeInteger(value.line_index) || value.line_index < 1) fail("LINE_INDEX_INVALID");
    for (const field of Object.keys(FACT_POLICY)) validateFact(field, value[field], completenessState);
    return value;
  }

  function validateOrderPayload(value) {
    canonical.exactMembers(value, allowlist.order, "ORDER_PAYLOAD_MEMBERS_INVALID");
    if (value.schema_version !== contracts.DOM_SCHEMA_VERSION) fail("ORDER_PAYLOAD_VERSION_INVALID", "UNSUPPORTED_PAGE");
    const orderId = contracts.validateSyntheticId(value.order_id, "ORDER");
    if (typeof value.mode !== "string" || !ALIAS.test(value.mode)) fail("ORDER_MODE_INVALID");
    if (typeof value.scenario_alias !== "string" || !ALIAS.test(value.scenario_alias)) fail("SCENARIO_ALIAS_INVALID");
    const completeness = validateCompleteness(value.completeness, orderId);
    if (value.source_status !== completeness.state) fail("SOURCE_STATUS_INVALID");
    if (!Array.isArray(value.lines) || value.lines.length > 4096) fail("LINES_INVALID");
    value.lines.forEach((line) => validateLine(line, completeness.state));
    return value;
  }

  function validateOrderBinding(value) {
    canonical.exactMembers(
      value,
      allowlist.order_binding,
      "ORDER_BINDING_MEMBERS_INVALID"
    );
    if (value.schema_version !== contracts.ORDER_BINDING_SCHEMA_VERSION) {
      fail("ORDER_BINDING_VERSION_UNSUPPORTED", "UNSUPPORTED_PAGE");
    }
    contracts.validateSyntheticId(value.order_id, "ORDER");
    if (!["SALES_CREDIT", "DOI"].includes(value.rule_pack)) {
      fail("ORDER_BINDING_RULE_PACK_INVALID");
    }
    return value;
  }

  function validateSourceRulePackBinding(completeness, rulePack) {
    const pair = sourceVersionPair(completeness);
    if (completeness.state !== "COMPLETE") return null;
    if (pair === MALFORMED_SOURCE_VERSION_PAIR) {
      fail("MALFORMED_SOURCE_PROMOTION_INVALID", "DOM_PAYLOAD_MISMATCH");
    }
    const expectedRulePack = pair === SALES_CREDIT_SOURCE_VERSION_PAIR
      ? "SALES_CREDIT"
      : pair === DOI_SOURCE_VERSION_PAIR
        ? "DOI"
        : null;
    if (expectedRulePack === null || rulePack !== expectedRulePack) {
      fail("SOURCE_RULE_PACK_BINDING_INVALID", "DOM_PAYLOAD_MISMATCH");
    }
    return expectedRulePack;
  }

  function extractDomCompleteness(section) {
    if (
      !section.matches(
        'section.panel[data-ssa-section="completeness"]' +
        '[data-ssa-completeness][data-ssa-manifest-digest]' +
        '[aria-labelledby="completeness-heading"]'
      )
    ) fail("COMPLETENESS_SECTION_INVALID", "INCOMPLETE_PAGE");
    const result = {};
    for (const member of allowlist.completeness) {
      result[member] = fieldValue(section, `completeness.${member}`);
    }
    if (section.getAttribute("data-ssa-completeness") !== result.state) {
      fail("COMPLETENESS_ATTRIBUTE_INVALID", "DOM_PAYLOAD_MISMATCH");
    }
    const digestAttribute = section.getAttribute("data-ssa-manifest-digest");
    const digestText = result.ordered_line_manifest_digest === null ? "None" : result.ordered_line_manifest_digest;
    if (digestAttribute !== digestText) {
      fail("MANIFEST_ATTRIBUTE_INVALID", "DOM_PAYLOAD_MISMATCH");
    }
    return result;
  }

  function extractDomLines(documentValue, section, payloadState) {
    if (!section.matches('section.panel.table-wrap[data-ssa-section="line-universe"]')) {
      fail("LINE_UNIVERSE_SECTION_INVALID", "DOM_PAYLOAD_MISMATCH");
    }
    const markerMatches = section.querySelectorAll(
      '[data-ssa-field="line-universe-end"]'
    );
    if (markerMatches.length !== 1 || markerMatches[0].parentElement !== section) {
      fail("LINE_UNIVERSE_SECTION_INVALID", payloadState === "COMPLETE" ? "DOM_PAYLOAD_MISMATCH" : "INCOMPLETE_PAGE");
    }
    const tables = section.querySelectorAll("table");
    if (tables.length !== 1 || tables[0].parentElement !== section) {
      fail("LINE_TABLE_INVALID", "DOM_PAYLOAD_MISMATCH");
    }
    const captions = tables[0].querySelectorAll("caption");
    const bodies = tables[0].querySelectorAll("tbody");
    if (
      captions.length !== 1 || captions[0].parentElement !== tables[0] ||
      bodies.length !== 1 || bodies[0].parentElement !== tables[0]
    ) fail("LINE_TABLE_STRUCTURE_INVALID", "DOM_PAYLOAD_MISMATCH");
    const rows = Array.from(bodies[0].children);
    if (!rows.every((row) => row.matches("tr[data-ssa-line-id][data-ssa-line-index]"))) {
      fail("LINE_ROW_STRUCTURE_INVALID", "DOM_PAYLOAD_MISMATCH");
    }
    const globalRows = Array.from(
      documentValue.querySelectorAll("tr[data-ssa-line-id], tr[data-ssa-line-index]")
    );
    const rowSet = new Set(rows);
    if (globalRows.length !== rows.length || !globalRows.every((row) => rowSet.has(row))) {
      fail("LINE_ROW_MISPLACED", "DOM_PAYLOAD_MISMATCH");
    }
    const lineFields = Array.from(documentValue.querySelectorAll('[data-ssa-field^="line."]'));
    if (!lineFields.every((field) => rowSet.has(field.closest("tr")))) {
      fail("LINE_FIELD_MISPLACED", "DOM_PAYLOAD_MISMATCH");
    }
    const lines = rows.map((row) => {
      const result = {};
      for (const member of allowlist.line) result[member] = fieldValue(row, `line.${member}`);
      if (
        row.getAttribute("data-ssa-line-id") !== result.line_id ||
        row.getAttribute("data-ssa-line-index") !== String(result.line_index)
      ) fail("LINE_ATTRIBUTE_INVALID", "DOM_PAYLOAD_MISMATCH");
      return result;
    });
    if (canonicalAttribute(markerMatches[0], "LINE_UNIVERSE_MARKER_INVALID") !== rows.length) {
      fail("LINE_UNIVERSE_MARKER_INVALID", "DOM_PAYLOAD_MISMATCH");
    }
    return lines;
  }

  async function orderedManifestDigest(lines) {
    const material = canonical.canonicalStringify({
      lines,
      schema_version: contracts.LINE_MANIFEST_SCHEMA_VERSION
    });
    return canonical.sha256Hex(`${contracts.LINE_MANIFEST_DOMAIN}\n${material}`);
  }

  async function extractOrder(documentValue, root, locationValue) {
    let orderId;
    try {
      orderId = contracts.validateSyntheticId(root.getAttribute("data-ssa-order-id"), "ORDER");
    } catch (_error) {
      fail("ORDER_ROOT_IDENTITY_INVALID", "UNSUPPORTED_PAGE");
    }
    if (!originPolicy.isClosedOrderPath(locationValue.path, orderId)) fail("ORDER_PATH_BINDING_INVALID", "UNSUPPORTED_PAGE");
    const sections = exactSections(
      documentValue,
      root,
      ["order-summary", "completeness", "line-universe"]
    );
    const summaryFields = new Set([
      "mode", "order_id", "rule_pack", "scenario_alias", "source_status"
    ]);
    const completenessFields = new Set(
      allowlist.completeness.map((member) => `completeness.${member}`)
    );
    const lineFields = new Set(allowlist.line.map((member) => `line.${member}`));
    requireGovernedFieldOwnership(documentValue, [
      Object.freeze({
        accepts: (name) => summaryFields.has(name),
        section: sections["order-summary"]
      }),
      Object.freeze({
        accepts: (name) => completenessFields.has(name),
        section: sections.completeness
      }),
      Object.freeze({
        accepts: (name) => name === "line-universe-end" || lineFields.has(name),
        section: sections["line-universe"]
      })
    ]);
    const script = exactPayloadScript(
      documentValue,
      root,
      "ssa-synthetic-order-payload",
      ORDER_PAYLOAD_SCRIPT_IDS,
      "INCOMPLETE_PAGE"
    );
    const bindingScript = exactPayloadScript(
      documentValue,
      root,
      "ssa-extension-order-binding",
      ORDER_PAYLOAD_SCRIPT_IDS,
      "INCOMPLETE_PAGE"
    );
    let payload;
    let binding;
    try {
      payload = canonical.parseCanonicalJson(script.textContent, allowlist.order);
    } catch (_error) {
      fail("ORDER_PAYLOAD_INVALID", "MALFORMED_PAGE");
    }
    try {
      validateOrderPayload(payload);
    } catch (error) {
      if (error.panelState === "UNSUPPORTED_PAGE") throw error;
      fail(error.code || "ORDER_PAYLOAD_INVALID", "MALFORMED_PAGE");
    }
    try {
      binding = canonical.parseCanonicalJson(
        bindingScript.textContent,
        allowlist.order_binding
      );
      validateOrderBinding(binding);
    } catch (error) {
      if (error.panelState === "UNSUPPORTED_PAGE") throw error;
      fail(error.code || "ORDER_BINDING_INVALID", "MALFORMED_PAGE");
    }
    if (
      payload.order_id !== orderId || binding.order_id !== orderId ||
      binding.order_id !== payload.order_id
    ) fail("ORDER_PAYLOAD_IDENTITY_INVALID", "DOM_PAYLOAD_MISMATCH");
    validateSourceRulePackBinding(payload.completeness, binding.rule_pack);
    const rootCompleteness = root.getAttribute("data-ssa-completeness");
    const rootDigest = root.getAttribute("data-ssa-manifest-digest");
    const payloadDigestAttribute = payload.completeness.ordered_line_manifest_digest === null
      ? "None"
      : payload.completeness.ordered_line_manifest_digest;
    if (
      rootCompleteness !== payload.completeness.state ||
      rootDigest !== payloadDigestAttribute
    ) fail("ORDER_ROOT_BINDING_INVALID", "DOM_PAYLOAD_MISMATCH");

    const summary = {
      mode: fieldValue(sections["order-summary"], "mode"),
      order_id: fieldValue(sections["order-summary"], "order_id"),
      rule_pack: fieldValue(sections["order-summary"], "rule_pack"),
      scenario_alias: fieldValue(sections["order-summary"], "scenario_alias"),
      source_status: fieldValue(sections["order-summary"], "source_status")
    };
    if (canonical.canonicalStringify(summary) !== canonical.canonicalStringify({
      mode: payload.mode,
      order_id: payload.order_id,
      rule_pack: binding.rule_pack,
      scenario_alias: payload.scenario_alias,
      source_status: payload.source_status
    })) fail("ORDER_SUMMARY_MISMATCH", "DOM_PAYLOAD_MISMATCH");

    const domCompleteness = extractDomCompleteness(sections.completeness);
    const domLines = extractDomLines(
      documentValue,
      sections["line-universe"],
      payload.completeness.state
    );
    if (
      canonical.canonicalStringify(domCompleteness) !== canonical.canonicalStringify(payload.completeness) ||
      canonical.canonicalStringify(domLines) !== canonical.canonicalStringify(payload.lines)
    ) fail("DOM_PAYLOAD_MISMATCH", "DOM_PAYLOAD_MISMATCH");

    const completeness = payload.completeness;
    const extractedOrder = Object.freeze({...payload, rule_pack: binding.rule_pack});
    if (completeness.state === "MALFORMED") {
      return makeExtraction(
        locationValue,
        "order-detail",
        orderId,
        false,
        "MALFORMED_PAGE",
        extractedOrder,
        null
      );
    }
    if (completeness.state !== "COMPLETE") {
      return makeExtraction(
        locationValue,
        "order-detail",
        orderId,
        false,
        "INCOMPLETE_PAGE",
        extractedOrder,
        null
      );
    }
    const lineIds = payload.lines.map((line) => line.line_id);
    const coherent =
      completeness.requested_order_id === orderId &&
      completeness.observed_order_id === orderId &&
      completeness.declared_relevant_line_count === payload.lines.length &&
      completeness.rendered_relevant_line_count === payload.lines.length &&
      completeness.source_observed_at !== null &&
      lineIds.length === new Set(lineIds).size &&
      payload.lines.every((line, index) => line.line_index === index + 1);
    if (!coherent) fail("COMPLETE_ORDER_COHERENCE_INVALID", "DOM_PAYLOAD_MISMATCH");
    const digest = await orderedManifestDigest(payload.lines);
    if (digest !== completeness.ordered_line_manifest_digest) {
      fail("ORDER_MANIFEST_MISMATCH", "DOM_PAYLOAD_MISMATCH");
    }
    return makeExtraction(
      locationValue,
      "order-detail",
      orderId,
      true,
      "SUPPORTED_READY",
      extractedOrder,
      null
    );
  }

  function validateInteractionPayload(value) {
    canonical.exactMembers(value, allowlist.interaction, "INTERACTION_PAYLOAD_MEMBERS_INVALID");
    if (value.schema_version !== contracts.APPLICATION_SCHEMA_VERSION) fail("INTERACTION_SCHEMA_INVALID", "UNSUPPORTED_PAGE");
    contracts.validateSyntheticId(value.interaction_id, "INTERACTION");
    contracts.validateSyntheticId(value.order_id, "ORDER");
    if (
      value.direction !== "INBOUND" ||
      value.evidence_classification !== "SYNTHETIC_SOURCE_INTERACTION" ||
      value.identifier_kind !== "EMAIL" ||
      !["KNOWN_PRESENT", "UNKNOWN"].includes(value.target_rep_participation) ||
      !["EXACT", "CORRECTED", "REVISION_DERIVED", "HISTORICAL_APPROXIMATION"].includes(value.timestamp_precision) ||
      typeof value.timestamp !== "string"
    ) fail("INTERACTION_FIELD_INVALID");
    validateTimestamp(value.timestamp, "INTERACTION_TIMESTAMP_INVALID");
    return value;
  }

  function extractInteraction(documentValue, root, locationValue) {
    let interactionId;
    let rootOrderId;
    try {
      interactionId = contracts.validateSyntheticId(
        root.getAttribute("data-ssa-interaction-id"),
        "INTERACTION"
      );
      rootOrderId = contracts.validateSyntheticId(root.getAttribute("data-ssa-order-id"), "ORDER");
    } catch (_error) {
      fail("INTERACTION_ROOT_IDENTITY_INVALID", "UNSUPPORTED_PAGE");
    }
    if (!originPolicy.isClosedInteractionPath(locationValue.path, interactionId)) fail("INTERACTION_PATH_BINDING_INVALID", "UNSUPPORTED_PAGE");
    const sections = exactSections(documentValue, root, ["interaction-summary"]);
    const interactionFields = new Set(
      allowlist.interaction
        .filter((member) => member !== "schema_version")
        .map((member) => `interaction.${member}`)
    );
    requireGovernedFieldOwnership(documentValue, [
      Object.freeze({
        accepts: (name) => interactionFields.has(name),
        section: sections["interaction-summary"]
      })
    ]);
    const script = exactPayloadScript(
      documentValue,
      root,
      "ssa-synthetic-interaction-payload",
      INTERACTION_PAYLOAD_SCRIPT_IDS,
      "INCOMPLETE_PAGE"
    );
    let payload;
    try {
      payload = canonical.parseCanonicalJson(script.textContent, allowlist.interaction);
    } catch (_error) {
      fail("INTERACTION_PAYLOAD_INVALID", "MALFORMED_PAGE");
    }
    try {
      validateInteractionPayload(payload);
    } catch (error) {
      if (error.panelState === "UNSUPPORTED_PAGE") throw error;
      fail(error.code || "INTERACTION_PAYLOAD_INVALID", "MALFORMED_PAGE");
    }
    if (payload.interaction_id !== interactionId || payload.order_id !== rootOrderId) {
      fail("INTERACTION_IDENTITY_MISMATCH", "DOM_PAYLOAD_MISMATCH");
    }
    const domFacts = {schema_version: contracts.APPLICATION_SCHEMA_VERSION};
    for (const member of allowlist.interaction) {
      if (member !== "schema_version") {
        domFacts[member] = fieldValue(
          sections["interaction-summary"],
          `interaction.${member}`
        );
      }
    }
    if (canonical.canonicalStringify(domFacts) !== canonical.canonicalStringify(payload)) {
      fail("INTERACTION_DOM_PAYLOAD_MISMATCH", "DOM_PAYLOAD_MISMATCH");
    }
    return makeExtraction(locationValue, "interaction-detail", interactionId, false, "SUPPORTED_READY", null, payload);
  }

  function makeExtraction(locationValue, pageKind, identity, canEvaluate, panelState, order, interaction) {
    return Object.freeze({
      can_evaluate: canEvaluate,
      extraction_schema_version: contracts.EXTRACTION_SCHEMA_VERSION,
      interaction,
      order,
      origin: locationValue.origin,
      page_identity: identity,
      page_kind: pageKind,
      page_path: locationValue.path,
      panel_state: panelState
    });
  }

  async function extractPage(documentValue, href) {
    let locationValue;
    try {
      locationValue = originPolicy.validatePageLocation(href);
    } catch (_error) {
      fail("PAGE_ORIGIN_INVALID", "UNSUPPORTED_PAGE");
    }
    const roots = documentValue.querySelectorAll("main[data-ssa-page-kind]");
    if (roots.length !== 1) return makeExtraction(locationValue, "unsupported", null, false, "UNSUPPORTED_PAGE", null, null);
    const root = roots[0];
    if (root.getAttribute("data-ssa-schema-version") !== contracts.DOM_SCHEMA_VERSION) {
      fail("DOM_SCHEMA_VERSION_UNSUPPORTED", "UNSUPPORTED_PAGE");
    }
    const pageKind = root.getAttribute("data-ssa-page-kind");
    if (pageKind === "order-detail") return extractOrder(documentValue, root, locationValue);
    if (pageKind === "interaction-detail") return extractInteraction(documentValue, root, locationValue);
    return makeExtraction(locationValue, "unsupported", null, false, "UNSUPPORTED_PAGE", null, null);
  }

  function panelSummary(extraction, sourceFingerprint = null) {
    return Object.freeze({
      backend: null,
      can_evaluate: extraction.can_evaluate,
      completeness_state: extraction.order === null ? null : extraction.order.completeness.state,
      evaluation: null,
      interaction_id: extraction.interaction === null ? null : extraction.interaction.interaction_id,
      order_id: extraction.order === null ? (extraction.interaction === null ? null : extraction.interaction.order_id) : extraction.order.order_id,
      origin: extraction.origin,
      page_identity: extraction.page_identity,
      page_kind: extraction.page_kind,
      rule_pack: extraction.order === null ? null : extraction.order.rule_pack,
      scenario_alias: extraction.order === null ? null : extraction.order.scenario_alias,
      source_fingerprint: sourceFingerprint
    });
  }

  const root = globalThis.SSA || (globalThis.SSA = {});
  root.Extraction = Object.freeze({
    ExtractionError,
    extractPage,
    orderedManifestDigest,
    panelSummary,
    validateCompleteness,
    validateFact,
    validateInteractionPayload,
    validateLine,
    validateOrderPayload,
    validateSourceRulePackBinding,
    validateTimestamp
  });
})();
