/* SYNTHETIC-SALES-ASSIST-AUTHORED-M6 */
"use strict";

importScripts("shared/canonical.js", "shared/contracts.js");

(() => {
  const contracts = globalThis.SSA.Contracts;
  const PANEL_URL = chrome.runtime.getURL("side_panel/index.html");

  function safeResponse(error, fallback) {
    const code = contracts.validateSafeCode(error && error.code, fallback);
    return contracts.response("SAFE_ERROR", null, code);
  }

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (sender.id !== chrome.runtime.id || sender.url !== PANEL_URL) {
      sendResponse(contracts.response("SAFE_ERROR", null, "MESSAGE_SENDER_INVALID"));
      return false;
    }
    try {
      contracts.validateMessage(message);
    } catch (error) {
      sendResponse(safeResponse(error, "MESSAGE_INVALID"));
      return false;
    }
    chrome.tabs.query({active: true, lastFocusedWindow: true})
      .then((tabs) => {
        if (tabs.length !== 1 || !Number.isInteger(tabs[0].id)) {
          return contracts.response("UNSUPPORTED_PAGE", null, "ACTIVE_PAGE_UNAVAILABLE");
        }
        return chrome.tabs.sendMessage(tabs[0].id, message)
          .then(contracts.validateResponse)
          .catch(() => contracts.response("UNSUPPORTED_PAGE", null, "SUPPORTED_CONTENT_SCRIPT_UNAVAILABLE"));
      })
      .then(sendResponse)
      .catch((error) => sendResponse(safeResponse(error, "MESSAGE_RELAY_FAILED")));
    return true;
  });
})();
