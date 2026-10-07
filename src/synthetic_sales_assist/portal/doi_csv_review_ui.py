"""The existing portal frame with a closed, in-memory DOI CSV review flow.

No customer or source CSV fields are accepted by the renderer. The browser sends
the chosen pair once, then renders only the server's minimized projection.
"""

from __future__ import annotations

from synthetic_sales_assist.portal.dashboard_rendering import _page


def render_doi_csv_review_page(csrf_token: str, *, review_only: bool = True) -> bytes:
    return _page(
        route_name="doi_csv_review",
        heading="DOI split review",
        lede="Review ready/waiting evidence beside each full captured order total. Verify source facts before taking action.",
        csrf_token=csrf_token,
        presentation=False,
        review_only=review_only,
        body='''
<section class="dashboard-panel dashboard-warning" aria-label="Review scope">
  <h2>Split-review worklist</h2>
  <p>Full order totals provide captured order context, not split value or a revenue forecast. Confirmed patterns remain human-review evidence; they do not authorize splitting or fulfillment.</p>
  <details><summary>Evidence scope and limits</summary>
  <p>An apparent split pattern requires distinct physical purchase records on the apparent ready and waiting sides. Stock labels alone do not establish FULL allocation or verified outstanding quantity. Confirmed split criteria are not available from these captures.</p>
  <p>Future ETA dates and relative lead-time labels are signals for lead-time / availability research. Overdue status and lateness remain unknown without captured promise chronology. Stock-status observations require outstanding-quantity verification before any fulfillment conclusion.</p>
  <p>A snapshot older than 24 hours is marked stale as a review-refresh heuristic. This threshold is not an ECS business rule or a fulfillment service-level agreement.</p>
  <p>The default worklist includes only orders with an eligible captured sales-rep scope. Confirmed other-rep assignments are excluded; missing, conflicting or unmapped rep values are held for verification. DOI reviewer assignment is separate from the order-level ECS Sales Rep. Mixed and non-drop-ship orders remain supported. Rep scope does not determine fulfillment readiness, shipping dates or sales-credit entitlement.</p>
  <p>Unknown fields remain unknown. Product ETA and current stock are distinct captured fields. Stock at order time and order date have not been verified or captured. Service/charge purchases are counted separately from physical merchandise. Component gap placeholders are not purchases.</p>
  <p>Capture scope: the Details inventory fields and customer email only. Do not add names, addresses, phone numbers, payment details or Notes. Customer contact details and unrestricted capture text are omitted from the retained review. Only bounded, validated stock, date and status observations appear in source references.</p>
  </details>
</section>
<section class="dashboard-panel" aria-labelledby="doi-load-heading">
  <h2 id="doi-load-heading">Load a file pair</h2>
  <p>The session is shared by tabs of this local service. Start a new pair to clear the prior review before choosing files. Clear removes the retained review; stopping the service removes the session. It expires after 30 minutes.</p>
  <p>Hiding, closing or leaving this page does not clear the shared review. A load already accepted can remain available and be restored until Clear session, expiry or service shutdown. Aborting the page's request does not undo an accepted load.</p>
  <div class="dashboard-actions">
    <button type="button" id="doi-new-pair">Start a new file pair</button>
    <button type="button" id="doi-clear">Clear session</button>
  </div>
  <form id="doi-load-form" class="dashboard-form">
    <label class="dashboard-field"><span>Order summary CSV</span>
      <input type="file" id="doi-summary-file" accept=".csv,text/csv" disabled required>
    </label>
    <label class="dashboard-field"><span>Lines and components CSV</span>
      <input type="file" id="doi-lines-file" accept=".csv,text/csv" disabled required>
    </label>
    <p class="dashboard-field-hint">UTF-8 CSV only. Up to 1 MiB and 5,000 records per file, with up to 500 joined order keys. File names are not sent to the service.</p>
    <button type="submit" id="doi-load" disabled>Load and review</button>
  </form>
  <p id="doi-message" role="status" aria-live="polite">Checking the local session…</p>
  <noscript><p>JavaScript is needed to load a file pair. No review has been loaded by this page.</p></noscript>
</section>
<section id="doi-results" class="dashboard-panel" hidden aria-labelledby="doi-results-heading">
  <h2 id="doi-results-heading">Current session review</h2>
  <p id="doi-session-label" class="dashboard-meta"></p>
  <p id="doi-batch-holds" class="dashboard-warning"></p>
  <p id="doi-ownership-summary" class="dashboard-meta"></p>
  <p id="doi-currency-summary" class="dashboard-meta"></p>
  <details><summary>Capture counts and review context</summary><dl id="doi-counts"></dl>
  <p id="doi-triage-context" class="dashboard-meta"></p>
  <dl id="doi-triage-counts"></dl></details>
  <div class="dashboard-filter"><label class="dashboard-field"><span>Captured rep scope</span>
    <select id="doi-rep-scope">
      <option value="eligible">Eligible for my review</option>
      <option value="other">Excluded: confirmed other rep</option>
      <option value="held">Held: verify rep assignment</option>
      <option value="all">All captured orders for reconciliation</option>
    </select>
  </label><label class="dashboard-field"><span>Review group</span>
    <select id="doi-group">
      <option value="APPARENT_SPLIT_CANDIDATE">Apparent ready/waiting pattern</option>
      <option value="all">All split statuses</option>
      <option value="INSUFFICIENT_SPLIT_EVIDENCE">Insufficient split evidence</option>
      <option value="NO_SPLIT_PATTERN">No observed split pattern</option>
      <option value="CAPTURE_HELD">Capture held</option>
      <option value="currency_conflict">Currency conflicts (review held)</option>
      <option value="missing_evidence">Missing evidence / evaluation held</option>
      <option value="coverage_held">Visible coverage held</option>
      <option value="batch_quarantine">Batch quarantine</option>
    </select>
  </label><label class="dashboard-field"><span>Worklist order</span><select id="doi-sort"><option value="total">Full order total, highest first</option><option value="priority">Split status, then full order total</option><option value="source">Capture order</option></select></label></div>
  <p id="doi-group-count" role="status"></p>
  <div class="dashboard-table-wrap doi-worklist">
    <table><caption>Captured order split-review worklist</caption>
    <thead><tr><th scope="col">Order</th><th scope="col">Full captured total</th><th scope="col">Split status</th><th scope="col">Ready / waiting</th><th scope="col">Next verification and evidence</th></tr></thead>
    <tbody id="doi-orders"></tbody></table>
  </div>
  <p class="dashboard-meta">Source references are logical CSV record numbers, including the header as record 1. They identify the original capture records without displaying customer details or source URLs. Invalid and orphan records are counted above even when they cannot appear as a joined order.</p>
</section>''',
    )


DOI_CSV_REVIEW_JS = r'''"use strict";
(() => {
  const byId = id => document.getElementById(id);
  const form = byId("doi-load-form"), summary = byId("doi-summary-file"), lines = byId("doi-lines-file");
  const loadButton = byId("doi-load"), newButton = byId("doi-new-pair"), clearButton = byId("doi-clear");
  const results = byId("doi-results"), message = byId("doi-message"), group = byId("doi-group");
  const csrf = document.querySelector('meta[name="ssa-csrf-token"]').content;
  const api = "/api/v1/doi-csv-review/";
  let revision = null, current = null, preparing = false, busy = false, epoch = 0, controller = null;
  const statuses = new Set(["empty", "loaded", "quarantined", "error", "expired"]);
  const countLabels = {
    summary_records: "Parsed summary records", line_records: "Parsed line/component records", orders: "Joined order keys",
    invalid_summary_records: "Summary records with invalid order keys", invalid_line_records: "Line records with invalid order keys",
    orphan_line_records: "Line records without a summary", purchased_records: "Explicitly marked purchase records, including services",
    physical_purchased_records: "Physical merchandise purchase records", service_purchased_records: "Service/charge purchase records",
    component_records: "Explicit non-purchase components", placeholder_records: "Explicit non-purchase gap placeholders"
  };
  const friendly = {
    PRODUCTION_EVALUATION_NOT_PERFORMED: "Fulfillment evaluation has not been performed",
    READINESS_UNVERIFIED: "Readiness remains unverified", CSV_SAFETY_HOLD: "CSV safety review required",
    VISIBLE_COVERAGE_INCOMPLETE: "Visible coverage has not been verified",
    UNKNOWN_QUANTITY: "Quantity evidence missing", INVALID_QUANTITY: "Quantity format requires review",
    UNKNOWN_DROP_SHIP: "Drop-ship evidence missing", INVALID_ORDER_ID: "Order key requires review",
    DUPLICATE_SUMMARY: "Duplicate summary records", CONFLICTING_SUMMARY: "Conflicting summary records",
    DUPLICATE_LINE_ID: "Duplicate native line references", SOURCE_JOIN_MISMATCH: "Source references do not agree",
    TIMESTAMP_RANGE_UNSUPPORTED: "Capture time cannot be verified", SNAPSHOT_INCONSISTENT: "Capture consistency unverified"
  };
  const fixedCode = value => typeof value === "string" && /^[A-Z][A-Z0-9_]{0,95}$/.test(value);
  const scopeLabels = {OWNER:"Your rep assignment was captured",UNASSIGNED_WEB:"Captured unassigned web",OTHER_REP:"Excluded: another confirmed rep",FIELD_UNVERIFIED:"Held: rep field unverified",REP_MISSING:"Held: rep value missing",REP_UNMAPPED:"Held: rep value unmapped",REP_CONFLICT:"Held: conflicting rep observations",CAPTURE_UNVERIFIED:"Held: capture provenance unverified"};
  const eligibleScope = value => value === "OWNER" || value === "UNASSIGNED_WEB";
  const splitLabels = {CONFIRMED_SPLIT_CRITERIA:"Confirmed split criteria",APPARENT_SPLIT_CANDIDATE:"Apparent ready/waiting pattern",INSUFFICIENT_SPLIT_EVIDENCE:"Insufficient split evidence",NO_SPLIT_PATTERN:"No observed split pattern",CAPTURE_HELD:"Capture held"};
  const splitReasons = new Set("DISTINCT_READY_WAITING_LINES LABELS_ONLY NOT_CONFIRMED_FULL CAPTURE_COHERENCE_HOLD TERMINAL_ORDER_OBSERVED KNOWN_DS_EXCLUDED ZERO_REMAINING_EXCLUDED KIT_EVIDENCE_UNRESOLVED STOCK_LABEL_CONFLICT NO_DISTINCT_SPLIT_PATTERN TOTAL_INVALID TOTAL_MISMATCH TOTAL_UNKNOWN".split(" "));
  const splitMissing = new Set("ACTIVE_QUANTITY_UNVERIFIED FULL_ALLOCATION_NOT_CAPTURED DS_UNVERIFIED CURRENT_STOCK_UNVERIFIED KIT_COMPONENT_SCOPE_UNVERIFIED".split(" "));
  const currencySymbols = new Set(["$","US$","CA$","C$","A$","AU$","NZ$","USD","CAD","AUD","NZD","EUR","GBP","JPY","€","£","¥"]);
  function canonicalAmount(value) {
    if (typeof value !== "string" || !/^[0-9]{1,18}(?:\.[0-9]{1,6})?$/.test(value)) return null;
    const [integer,fraction=""] = value.split("."); const tail=fraction.replace(/0+$/,"");
    return integer.replace(/^0+(?=[0-9])/,"") + (tail ? "."+tail : "");
  }
  function validTotal(t) {
    if (!exactKeys(t,["amount","displayed","currency_code","currency_symbol","status"]) || !["VALID","UNKNOWN","INVALID","MISMATCH"].includes(t.status)
      || (t.currency_code !== null && (typeof t.currency_code !== "string" || !/^[A-Z]{3}$/.test(t.currency_code)))
      || (t.currency_symbol !== null && !currencySymbols.has(t.currency_symbol))) return false;
    if (t.status === "VALID" ? canonicalAmount(t.amount) !== t.amount : t.amount !== null) return false;
    if (t.displayed === null) return t.status !== "VALID";
    if (typeof t.displayed !== "string" || t.displayed.length>64 || t.displayed.trim()!==t.displayed) return false;
    let token=t.displayed;
    if (t.currency_symbol && token.startsWith(t.currency_symbol)) token=token.slice(t.currency_symbol.length).trim();
    else if (t.currency_symbol && token.endsWith(t.currency_symbol)) token=token.slice(0,-t.currency_symbol.length).trim();
    if (!/^(?:[0-9]{1,18}|[0-9]{1,3}(?:,[0-9]{3}){1,5})(?:\.[0-9]{1,6})?$/.test(token) || token.length>32) return false;
    return t.status !== "VALID" || canonicalAmount(token.replaceAll(",",""))===t.amount;
  }
  function validCurrency(c) {
    if(!Array.isArray(c)||c.length!==3||!["OWNER_USD","OBSERVED_USD","CONFLICT"].includes(c[2]))return false;
    const missing=v=>typeof v==="string"&&["","unknown","unknown - not displayed","not displayed"].includes(v.replace(/^[ \t\r\n]+|[ \t\r\n]+$/g,"").toLowerCase());
    if(c[0]!==null&&(typeof c[0]!=="string"||c[0].length>40||!missing(c[0])&&!/^[A-Z]{3}$/.test(c[0])))return false;
    if(c[1]!==null&&(typeof c[1]!=="string"||c[1].length>40||!missing(c[1])&&!currencySymbols.has(c[1])))return false;
    const conflict=c[0]===null||c[1]===null||!missing(c[0])&&c[0]!=="USD"||!missing(c[1])&&c[1]!=="$";
    return c[2]===(conflict?"CONFLICT":c[0]==="USD"?"OBSERVED_USD":"OWNER_USD");
  }
  function validConfirmation(o,asOf) {
    const p=o.rep_confirmation;
    return p===undefined||o.rep_scope==="OTHER_REP"&&exactKeys(p,["confirmed_at","evidence_reference"])
      &&utc(p.confirmed_at)&&typeof p.evidence_reference==="string"&&/^(?:Sentinel_[a-f0-9]{32}|SYN-[A-Z0-9_-]{1,64})$/.test(p.evidence_reference)
      &&Date.parse(p.confirmed_at)<=Date.parse(asOf)&&o.evidence.capture_time!==null&&Date.parse(o.evidence.capture_time)<=Date.parse(p.confirmed_at);
  }
  function validSplit(t, order) {
    if (!exactKeys(t,["schema","status","ready_line_ordinals","waiting_line_ordinals","unresolved_line_ordinals","reason_codes","missing_fact_codes","total","quantity_verified","decision_eligible","line_items"])
      || t.schema!=="doi-split-review/v1" || !Object.hasOwn(splitLabels,t.status) || t.status==="CONFIRMED_SPLIT_CRITERIA"
      || t.quantity_verified!==false || t.decision_eligible!==false || !validTotal(t.total)
      || !closedList(t.reason_codes,splitReasons,32) || !closedList(t.missing_fact_codes,splitMissing,16)) return false;
    if (![t.ready_line_ordinals,t.waiting_line_ordinals,t.unresolved_line_ordinals].every(references)) return false;
    const all=[...t.ready_line_ordinals,...t.waiting_line_ordinals,...t.unresolved_line_ordinals];
    if (new Set(all).size!==all.length || !all.every(n=>order.line_record_ordinals.includes(n))) return false;
    const candidate=t.ready_line_ordinals.length>0&&t.waiting_line_ordinals.length>0;
    if ((t.status==="APPARENT_SPLIT_CANDIDATE")!==candidate || t.status==="CAPTURE_HELD"&&(t.ready_line_ordinals.length||t.waiting_line_ordinals.length)) return false;
    if(t.reason_codes.some(code=>["CAPTURE_COHERENCE_HOLD","TERMINAL_ORDER_OBSERVED"].includes(code))&&t.status!=="CAPTURE_HELD")return false;
    return Array.isArray(t.line_items)&&t.line_items.length<=5000&&t.line_items.every(item=>exactKeys(item,["record_ordinal","es_number","current_stock","ds"])
      && natural(item.record_ordinal)&&item.record_ordinal>=2&&item.record_ordinal<=5001&&order.line_record_ordinals.includes(item.record_ordinal)
      && (item.es_number===null||typeof item.es_number==="string"&&/^[1-9][0-9]{0,63}$/.test(item.es_number))
      && (item.current_stock===null||safeObserved("current_stock_icon_exact",item.current_stock))&&["YES","NO","UNKNOWN"].includes(item.ds))
      &&new Set(t.line_items.map(item=>item.record_ordinal)).size===t.line_items.length&&all.every(n=>t.line_items.some(item=>item.record_ordinal===n))
      &&t.ready_line_ordinals.every(n=>{const item=t.line_items.find(line=>line.record_ordinal===n);return item.ds!=="YES"&&["in stock","instock","ships today","shipstoday"].includes((item.current_stock||"").toLowerCase());})
      &&t.waiting_line_ordinals.every(n=>{const item=t.line_items.find(line=>line.record_ordinal===n);return item.ds!=="YES"&&waitingObserved(item.current_stock,order);});
  }
  const natural = value => Number.isSafeInteger(value) && value >= 0;
  const references = value => Array.isArray(value) && value.length <= 5000 && value.every(x => natural(x) && x >= 2);
  const codeList = value => Array.isArray(value) && value.length <= 256 && value.every(fixedCode);
  const exactKeys = (value, keys) => value && typeof value === "object" && !Array.isArray(value)
    && Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));
  function sourceCompare(a,b) {
    return (a.summary_record_ordinals[0]||5002)-(b.summary_record_ordinals[0]||5002)
      || a.order_id.length-b.order_id.length || (a.order_id<b.order_id?-1:a.order_id>b.order_id?1:0);
  }
  function totalCompare(a,b) {
    const left=a.split.total, right=b.split.total, lv=left.status==="VALID", rv=right.status==="VALID";
    if(lv!==rv)return lv?-1:1;
    if(lv){
      const units=t=>{const [whole,fraction=""]=t.amount.split(".");return BigInt(whole+fraction.padEnd(6,"0"));};
      const la=units(left), ra=units(right);
      if(la!==ra)return la>ra?-1:1;
    }
    return sourceCompare(a,b);
  }
  function matchesRepScope(order,repFilter) {
    return repFilter==="all"||repFilter==="eligible"&&eligibleScope(order.rep_scope)
      ||repFilter==="other"&&order.rep_scope==="OTHER_REP"
      ||repFilter==="held"&&!eligibleScope(order.rep_scope)&&order.rep_scope!=="OTHER_REP";
  }
  function currencyConflictCounts(orders,repFilter) {
    const conflicts=orders.filter(o=>o.currency[2]==="CONFLICT");
    return {total:conflicts.length,selected_scope:conflicts.filter(o=>matchesRepScope(o,repFilter)).length};
  }
  function worklistOrders(orders,repFilter,splitFilter,sortMode) {
    const picked=orders.filter(o=>matchesRepScope(o,repFilter)
      &&(repFilter!=="eligible"||o.currency[2]!=="CONFLICT"||splitFilter==="currency_conflict")
      &&(splitFilter==="all"||o.split.status===splitFilter||splitFilter==="currency_conflict"&&o.currency[2]==="CONFLICT"||splitFilter==="missing_evidence"&&!o.evidence_complete
      ||splitFilter==="coverage_held"&&!o.visible_coverage_complete||splitFilter==="batch_quarantine"&&o.holds.includes("GLOBAL_INPUT_HOLD")));
    const ranks={APPARENT_SPLIT_CANDIDATE:0,INSUFFICIENT_SPLIT_EVIDENCE:1,NO_SPLIT_PATTERN:2,CAPTURE_HELD:3};
    return picked.sort(sortMode==="source"?sourceCompare:sortMode==="priority"?(a,b)=>ranks[a.split.status]-ranks[b.split.status]||totalCompare(a,b):totalCompare);
  }
  const utc = value => typeof value === "string" && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|\+00:00)$/.test(value) && calendarDate(value.slice(0,10)) && Number.isFinite(Date.parse(value));
  const reasons = new Set("GLOBAL_INPUT_HOLD STRUCTURAL_INPUT_HOLD CAPTURE_FAILED CAPTURE_TIME_MISSING CAPTURE_TIME_FUTURE CAPTURE_STALE ETA_YEAR_ANOMALY ETA_BEFORE_CAPTURE ETA_DATE_CONFLICT ETA_DATE_INVALID PRODUCT_CURRENT_LABEL_CONTRAST WAREHOUSE_TRANSFER_CURRENT_STOCK NEGATIVE_OPAQUE_OS_CURRENT_STOCK APPARENT_CURRENT_STOCK OBSERVED_TERMINAL_PROGRESS_SUPPRESSED OBSERVED_LEAD_TIME_LABEL OBSERVED_RELATIVE_SHIP_LABEL OBSERVED_FUTURE_ETA KIT_COMPONENT_EVIDENCE_UNRESOLVED UNKNOWN_FACTS NO_POSITIVE_SIGNAL".split(" "));
  reasons.add("CAPTURE_INCOMPLETE_SOURCE");
  const missingFacts = new Set("AT_ORDER_STOCK_NOT_CAPTURED ORDER_DATE_NOT_CAPTURED DS_NOT_CONFIRMED QUANTITY_NOT_CONFIRMED ALLOCATION_NOT_CAPTURED CURRENCY_NOT_CONFIRMED KIT_COMPONENT_EVIDENCE_UNRESOLVED CURRENT_STOCK_NOT_CAPTURED".split(" "));
  const evidenceLabels = {
    order_status: "Observed order status", captured_at_america_new_york: "Capture timestamp",
    expected_arrival_date_exact: "Expected arrival", current_expected_ship_date_exact: "Current expected ship date",
    revised_ship_date_exact: "Revised ship date", stock_eta_exact: "Summary stock ETA",
    product_eta_exact: "Product ETA label", current_stock_icon_exact: "Current stock label",
    dated_line_eta: "Dated line ETA", OS_displayed: "Opaque OS observation", drop_ship: "Drop-ship observation",
    remaining_quantity: "Remaining quantity observation", component_coverage_complete: "Component coverage observation"
  };
  const stockLabels = new Set(["in stock", "instock", "ships today", "shipstoday", "backordered", "back ordered", "back order", "special order no guaranteed eta", "special order - no guaranteed eta", "special order: no guaranteed eta", "specialorder: noguaranteedeta", "specialorder noguaranteedeta", "nla", "vendor stock", "in stock at vendor", "in stock at supplier", "instockatvendor", "in stock (at vendor)", "instock(atvendor)"]);
  function calendarDate(value) {
    let match, year, month, day;
    const months = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"];
    if ((match = /^([0-9]{4})-([0-9]{2})-([0-9]{2})$/.exec(value))) [year,month,day] = [Number(match[1]),Number(match[2]),Number(match[3])];
    else if ((match = /^([0-9]{1,2})\/([0-9]{1,2})\/([0-9]{4})$/.exec(value))) [year,month,day] = [Number(match[3]),Number(match[1]),Number(match[2])];
    else if ((match = /^([0-9]{1,2})-([A-Za-z]{3})-([0-9]{4})$/.exec(value))) [year,month,day] = [Number(match[3]),months.indexOf(match[2].toLowerCase())+1,Number(match[1])];
    else if ((match = /^([A-Za-z]{3}) ([0-9]{1,2}), ([0-9]{4})$/.exec(value))) [year,month,day] = [Number(match[3]),months.indexOf(match[1].toLowerCase())+1,Number(match[2])];
    else return false;
    const days = [31,year%4===0&&(year%100!==0||year%400===0)?29:28,31,30,31,30,31,31,30,31,30,31];
    return year>=1 && year<=9999 && month>=1 && month<=12 && day>=1 && day<=days[month-1];
  }
  function sourceDateKey(value) {
    const text=value.replace(/^ships on /i,"").replace(/ \([0-9]{1,6}\)$/,"");
    if(!calendarDate(text))return null;
    const months=["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"];
    let m,year,month,day;
    if((m=/^([0-9]{4})-([0-9]{2})-([0-9]{2})$/.exec(text)))[year,month,day]=[m[1],m[2],m[3]];
    else if((m=/^([0-9]{1,2})\/([0-9]{1,2})\/([0-9]{4})$/.exec(text)))[year,month,day]=[m[3],m[1],m[2]];
    else if((m=/^([0-9]{1,2})-([A-Za-z]{3})-([0-9]{4})$/.exec(text)))[year,month,day]=[m[3],String(months.indexOf(m[2].toLowerCase())+1),m[1]];
    else {m=/^([A-Za-z]{3}) ([0-9]{1,2}), ([0-9]{4})$/.exec(text);[year,month,day]=[m[3],String(months.indexOf(m[1].toLowerCase())+1),m[2]];}
    return year+"-"+month.padStart(2,"0")+"-"+day.padStart(2,"0");
  }
  function waitingObserved(value, order) {
    if(typeof value!=="string")return false;
    const lower=value.toLowerCase();
    if(["backordered","back ordered","back order","special order no guaranteed eta","special order - no guaranteed eta","special order: no guaranteed eta","specialorder: noguaranteedeta","specialorder noguaranteedeta","nla"].includes(lower)
      || /^ships ?in ?[1-9][0-9]{0,2}(?:-[1-9][0-9]{0,2})? ?(?:business ?)?days?$/.test(lower))return true;
    if(!lower.startsWith("ships on "))return false;
    const date=sourceDateKey(value);
    const capture=order.evidence?.evidence_references?.find(ref=>ref.scope==="summary"&&ref.field==="captured_at_america_new_york"&&!ref.redacted)?.observed_value;
    return date!==null&&!date.startsWith("1999-")&&safeObserved("captured_at_america_new_york",capture)&&date>=capture.slice(0,10);
  }
  function safeObserved(field, value) {
    if (typeof value !== "string" || !value.length || value.length > 64 || !/^[\x20-\x7e]+$/.test(value) || value.trim() !== value) return false;
    const lower = value.toLowerCase();
    if (["OS_displayed", "remaining_quantity"].includes(field)) return /^-?[0-9]+(?:\.[0-9]+)?$/.test(value);
    if (field === "captured_at_america_new_york") return /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})$/.test(value) && calendarDate(value.slice(0,10)) && Number.isFinite(Date.parse(value));
    if (field === "drop_ship") return ["yes", "no", "true", "false"].includes(lower);
    if (field === "component_coverage_complete") return ["yes", "no", "true", "false", "complete", "verified"].includes(lower);
    if (field === "order_status") return ["active", "batched", "warehouse transfer", "warehousetransfer", "shipped", "canceled", "cancelled"].includes(lower);
    if (stockLabels.has(lower) || /^ships ?in ?[1-9][0-9]{0,2}(?:-[1-9][0-9]{0,2})? ?(?:business ?)?days?$/.test(lower)) return true;
    const dateText = value.replace(/^ships on /i, "").replace(/ \([0-9]{1,6}\)$/, "");
    return calendarDate(dateText);
  }
  const closedList = (value, allowed, limit) => Array.isArray(value) && value.length <= limit
    && value.every(item => allowed.has(item)) && new Set(value).size === value.length;
  function validEvidence(e) {
    if (!exactKeys(e,["reason_codes","missing_fact_codes","evidence_references","evidence_omitted_count","capture_time","snapshot_age_seconds","snapshot_age_status"])
      || !closedList(e.reason_codes,reasons,12)||!closedList(e.missing_fact_codes,missingFacts,8)||!natural(e.evidence_omitted_count)
      || (e.capture_time!==null&&!utc(e.capture_time)) || (e.snapshot_age_seconds!==null&&!natural(e.snapshot_age_seconds))) return false;
    const status=e.snapshot_age_status, age=e.snapshot_age_seconds, capture=e.capture_time;
    if (status==="KNOWN"||status==="STALE") {if(age===null||capture===null||(status==="KNOWN"?age>86400:age<86400||!e.reason_codes.includes("CAPTURE_STALE")))return false;}
    else if(status==="FUTURE_CAPTURE") {if(age!==null||capture===null||!e.reason_codes.includes("CAPTURE_TIME_FUTURE"))return false;}
    else if(status!=="UNVERIFIED"||age!==null||capture!==null||!e.reason_codes.includes("CAPTURE_TIME_MISSING"))return false;
    return Array.isArray(e.evidence_references)&&e.evidence_references.length<=6&&e.evidence_references.every(ref=>
      exactKeys(ref,["scope","record_ordinal","field","observed_value","redacted"])&&["summary","lines"].includes(ref.scope)
      && natural(ref.record_ordinal)&&ref.record_ordinal>=2&&ref.record_ordinal<=5001&&Object.hasOwn(evidenceLabels,ref.field)&&typeof ref.redacted==="boolean"
      &&(ref.observed_value===null?ref.redacted:!ref.redacted&&safeObserved(ref.field,ref.observed_value)));
  }
  function validContext(t, orderCount) {
    return exactKeys(t,["schema","as_of","order_count","status_counts","confirmed_split_count","decision_eligible_count"])
      &&t.schema==="doi-split-review/v1"&&(t.as_of===null?orderCount===0:utc(t.as_of))&&t.order_count===orderCount
      &&t.confirmed_split_count===0&&t.decision_eligible_count===0&&exactKeys(t.status_counts,Object.keys(splitLabels))
      &&Object.values(t.status_counts).every(natural)&&Object.values(t.status_counts).reduce((a,b)=>a+b,0)===orderCount;
  }
  function validState(s) {
    return exactKeys(s,["schema", "revision", "status", "counts", "groups", "orders", "batch_holds", "error_code", "expires_in_seconds", "split_review", "ownership_review"])
      && s.schema === "doi-csv-review/v5" && natural(s.revision) && statuses.has(s.status)
      && natural(s.expires_in_seconds) && s.counts && Object.keys(countLabels).every(k => natural(s.counts[k]))
      && s.groups && natural(s.groups.review) && natural(s.groups.quarantined)
      && codeList(s.batch_holds) && (s.error_code === null || fixedCode(s.error_code))
      && Array.isArray(s.orders) && s.orders.length <= 500 && s.orders.every(o =>
        exactKeys(o,["order_id", "rep_scope", "currency", "summary_record_ordinals", "line_record_ordinals", "visible_coverage_complete", "evidence_complete", "decision_eligible", "holds", "reviewer_assignment", "sales_credit_observed", "sales_credit_entitlement", "split", "evidence",...(o.rep_confirmation===undefined?[]:["rep_confirmation"])])
        && typeof o.rep_scope === "string" && Object.hasOwn(scopeLabels,o.rep_scope)
        && typeof o.order_id === "string" && /^[1-9][0-9]{0,127}$/.test(o.order_id)
        && references(o.summary_record_ordinals) && references(o.line_record_ordinals)
        && typeof o.visible_coverage_complete === "boolean" && o.evidence_complete === false
        && o.decision_eligible === false && codeList(o.holds)
        && (o.reviewer_assignment === "Jude" || o.reviewer_assignment === null)
        && ["OBSERVED", "UNKNOWN"].includes(o.sales_credit_observed)
        && o.sales_credit_entitlement === "UNINTERPRETED" && validSplit(o.split,o) && validEvidence(o.evidence)
        &&validCurrency(o.currency)&&(o.currency[2]==="CONFLICT")===o.holds.includes("CURRENCY_CONFLICT")&&validConfirmation(o,s.split_review?.as_of)
        && o.evidence.evidence_references.every(ref => (ref.scope === "summary" ? o.summary_record_ordinals : o.line_record_ordinals).includes(ref.record_ordinal)))
      && validContext(s.split_review, s.orders.length)
      && validOwnership(s.ownership_review,s.orders)
      && Object.keys(splitLabels).every(key => s.split_review.status_counts[key] === s.orders.filter(o => o.split.status === key).length);
  }
  function validOwnership(t,orders) {
    if(!exactKeys(t,["schema","order_count","eligible_count","excluded_count","held_count","status_counts","eligible_split_counts"])
      ||t.schema!=="doi-rep-scope/v1"||t.order_count!==orders.length
      ||![t.order_count,t.eligible_count,t.excluded_count,t.held_count].every(natural)
      ||!exactKeys(t.status_counts,Object.keys(scopeLabels))||!Object.values(t.status_counts).every(natural)
      ||!exactKeys(t.eligible_split_counts,Object.keys(splitLabels))||!Object.values(t.eligible_split_counts).every(natural))return false;
    const eligible=orders.filter(o=>eligibleScope(o.rep_scope));
    return t.eligible_count===eligible.length&&t.excluded_count===orders.filter(o=>o.rep_scope==="OTHER_REP").length
      &&t.held_count===orders.length-t.eligible_count-t.excluded_count
      &&Object.keys(scopeLabels).every(key=>t.status_counts[key]===orders.filter(o=>o.rep_scope===key).length)
      &&Object.keys(splitLabels).every(key=>t.eligible_split_counts[key]===eligible.filter(o=>o.split.status===key).length);
  }
  const labelCode = code => friendly[code] || code.toLowerCase().replaceAll("_", " ");
  function blank() {
    current = null; results.hidden = true;
    byId("doi-orders").replaceChildren(); byId("doi-counts").replaceChildren();
    byId("doi-triage-counts").replaceChildren(); byId("doi-triage-context").textContent = "";
    byId("doi-batch-holds").textContent = ""; byId("doi-session-label").textContent = "";
    byId("doi-ownership-summary").textContent = "";
    byId("doi-currency-summary").textContent = "";
  }
  function resetFiles() { summary.value = ""; lines.value = ""; }
  function controls() {
    newButton.disabled = busy || revision === null; clearButton.disabled = busy || revision === null;
    summary.disabled = busy || !preparing; lines.disabled = busy || !preparing;
    loadButton.disabled = busy || !preparing || !summary.files.length || !lines.files.length;
  }
  function add(parent, tag, text) { const node = document.createElement(tag); node.textContent = text; parent.append(node); return node; }
  function totalLabel(t,currency) {
    const code=currency[2]==="CONFLICT"?"currency conflict":"USD";
    if(t.status==="VALID") return `${t.displayed} (${code})`;
    return `${t.status.toLowerCase()}: ${t.displayed||"not captured"} (${code})`;
  }
  function nextCheck(order) {
    if(!eligibleScope(order.rep_scope))return scopeLabels[order.rep_scope]+". Outside the default worklist; reconcile the captured rep field.";
    if(order.split.status==="CAPTURE_HELD") return "Resolve capture conflicts before split review.";
    if(order.split.status==="APPARENT_SPLIT_CANDIDATE") return "Verify outstanding quantity, DS scope and full allocation for each side.";
    if(order.split.status==="INSUFFICIENT_SPLIT_EVIDENCE") return "Verify missing stock or kit evidence and outstanding quantities.";
    return "Verify source scope; no distinct ready/waiting pattern is established.";
  }
  function renderEvidence(td, order) {
    const e=order.evidence, split=order.split;
    add(td,"p",nextCheck(order)).className="doi-next-check";
    const details=add(td,"details","");add(details,"summary","Line evidence and source checks");
    const side=(title,ordinals)=>{
      add(details,"h3",title);
      const list=add(details,"ul","");
      for(const ordinal of ordinals) {
        const item=split.line_items.find(line=>line.record_ordinal===ordinal);
        add(list,"li",`Lines record ${ordinal}; ES ${item&&item.es_number!==null?item.es_number:"not captured"}; current stock: ${item&&item.current_stock!==null?item.current_stock:"unverified"}; DS: ${item?item.ds.toLowerCase():"unknown"}.`);
      }
      if(!ordinals.length)add(list,"li","No source records on this side.");
    };
    side("Apparent ready — allocation unverified",split.ready_line_ordinals);
    side("Apparent waiting — verify current label",split.waiting_line_ordinals);
    if(split.unresolved_line_ordinals.length)side("Unresolved source records",split.unresolved_line_ordinals);
    const assigned=new Set([...split.ready_line_ordinals,...split.waiting_line_ordinals,...split.unresolved_line_ordinals]);
    const other=split.line_items.filter(item=>!assigned.has(item.record_ordinal)).map(item=>item.record_ordinal);
    if(other.length)side("Other physical purchases — outside the apparent sides",other);
    add(details,"p",`Summary records: ${order.summary_record_ordinals.join(", ")||"none"}; lines: ${order.line_record_ordinals.join(", ")||"none"}.`);
    add(details,"p",`Capture time: ${e.capture_time||"unverified"}. Snapshot age at the stated reference time: ${e.snapshot_age_seconds===null?"unverified":e.snapshot_age_seconds+" seconds"}; ${e.snapshot_age_status.toLowerCase().replaceAll("_"," ")}.`);
    add(details,"p","Split reasons: "+split.reason_codes.map(labelCode).join("; "));
    add(details,"p","Missing split facts: "+split.missing_fact_codes.map(labelCode).join("; "));
    add(details,"p","Other source warnings: "+e.reason_codes.map(labelCode).join("; "));
    add(details,"p","Other missing facts: "+e.missing_fact_codes.map(labelCode).join("; "));
    const list=add(details,"ul","");
    for(const ref of e.evidence_references)add(list,"li",`${ref.scope==="summary"?"Summary":"Lines"} record ${ref.record_ordinal}, ${evidenceLabels[ref.field]} (${ref.field}): ${ref.redacted?"observation redacted":ref.observed_value}`);
    if(e.evidence_omitted_count)add(details,"p",`${e.evidence_omitted_count} additional references omitted from this minimized view.`);
    add(details,"p",`Captured rep scope: ${scopeLabels[order.rep_scope]}. Source: ECS Sales Rep in summary records ${order.summary_record_ordinals.join(", ")||"none"}. DOI reviewer: ${order.reviewer_assignment||"unverified"}. Sales-credit entitlement unreviewed. Evidence incomplete; decision held.`);
    if(order.rep_confirmation)add(details,"p",`Owner confirmed other-rep assignment at ${order.rep_confirmation.confirmed_at}; evidence ${order.rep_confirmation.evidence_reference}. Bound to this captured record.`);
    const c=order.currency;
    add(details,"p",`${c[2]==="OWNER_USD"?"USD from owner-confirmed ECS policy":c[2]==="OBSERVED_USD"?"USD observed in capture":"Currency conflict: review held"}. Captured code: ${c[0]===null?"invalid observation redacted":c[0]||"blank"}; captured symbol: ${c[1]===null?"invalid observation redacted":c[1]||"blank"}. No conversion.`);
    if(order.holds.length)add(details,"p","Review holds: "+order.holds.map(labelCode).join("; "));
  }
  function renderOrders() {
    const body=byId("doi-orders");body.replaceChildren();if(!current)return;
    const repFilter=byId("doi-rep-scope").value;
    const picked=worklistOrders(current.orders,repFilter,group.value,byId("doi-sort").value);
    const currencyCounts=currencyConflictCounts(current.orders,repFilter);
    byId("doi-currency-summary").textContent=`Currency conflicts: ${currencyCounts.selected_scope} in the selected rep scope; ${currencyCounts.total} across all captured orders. Choose the Currency conflicts review group to inspect them. Select All captured orders for reconciliation to include every rep scope. Currency conflicts remain held and do not change rep assignments or split classifications.`;
    byId("doi-group-count").textContent=`${picked.length} visible of ${current.orders.length} captured orders; ${current.ownership_review.eligible_count} eligible for your review. Default order: exact nominal full total, highest first; currencies are not converted.`;
    for(const order of picked) {
      const tr=add(body,"tr","");add(tr,"td",order.order_id);add(tr,"td",totalLabel(order.split.total,order.currency));
      add(tr,"td",splitLabels[order.split.status]);
      add(tr,"td",`${order.split.ready_line_ordinals.length} apparent ready / ${order.split.waiting_line_ordinals.length} apparent waiting${order.split.unresolved_line_ordinals.length?" / "+order.split.unresolved_line_ordinals.length+" unresolved":""}`);
      renderEvidence(add(tr,"td",""),order);
    }
    if(!picked.length){const tr=add(body,"tr","");add(tr,"td","No orders match this split-review filter.").colSpan=5;}
  }
  function applyState(s, justLoaded = false) {
    if (!validState(s)) throw new Error("INVALID_RESPONSE");
    revision = s.revision; blank();
    if (s.status === "loaded" || s.status === "quarantined") {
      current = s; results.hidden = false;
      byId("doi-session-label").textContent = `Session revision ${s.revision} · expires in ${Math.ceil(s.expires_in_seconds / 60)} minutes · ${s.batch_holds.length ? "batch quarantined" : s.status === "quarantined" ? "coverage held" : "evidence review loaded"}`;
      byId("doi-batch-holds").textContent = s.batch_holds.length ? "Batch holds: " + s.batch_holds.map(labelCode).join("; ") + ". Joined order keys remain accounted for in the reconciliation filters." + (s.batch_holds.includes("MALFORMED_CSV") ? " Counts cover the parsed prefix only; total input record coverage is unknown." : "") : "No batch-level CSV safety holds. Every order remains held for evidence review and fulfillment evaluation.";
      byId("doi-ownership-summary").textContent=`Captured rep scope: ${s.ownership_review.eligible_count} eligible; ${s.ownership_review.excluded_count} confirmed other-rep assignments excluded; ${s.ownership_review.held_count} held for verification. All ${s.ownership_review.order_count} orders remain accounted for. Rep scope is separate from sales-credit entitlement.`;
      for (const [key, label] of Object.entries(countLabels)) { add(byId("doi-counts"), "dt", label); add(byId("doi-counts"), "dd", String(s.counts[key])); }
      byId("doi-triage-context").textContent = `Snapshot ages measured at ${s.split_review.as_of || "an unverified reference time"}. Capture age is not order age. Full totals are captured order context; no split value or currency conversion is calculated.`;
      for (const [key,label] of Object.entries(splitLabels)) { add(byId("doi-triage-counts"), "dt", "Eligible ownership: "+label); add(byId("doi-triage-counts"), "dd", String(s.ownership_review.eligible_split_counts[key])); }
      for (const [key,label] of Object.entries(scopeLabels)) { add(byId("doi-triage-counts"), "dt", label); add(byId("doi-triage-counts"), "dd", String(s.ownership_review.status_counts[key])); }
      renderOrders();
      message.textContent = (justLoaded ? "This pair was reviewed. " : "Existing current session review restored. ") + (s.batch_holds.length ? "The batch has holds and authorizes no decisions." : s.status === "quarantined" ? "Coverage is held. Check each order's evidence gaps." : "No fulfillment or sales-credit decision has been made.");
    } else {
      message.textContent = s.status === "expired" ? "The local review expired. Start a new pair to reload."
        : s.status === "error" ? "The pair could not be reviewed. The previous review was cleared. " + labelCode(s.error_code || "REVIEW_INTERNAL_ERROR") + ". Start a new pair and check the CSV format and limits."
        : "No pair is loaded. Start a new file pair to choose captures.";
    }
  }
  async function request(path, payload, signal) {
    const options = {method: payload === undefined ? "GET" : "POST", cache: "no-store", credentials: "same-origin", signal};
    if (payload !== undefined) { options.headers = {"Content-Type": "application/json", "X-SSA-CSRF-Token": csrf}; options.body = JSON.stringify(payload); }
    const response = await fetch(api + path, options);
    if (!response.ok) throw new Error("REQUEST_REJECTED");
    return response.json();
  }
  async function sync() {
    if (busy) return;
    const run = ++epoch;
    try { const state = await request("state"); if (run !== epoch) return;
      if (revision !== state.revision) { preparing = false; resetFiles(); applyState(state); }
      else if (current) applyState(state);
      controls();
    } catch { if (run !== epoch) return; blank(); revision = null; preparing = false; resetFiles(); controls(); message.textContent = "Cannot confirm the current local session. Reconnect or reload this page before choosing files."; }
  }
  async function clearSession(beginPair) {
    if (busy || revision === null) return;
    const run = ++epoch; busy = true; preparing = false; blank(); resetFiles(); controls();
    message.textContent = "Clearing the previous review…";
    try { const state = await request("clear", {revision}); if (run !== epoch) return; applyState(state); preparing = beginPair;
      if (beginPair) message.textContent = "Previous review cleared. Choose both CSV files, then load the pair.";
    } catch { if (run !== epoch) return; revision = null; message.textContent = "Clear was not confirmed. Rechecking the current session before another load."; }
    finally { if (run === epoch) { busy = false; controls(); if (revision === null) await sync(); } }
  }
  newButton.addEventListener("click", () => clearSession(true));
  clearButton.addEventListener("click", () => clearSession(false));
  for (const input of [summary, lines]) {
    input.addEventListener("change", () => { blank(); controls(); message.textContent = "Choose both captures before loading. No new pair has been reviewed yet."; });
    input.addEventListener("cancel", () => { blank(); resetFiles(); controls(); message.textContent = "File selection cancelled. Both selected files were cleared; no new pair has been loaded. An existing shared review can remain available until Clear session, expiry or service shutdown."; });
  }
  form.addEventListener("submit", async event => {
    event.preventDefault(); if (busy || !preparing || revision === null || !summary.files.length || !lines.files.length) return;
    const run = ++epoch; busy = true; preparing = false; blank(); controls();
    const left = summary.files[0], right = lines.files[0]; controller = new AbortController();
    message.textContent = "Loading and checking this pair…";
    try {
      if (left.size > 1048576 || right.size > 1048576) throw new Error("FILE_LIMIT");
      const decode = async file => new TextDecoder("utf-8", {fatal:true}).decode(await file.arrayBuffer());
      const [summary_csv, lines_csv] = await Promise.all([decode(left), decode(right)]);
      if (run !== epoch) return;
      const state = await request("load", {revision, summary_csv, lines_csv}, controller.signal);
      if (run !== epoch) return; applyState(state, true);
    } catch {
      if (run !== epoch) return; blank(); revision = null;
      message.textContent = "The load was not confirmed. Rechecking the session; the previous pair is not displayed.";
    } finally {
      if (run === epoch) { controller = null; resetFiles(); busy = false; controls(); if (revision === null) await sync(); }
    }
  });
  group.addEventListener("change", renderOrders);
  byId("doi-rep-scope").addEventListener("change", renderOrders);
  byId("doi-sort").addEventListener("change", renderOrders);
  window.addEventListener("pagehide", () => { ++epoch; if (controller) controller.abort(); controller = null; busy = false; preparing = false; revision = null; resetFiles(); blank(); });
  window.addEventListener("pageshow", () => { blank(); preparing = false; revision = null; resetFiles(); controls(); void sync(); });
  window.setInterval(() => { if (!document.hidden && !busy) void sync(); }, 10000);
  controls(); void sync();
})();
'''
