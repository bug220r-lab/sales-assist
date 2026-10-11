// SYNTHETIC-SALES-ASSIST-AUTHORED-M5
"use strict";
(() => {
  const normalized = value => value.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  const preserveBody = (original, edited) => normalized(original) === edited ? original : edited;
  const frozen = record => ["IN_FLIGHT", "UNKNOWN", "CREATED", "CREATED_UNVERIFIED"]
    .includes(record?.transfer?.state);
  // Pure helpers also drive the offline regression harness.
  globalThis.DraftTransferUI = {normalized, preserveBody, frozen};
  if (typeof document === "undefined" || !document.getElementById("draft-transfer")) return;
  const byId = id => document.getElementById(id);
  const csrf = document.querySelector('meta[name="ssa-csrf-token"]').content;
  let selected = null, preview = null, busy = false, dirty = false, configured = false;
  let fileGeneration = 0;
  const checks = new Map(), carts = new Map();
  const buttons = ["preview", "commit", "cancel", "check-connection", "refresh", "save",
    "discard", "approve", "create", "retry", "verify"];
  const message = value => { byId("transfer-message").textContent = value; };
  const element = (tag, text) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const checked = id => byId(id).checked;
  const value = id => byId(id).value;
  function controls() {
    for (const id of buttons) byId("transfer-" + id).disabled = busy;
    byId("transfer-commit").disabled = busy || !preview?.can_commit;
    byId("transfer-cancel").disabled = busy || !preview;
    byId("transfer-approve").disabled = busy || dirty || !selected || frozen(selected)
      || selected.holds.length > 0 || !checked("transfer-exact-approval");
    byId("transfer-create").disabled = busy || dirty || !configured || !selected?.approved
      || Boolean(selected?.transfer);
    byId("transfer-retry").disabled = busy || dirty || !configured || !selected?.approved
      || !selected?.transfer?.retry_allowed;
    byId("transfer-save").disabled = busy || !selected || frozen(selected);
    byId("transfer-check-connection").disabled = busy || !configured;
    byId("transfer-body").disabled = busy || !selected?.row.selected_body_text || frozen(selected);
    byId("transfer-recipient").disabled = busy || frozen(selected);
    byId("transfer-customer-decision").disabled = busy || frozen(selected);
    byId("transfer-customer-evidence").disabled = busy || frozen(selected);
    byId("transfer-customer-conditional").disabled = busy || frozen(selected)
      || value("transfer-customer-decision") !== "pending_conditional_outreach";
  }
  async function request(action, fields = {}) {
    const options = {cache: "no-store", credentials: "same-origin"};
    let route = "/api/v1/doi-draft-transfer/state";
    if (action) {
      route = "/api/v1/doi-draft-transfer/action";
      options.method = "POST";
      options.headers = {"Content-Type": "application/json", "X-SSA-CSRF-Token": csrf};
      options.body = JSON.stringify({action, ...fields});
    }
    const response = await fetch(route, options);
    const raw = await response.text();
    if (new TextEncoder().encode(raw).length > 8388608) throw new Error("Response exceeded the local limit.");
    const result = JSON.parse(raw);
    if (!response.ok) throw new Error(result.error?.code || result.code || "Request rejected.");
    return result;
  }
  async function run(work) {
    if (busy) return;
    busy = true; controls();
    try { await work(); }
    catch (error) {
      message(error instanceof TypeError
        ? "Connection interrupted. Refresh results to inspect the journal; no retry was submitted."
        : String(error.message || "Request failed."));
    } finally { busy = false; controls(); }
  }
  function markDirty() {
    if (!selected) return;
    dirty = true;
    byId("transfer-exact-approval").checked = false;
    byId("transfer-body-preview").textContent = value("transfer-body");
    byId("transfer-preview-status").textContent = "Unsaved copy. Save edits to refresh the exact preview.";
    controls();
  }
  function showSavedPreview(segments) {
    const root = byId("transfer-body-preview"); root.replaceChildren();
    for (const part of segments) {
      const linked = typeof part.url === "string" && /^https?:\/\//.test(part.url);
      const node = element(linked ? "a" : "span", part.text);
      if (linked) {
        node.href = part.url; node.target = "_blank"; node.rel = "noopener noreferrer";
      }
      root.append(node);
    }
    byId("transfer-preview-status").textContent = "Saved exact preview. Links open only when you click them.";
  }
  function inputCheck(parent, title, prior, withTime = false) {
    const group = element("div"); group.className = "draft-check";
    const label = element("label"), box = element("input");
    box.type = "checkbox"; box.checked = Boolean(prior.resolved ?? prior.verified);
    label.append(box, document.createTextNode(" " + title)); group.append(label);
    const noteLabel = element("label", "Evidence / explicit acknowledgment");
    const note = element("textarea"); note.rows = 2; note.maxLength = 2000;
    note.value = prior.evidence || ""; noteLabel.append(note); group.append(noteLabel);
    let observed;
    if (withTime) {
      const timeLabel = element("label", "Observed time with UTC offset");
      observed = element("input"); observed.value = prior.observed_at_utc || "";
      observed.placeholder = "YYYY-MM-DDTHH:MM:SSZ"; timeLabel.append(observed);
      group.append(timeLabel); observed.addEventListener("input", markDirty);
    }
    box.addEventListener("change", markDirty); note.addEventListener("input", markDirty);
    parent.append(group); return {box, note, observed};
  }
  async function refresh() {
    const result = await request(); configured = result.transfer_configured;
    byId("transfer-destination").textContent = "ECS Sales · mailbox " + result.mailbox_id
      + " · Jude " + result.user_id + (configured ? " · API configured" : " · API setup required");
    const list = byId("transfer-rows"); list.replaceChildren();
    for (const row of result.rows) {
      const tr = element("tr");
      for (const text of [row.order_id, row.has_selected_copy ? row.copy_version : "WITHHELD",
        row.approved ? "Approved exact version" : row.holds.length + " unresolved checks",
        row.transfer?.state || "Not transferred"]) tr.append(element("td", text));
      const td = element("td"), open = element("button", "Review"); open.type = "button";
      open.addEventListener("click", () => run(async () => {
        if (dirty) { message("Save or discard the current edits before changing drafts."); return; }
        await load(row.order_id);
      })); td.append(open); tr.append(td); list.append(tr);
    }
    controls();
  }
  async function load(oid) {
    selected = await request("detail", {order_id: oid}); dirty = false;
    const row = selected.row, review = selected.review;
    byId("transfer-editor").hidden = false;
    byId("transfer-order-heading").textContent = "Order " + oid;
    byId("transfer-version").textContent = "Version " + selected.version + " · " + row.copy_version
      + " · selected SHA-256 " + (row.selected_body_sha256 || "none");
    byId("transfer-holds").textContent = selected.holds.length ? selected.holds.join("\n") : "All review gates resolved.";
    byId("transfer-recipient").value = row.recipient_email;
    byId("transfer-recipient-verified").checked = review.recipient_verified;
    byId("transfer-recipient-provenance").value = review.recipient_provenance;
    byId("transfer-subject").textContent = row.subject;
    byId("transfer-body").value = row.selected_body_text;
    showSavedPreview(selected.preview_segments);
    byId("transfer-original").textContent = row.preserved_original_body_text;
    byId("transfer-source").textContent = JSON.stringify(row, null, 2);
    byId("transfer-notes").value = row.reviewer_notes;
    byId("transfer-holds-reviewed").checked = review.holds_reviewed;
    byId("transfer-holds-note").value = review.holds_review_note;
    byId("transfer-existing-reference").textContent = "Imported claims only: "
      + (row.existing_help_scout_reference || "no prior reference supplied") + " / "
      + (row.help_scout_draft_id || "no draft ID supplied");
    byId("transfer-duplicate-status").value = review.duplicate_status;
    byId("transfer-duplicate-evidence").value = review.duplicate_evidence;
    byId("transfer-exact-approval").checked = false;
    const checkRoot = byId("transfer-checks"); checkRoot.replaceChildren(); checks.clear();
    for (const [key, prior] of Object.entries(review.checks)) {
      if (key !== "customer_approval") checks.set(key, inputCheck(checkRoot, key.replaceAll("_", " "), prior));
    }
    const customer = review.checks.customer_approval || {};
    byId("transfer-customer-decision").value = customer.decision || "unreviewed";
    byId("transfer-customer-conditional").checked = Boolean(customer.conditional_copy_reviewed);
    byId("transfer-customer-evidence").value = customer.evidence || "";
    const cartRoot = byId("transfer-carts"); cartRoot.replaceChildren(); carts.clear();
    cartRoot.append(element("p", row.alternate_relationship + " · " + row.cart_validation_status));
    const data = JSON.parse(row.cart_links_json);
    for (const cart of Array.isArray(data) ? data : []) {
      const block = element("div"); block.className = "draft-cart";
      block.append(element("pre", JSON.stringify(cart, null, 2)));
      // Structured evidence stays text; preview links require a user click. No cart is fetched here.
      if (cart && typeof cart.option_id === "string") carts.set(cart.option_id, inputCheck(block,
        "Verified exact cart contents and quantities for " + cart.option_id,
        review.carts[cart.option_id] || {}, true));
      cartRoot.append(block);
    }
    const result = selected.transfer;
    byId("transfer-result").textContent = result ? JSON.stringify(result, null, 2) : "No API transfer attempted.";
    byId("transfer-retry").hidden = !result?.retry_allowed;
    byId("transfer-verify").hidden = !result?.conversation_id;
    const linkRoot = byId("transfer-link"); linkRoot.replaceChildren();
    if (result?.web_link && /^https:\/\/secure\.helpscout\.net\/conversation\/[0-9/]+$/.test(result.web_link)) {
      const link = element("a", "Open created draft in Help Scout"); link.href = result.web_link;
      link.rel = "noopener noreferrer"; link.target = "_blank"; linkRoot.append(link);
    }
    controls();
  }
  function reviewValues() {
    return {recipient_verified: checked("transfer-recipient-verified"),
      recipient_provenance: value("transfer-recipient-provenance"),
      holds_reviewed: checked("transfer-holds-reviewed"), holds_review_note: value("transfer-holds-note"),
      duplicate_status: value("transfer-duplicate-status"),
      duplicate_evidence: value("transfer-duplicate-evidence"),
      checks: {...Object.fromEntries([...checks].map(([key, item]) => [key,
        {resolved: item.box.checked, evidence: item.note.value}])),
        customer_approval: {decision: value("transfer-customer-decision"),
          conditional_copy_reviewed: checked("transfer-customer-conditional"),
          evidence: value("transfer-customer-evidence")}},
      carts: Object.fromEntries([...carts].map(([key, item]) => [key,
        {verified: item.box.checked, evidence: item.note.value, observed_at_utc: item.observed.value}]))};
  }
  byId("transfer-preview").addEventListener("click", () => run(async () => {
    if (dirty) { message("Save or discard edits before importing."); return; }
    const file = byId("transfer-file").files[0];
    if (!file || file.size > 33554432) throw new Error("Choose a UTF-8 CSV no larger than 32 MiB.");
    const generation = ++fileGeneration;
    const csvText = new TextDecoder("utf-8", {fatal: true}).decode(await file.arrayBuffer());
    if (generation !== fileGeneration) return;
    const incoming = await request("preview_import", {csv_text: csvText});
    if (generation !== fileGeneration) {
      if (incoming.preview_token) await request("cancel_import", {preview_token: incoming.preview_token});
      return;
    }
    preview = incoming;
    byId("transfer-import-results").textContent = JSON.stringify(preview, null, 2);
    message(preview.can_commit ? "Preview ready. No rows or approvals have been saved." : "Fix the listed CSV errors; nothing was imported.");
  }));
  byId("transfer-file").addEventListener("change", () => {
    fileGeneration++; preview = null; controls();
  });
  byId("transfer-cancel").addEventListener("click", () => run(async () => {
    if (preview?.preview_token) await request("cancel_import", {preview_token: preview.preview_token});
    preview = null; fileGeneration++; byId("transfer-import-results").textContent = "Import canceled.";
  }));
  byId("transfer-commit").addEventListener("click", () => run(async () => {
    const result = await request("commit_import", {preview_token: preview.preview_token, revision: preview.revision});
    preview = null; byId("transfer-import-results").textContent = JSON.stringify(result, null, 2);
    await refresh(); message("Import complete. Local conflicts were retained; review each new row before approval.");
  }));
  byId("transfer-save").addEventListener("click", () => run(async () => {
    await request("edit", {order_id: selected.order_id, version: selected.version,
      fields: {selected_body_text: preserveBody(selected.row.selected_body_text, value("transfer-body")),
        recipient_email: value("transfer-recipient"), reviewer_notes: value("transfer-notes")},
      review: reviewValues()});
    await load(selected.order_id); await refresh(); message("Review saved. Check remaining gates before approving.");
  }));
  byId("transfer-discard").addEventListener("click", () => run(async () => {
    if (!dirty || globalThis.confirm("Discard unsaved edits for this draft?")) await load(selected.order_id);
  }));
  byId("transfer-exact-approval").addEventListener("change", controls);
  byId("transfer-approve").addEventListener("click", () => run(async () => {
    if (dirty || !checked("transfer-exact-approval")) return;
    await request("approve", {order_id: selected.order_id, version: selected.version,
      binding: selected.approval_binding, confirmation: "I_APPROVE_THIS_EXACT_HELP_SCOUT_DRAFT"});
    await load(selected.order_id); await refresh(); message("This exact version is approved for draft creation only.");
  }));
  const transfer = retry => run(async () => {
    if (dirty || !selected.approved) return;
    await request("transfer", {order_id: selected.order_id, version: selected.version,
      binding: selected.approval_binding, retry});
    await load(selected.order_id); await refresh(); message("Transfer result recorded. Review its status and returned link.");
  });
  byId("transfer-create").addEventListener("click", () => transfer(false));
  byId("transfer-retry").addEventListener("click", () => transfer(true));
  byId("transfer-verify").addEventListener("click", () => run(async () => {
    await request("verify_transfer", {order_id: selected.order_id, version: selected.version});
    await load(selected.order_id); await refresh();
  }));
  byId("transfer-refresh").addEventListener("click", () => run(async () => {
    await refresh(); if (selected && !dirty) await load(selected.order_id);
  }));
  byId("transfer-check-connection").addEventListener("click", () => run(async () => {
    await request("check_destination"); message("Configured mailbox and Jude user access verified (read only).");
  }));
  for (const id of ["body", "recipient", "recipient-provenance", "holds-note", "notes",
    "duplicate-evidence", "customer-evidence"])
    byId("transfer-" + id).addEventListener("input", markDirty);
  for (const id of ["recipient-verified", "holds-reviewed", "duplicate-status",
    "customer-decision", "customer-conditional"])
    byId("transfer-" + id).addEventListener("change", markDirty);
  globalThis.addEventListener("beforeunload", event => {
    if (dirty) { event.preventDefault(); event.returnValue = ""; }
  });
  run(async () => { await refresh(); message("Ready. Import is not approval; transfer creates drafts only."); });
})();
