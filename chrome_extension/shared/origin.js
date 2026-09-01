/* SYNTHETIC-SALES-ASSIST-AUTHORED-M6 */
"use strict";

(() => {
  const contracts = globalThis.SSA.Contracts;
  const ALLOWED_HOSTS = Object.freeze(["127.0.0.1", "localhost"]);

  function reject() {
    contracts.contractError("LOOPBACK_ORIGIN_INVALID");
  }

  function parseUrl(candidate, allowFragment) {
    if (typeof candidate !== "string" || candidate.length > 2048) reject();
    if (/[\r\n\u2028\u2029]/.test(candidate)) reject();
    const fragmentIndex = candidate.indexOf("#");
    const queryIndex = candidate.indexOf("?");
    if (
      (queryIndex !== -1 && (fragmentIndex === -1 || queryIndex < fragmentIndex)) ||
      (!allowFragment && fragmentIndex !== -1)
    ) reject();
    if (
      !/^http:\/\/(?:127\.0\.0\.1|localhost):8765(?:\/|(?![\s\S]))/.test(candidate)
    ) reject();
    let parsed;
    try {
      parsed = new URL(candidate);
    } catch (_error) {
      reject();
    }
    if (
      parsed.protocol !== "http:" ||
      !ALLOWED_HOSTS.includes(parsed.hostname) ||
      parsed.port !== contracts.SERVICE_PORT ||
      parsed.username !== "" ||
      parsed.password !== ""
    ) reject();
    return parsed;
  }

  function normalizeServiceOrigin(candidate) {
    const parsed = parseUrl(candidate, false);
    if (parsed.pathname !== "/" || parsed.search !== "" || parsed.hash !== "") reject();
    return parsed.origin;
  }

  function validatePageLocation(candidate) {
    const parsed = parseUrl(candidate, true);
    if (parsed.search !== "") reject();
    return Object.freeze({
      origin: parsed.origin,
      path: parsed.pathname,
      url: `${parsed.origin}${parsed.pathname}${parsed.hash}`
    });
  }

  function isClosedOrderPath(path, orderId) {
    return path === `/orders/${encodeURIComponent(orderId)}`;
  }

  function isClosedInteractionPath(path, interactionId) {
    return path === `/interactions/${encodeURIComponent(interactionId)}`;
  }

  function dashboardUrl(origin, kind, identifier = null) {
    const normalizedOrigin = normalizeServiceOrigin(`${origin}/`);
    let path;
    if (kind === "OVERVIEW") path = "/overview";
    else if (kind === "REVIEW") path = "/review";
    else if (kind === "SYSTEM") path = "/system";
    else if (kind === "ORDER") {
      path = `/orders/${encodeURIComponent(contracts.validateSyntheticId(identifier, "ORDER"))}`;
    } else if (kind === "SALES_CREDIT_CASE") {
      path = `/sales-credit/${encodeURIComponent(contracts.validateSyntheticId(identifier, "ORDER"))}`;
    } else if (kind === "DOI_CASE") {
      path = `/doi/${encodeURIComponent(contracts.validateSyntheticId(identifier, "EVIDENCE"))}`;
    } else if (kind === "EVALUATION_AUDIT") {
      path = `/audit/evaluation/${encodeURIComponent(
        contracts.validateSyntheticId(identifier, "EVALUATION")
      )}`;
    } else {
      contracts.contractError("DASHBOARD_LINK_KIND_INVALID");
    }
    const href = `${normalizedOrigin}${path}`;
    const parsed = new URL(href);
    if (
      parsed.origin !== normalizedOrigin || parsed.pathname !== path ||
      parsed.search !== "" || parsed.hash !== ""
    ) contracts.contractError("DASHBOARD_LINK_INVALID");
    return href;
  }

  const root = globalThis.SSA || (globalThis.SSA = {});
  root.Origin = Object.freeze({
    ALLOWED_HOSTS,
    dashboardUrl,
    isClosedInteractionPath,
    isClosedOrderPath,
    normalizeServiceOrigin,
    validatePageLocation
  });
})();
