/* SYNTHETIC-SALES-ASSIST-AUTHORED-M6 */
"use strict";

(() => {
  const contracts = globalThis.SSA.Contracts;
  const originPolicy = globalThis.SSA.Origin;
  const elements = Object.freeze({
    appVersion: document.getElementById("app-version"),
    auditLink: document.getElementById("audit-link"),
    backendHealth: document.getElementById("backend-health"),
    buildVersion: document.getElementById("build-version"),
    caseLink: document.getElementById("case-link"),
    completeness: document.getElementById("completeness"),
    evaluate: document.getElementById("evaluate"),
    historyLink: document.getElementById("history-link"),
    opportunities: document.getElementById("opportunities"),
    overviewLink: document.getElementById("overview-link"),
    pageIdentity: document.getElementById("page-identity"),
    pageKind: document.getElementById("page-kind"),
    reasons: document.getElementById("reasons"),
    refresh: document.getElementById("refresh"),
    requestKey: document.getElementById("request-key"),
    resultCard: document.getElementById("result-card"),
    resultDetails: document.getElementById("result-details"),
    retry: document.getElementById("retry"),
    reviewLink: document.getElementById("review-link"),
    safetyCounters: document.getElementById("safety-counters"),
    scenario: document.getElementById("scenario"),
    sourceRulePack: document.getElementById("source-rule-pack"),
    stateDetail: document.getElementById("state-detail"),
    stateHeading: document.getElementById("state-heading"),
    systemLink: document.getElementById("system-link")
  });
  const STATE_COPY = Object.freeze({
    UNSUPPORTED_PAGE: ["Unsupported page", "Open a supported synthetic order or interaction detail page."],
    SUPPORTED_READY: ["Supported page ready", "The local source is coherent and the backend is healthy."],
    INCOMPLETE_PAGE: ["Incomplete source page", "Evaluation is blocked because the complete source universe is unavailable."],
    MALFORMED_PAGE: ["Malformed source page", "Evaluation is blocked because a governed field is malformed."],
    DOM_PAYLOAD_MISMATCH: ["DOM and payload disagree", "Evaluation failed closed before any evaluation POST."],
    BACKEND_OFFLINE: ["Local backend offline", "Start the localhost service, then refresh this panel."],
    BACKEND_UNHEALTHY: ["Local backend unhealthy", "Evaluation is blocked until all local health checks pass."],
    EVALUATING: ["Evaluating locally…", "Keep this supported page active while the bounded request completes."],
    SALES_CREDIT_RESULT: ["Sales Credit result", "A local synthetic Sales Credit result was returned."],
    DOI_OPPORTUNITY: ["DOI opportunity", "One or more separately scoped synthetic opportunities were returned."],
    DOI_MANUAL_REVIEW: ["DOI manual review", "The result requires a fictional human review; no external action was taken."],
    DOI_EXCLUDED: ["DOI excluded", "The synthetic order is excluded under the committed local rule pack."],
    DOI_MONITOR: ["DOI monitor", "The synthetic order remains in monitor state."],
    EXACT_REPLAY: ["Exact replay", "The same bounded request key returned its persisted result."],
    REQUEST_CONFLICT: ["Request-key conflict", "This key is already bound to different material; the original result was preserved."],
    SAFE_ERROR: ["Request failed closed", "No external action was taken. A safe retry may use the same request key."]
  });
  let inFlight = false;
  let lastRequestBinding = null;
  let lastRequestKey = null;
  let operationGeneration = 0;
  let readyBinding = null;
  let renderedCanEvaluate = false;
  let renderedState = "UNSUPPORTED_PAGE";

  function generatedRequestKey() {
    const bytes = new Uint8Array(16);
    crypto.getRandomValues(bytes);
    return `M6-EXT-${Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("")}`;
  }

  function clearChildren(element) {
    while (element.firstChild) element.removeChild(element.firstChild);
  }

  function text(value) {
    if (value === null || value === undefined) return "Not available";
    if (Array.isArray(value)) return value.length === 0 ? "None" : value.join(", ");
    if (typeof value === "object") return JSON.stringify(value);
    return String(value);
  }

  function addDetail(label, value) {
    const term = document.createElement("dt");
    const description = document.createElement("dd");
    term.textContent = label;
    description.textContent = text(value);
    elements.resultDetails.append(term, description);
  }

  function addListItem(list, value) {
    const item = document.createElement("li");
    item.textContent = text(value);
    list.append(item);
  }

  function hideLink(element) {
    element.hidden = true;
    element.removeAttribute("href");
  }

  function showLink(element, origin, kind, identifier = null) {
    element.href = originPolicy.dashboardUrl(origin, kind, identifier);
    element.hidden = false;
  }

  function renderDashboardLinks(data) {
    const links = [
      elements.auditLink, elements.caseLink, elements.historyLink,
      elements.overviewLink, elements.reviewLink, elements.systemLink
    ];
    links.forEach(hideLink);
    if (
      !data || !["order-detail", "interaction-detail"].includes(data.page_kind)
    ) return;
    showLink(elements.overviewLink, data.origin, "OVERVIEW");
    showLink(elements.systemLink, data.origin, "SYSTEM");
    if (data.order_id !== null) {
      showLink(elements.historyLink, data.origin, "ORDER", data.order_id);
    }
    const evaluation = data.evaluation;
    if (evaluation === null) return;
    const caseKind = evaluation.rule_pack === "SALES_CREDIT"
      ? "SALES_CREDIT_CASE"
      : "DOI_CASE";
    showLink(elements.caseLink, data.origin, caseKind, evaluation.case_id);
    elements.caseLink.textContent = evaluation.rule_pack === "SALES_CREDIT"
      ? "Open Sales Credit case"
      : "Open DOI case";
    showLink(
      elements.auditLink,
      data.origin,
      "EVALUATION_AUDIT",
      evaluation.evaluation_id
    );
    if (evaluation.human_review_required) {
      showLink(elements.reviewLink, data.origin, "REVIEW");
    }
  }

  function renderEvaluation(evaluation) {
    clearChildren(elements.resultDetails);
    clearChildren(elements.reasons);
    clearChildren(elements.opportunities);
    if (!evaluation) {
      elements.resultCard.hidden = true;
      return;
    }
    elements.resultCard.hidden = false;
    const details = [
      ["Rule pack", evaluation.rule_pack],
      ["Rule pack version", evaluation.rule_pack_version],
      ["Result", evaluation.top_level_result],
      ["Workflow", evaluation.workflow_state],
      ["Human review", evaluation.human_review_required],
      ["Value status", evaluation.value_status],
      ["Value", evaluation.value],
      ["Aggregate potential", evaluation.aggregate_potential_status],
      ["Aggregate potential value", evaluation.aggregate_potential_value],
      ["Closure state", evaluation.closure_state],
      ["Handling flags", evaluation.handling_flags],
      ["Exact replay", evaluation.replayed],
      ["Conflict", evaluation.conflict],
      ["Evaluation ID", evaluation.evaluation_id],
      ["Run ID", evaluation.run_id],
      ["Snapshot ID", evaluation.snapshot_id],
      ["Command ID", evaluation.command_id],
      ["Case ID", evaluation.case_id],
      ["Processing duration (ns)", evaluation.processing_duration_ns]
    ];
    details.forEach(([label, value]) => addDetail(label, value));
    if (evaluation.reasons.length === 0) addListItem(elements.reasons, "None");
    evaluation.reasons.forEach((reason) => addListItem(elements.reasons, reason));
    if (evaluation.opportunities.length === 0) addListItem(elements.opportunities, "None");
    evaluation.opportunities.forEach((opportunity) => {
      addListItem(elements.opportunities, `${opportunity.opportunity_type} · lines ${opportunity.line_ids.join(", ")} · potential ${text(opportunity.potential_value)}`);
    });
  }

  function render(response) {
    response = contracts.validateResponse(response);
    const state = contracts.PANEL_STATES.includes(response.panel_state) ? response.panel_state : "SAFE_ERROR";
    const copy = STATE_COPY[state];
    document.body.dataset.state = state;
    elements.stateHeading.textContent = copy[0];
    elements.stateDetail.textContent = response.error_code === null ? copy[1] : `${copy[1]} Code: ${contracts.validateSafeCode(response.error_code)}`;
    const data = response.data;
    readyBinding = state === "SUPPORTED_READY" && data && data.can_evaluate
      ? Object.freeze({
        expected_order_id: data.order_id,
        expected_origin: data.origin,
        expected_source_fingerprint: data.source_fingerprint
      })
      : null;
    elements.pageKind.textContent = data ? text(data.page_kind) : "Not available";
    elements.pageIdentity.textContent = data ? text(data.page_identity) : "Not available";
    elements.completeness.textContent = data ? text(data.completeness_state) : "Not available";
    elements.scenario.textContent = data ? text(data.scenario_alias) : "Not available";
    elements.sourceRulePack.textContent = data ? text(data.rule_pack) : "Not available";
    const backend = data && data.backend;
    elements.backendHealth.textContent = backend ? text(backend.status) : "Not checked";
    elements.appVersion.textContent = backend ? text(backend.app_version) : "Not available";
    elements.buildVersion.textContent = backend ? text(backend.build_version) : "Not available";
    elements.safetyCounters.textContent = backend ? (backend.safety_counters_zero ? "All nine zero" : "FAIL") : "Not checked";
    renderedState = state;
    renderedCanEvaluate = readyBinding !== null;
    elements.retry.hidden = !(["SAFE_ERROR", "BACKEND_OFFLINE"].includes(state) && lastRequestKey !== null);
    renderEvaluation(data && data.evaluation);
    renderDashboardLinks(data);
    synchronizeControls();
  }

  async function send(message) {
    try {
      contracts.validateMessage(message);
      return contracts.validateResponse(await chrome.runtime.sendMessage(message));
    } catch (_error) {
      return contracts.response("SAFE_ERROR", null, "PANEL_MESSAGE_FAILED");
    }
  }

  function synchronizeControls() {
    elements.evaluate.disabled = inFlight || !(
      renderedState === "SUPPORTED_READY" && renderedCanEvaluate
    );
    elements.refresh.disabled = inFlight;
    elements.retry.disabled = inFlight;
  }

  function beginOperation(evaluating) {
    if (inFlight) return null;
    inFlight = true;
    operationGeneration += 1;
    if (evaluating) {
      document.body.dataset.state = "EVALUATING";
      elements.stateHeading.textContent = STATE_COPY.EVALUATING[0];
      elements.stateDetail.textContent = STATE_COPY.EVALUATING[1];
    }
    synchronizeControls();
    return operationGeneration;
  }

  function finishOperation(generation, response) {
    if (generation !== operationGeneration) return;
    inFlight = false;
    render(response);
  }

  async function refresh() {
    const generation = beginOperation(false);
    if (generation === null) return;
    const response = await send({
      expected_order_id: null,
      expected_origin: null,
      expected_source_fingerprint: null,
      kind: "GET_PAGE_STATE",
      request_key: null,
      schema_version: contracts.MESSAGE_SCHEMA_VERSION
    });
    finishOperation(generation, response);
  }

  async function evaluate(useLastKey) {
    if (inFlight) return;
    const binding = useLastKey ? lastRequestBinding : readyBinding;
    if (binding === null) {
      render(contracts.response("SAFE_ERROR", null, "DISPLAYED_PAGE_BINDING_UNAVAILABLE"));
      return;
    }
    const candidate = useLastKey ? lastRequestKey : elements.requestKey.value;
    let requestKey;
    try {
      requestKey = contracts.validateRequestKey(candidate);
    } catch (_error) {
      render(contracts.response("SAFE_ERROR", null, "REQUEST_KEY_INVALID"));
      return;
    }
    if (!useLastKey) lastRequestBinding = binding;
    lastRequestKey = requestKey;
    const generation = beginOperation(true);
    if (generation === null) return;
    elements.retry.hidden = true;
    const response = await send({
      expected_order_id: binding.expected_order_id,
      expected_origin: binding.expected_origin,
      expected_source_fingerprint: binding.expected_source_fingerprint,
      kind: "EVALUATE",
      request_key: lastRequestKey,
      schema_version: contracts.MESSAGE_SCHEMA_VERSION
    });
    finishOperation(generation, response);
  }

  elements.evaluate.addEventListener("click", () => evaluate(false));
  elements.retry.addEventListener("click", () => evaluate(true));
  elements.refresh.addEventListener("click", refresh);
  elements.requestKey.value = generatedRequestKey();
  refresh();
})();
