// SYNTHETIC-SALES-ASSIST-AUTHORED-M5
"use strict";
(() => {
  const maxReviewResponseBytes = __DOI_RESPONSE_LIMIT_BYTES__;
  const byId = id => document.getElementById(id);
  const form = byId("doi-load-form"), summary = byId("doi-summary-file"), lines = byId("doi-lines-file");
  const loadButton = byId("doi-load"), newButton = byId("doi-new-pair"), clearButton = byId("doi-clear");
  const results = byId("doi-results"), message = byId("doi-message"), group = byId("doi-group");
  const csrf = document.querySelector('meta[name="ssa-csrf-token"]').content;
  const api = "/api/v1/doi-csv-review/";
  let revision = null, current = null, preparing = false, busy = false, epoch = 0, controller = null;
  let reviewedState=null, reviewedById=new Map(), marksBusy=false, marksError="";
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
  const discoveryLabels = {NONE:"",HELD_MIXED_LABELS:"Held ready/waiting pattern",STOCK_COUNTER_CLUE:"Stock-counter clue only"};
  const discoveryBlockingHolds = new Set("STRUCTURAL_COVERAGE_INCOMPLETE LINE_STRUCTURE_CONFLICT LINE_STRUCTURE_UNRESOLVED MISSING_LINE_ID DUPLICATE_LINE_ID INVALID_COMPONENT_PARENT MISSING_COMPONENT_PARENT CONFLICTING_LINE DUPLICATE_SUMMARY CONFLICTING_SUMMARY SOURCE_JOIN_MISMATCH TIMESTAMP_MISMATCH TIMESTAMP_INVALID_OR_NAIVE TIMESTAMP_RANGE_UNSUPPORTED TIMEZONE_MISMATCH UTC_OFFSET_MISMATCH SUMMARY_LINE_COUNT_MISMATCH PAGINATION_COVERAGE_UNVERIFIED REVIEW_ASSIGNMENT_UNVERIFIED MISSING_HEADER DUPLICATE_HEADER MISSING_COLUMN UNEXPECTED_COLUMN MALFORMED_CSV MALFORMED_ROW_WIDTH INVALID_ORDER_ID CSV_INPUT_TYPE CSV_FORMULA_RISK GLOBAL_INPUT_HOLD ORDER_CAPTURE_INCOMPLETE DISPLAYED_ORDER_ID_UNVERIFIED".split(" "));
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
  function validDiscovery(d,order,globalHeld=false) {
    if(!exactKeys(d,["schema","category","ready_line_ordinals","waiting_line_ordinals","kit_dependent","stock_clues","quantity_verified","decision_eligible"])
      ||d.schema!=="doi-split-discovery/v1"||typeof d.category!=="string"||!Object.hasOwn(discoveryLabels,d.category)
      ||typeof d.kit_dependent!=="boolean"||d.quantity_verified!==false||d.decision_eligible!==false
      ||![d.ready_line_ordinals,d.waiting_line_ordinals].every(references)
      ||!Array.isArray(d.stock_clues)||d.stock_clues.length>5000)return false;
    const items=new Map(order.split.line_items.map(item=>[item.record_ordinal,item]));
    const physical=n=>natural(n)&&n>=2&&n<=5001&&items.has(n)&&items.get(n).ds!=="YES";
    const sides=[...d.ready_line_ordinals,...d.waiting_line_ordinals];
    if(sides.length>5000||new Set(sides).size!==sides.length||!sides.every(physical))return false;
    const units=value=>{const [whole,fraction=""]=value.split(".");return BigInt(whole+fraction.padEnd(6,"0"));};
    if(!d.stock_clues.every(clue=>exactKeys(clue,["record_ordinal","ordered","oh"])&&physical(clue.record_ordinal)
      &&canonicalAmount(clue.ordered)===clue.ordered&&canonicalAmount(clue.oh)===clue.oh
      &&clue.ordered!==null&&clue.oh!==null&&units(clue.oh)>0n&&units(clue.oh)<units(clue.ordered))
      ||new Set(d.stock_clues.map(clue=>clue.record_ordinal)).size!==d.stock_clues.length)return false;
    if(d.category==="NONE")return !sides.length&&!d.stock_clues.length&&!d.kit_dependent;
    if(globalHeld||!order.visible_coverage_complete||order.holds.some(code=>discoveryBlockingHolds.has(code))
      ||["UNVERIFIED","FUTURE_CAPTURE"].includes(order.evidence.snapshot_age_status)
      ||order.split.reason_codes.includes("TERMINAL_ORDER_OBSERVED")||order.split.status==="APPARENT_SPLIT_CANDIDATE")return false;
    if(d.category==="STOCK_COUNTER_CLUE")return !sides.length&&!d.kit_dependent&&d.stock_clues.length>0
      &&order.split.status!=="APPARENT_SPLIT_CANDIDATE";
    return d.ready_line_ordinals.length>0&&d.waiting_line_ordinals.length>0&&!d.stock_clues.length
      &&order.split.status==="CAPTURE_HELD"&&order.visible_coverage_complete
      &&order.holds.includes("SOURCE_ASSIGNMENT_CONFLICT_OR_UNKNOWN")
      &&d.ready_line_ordinals.every(n=>["in stock","instock","ships today","shipstoday"].includes((items.get(n).current_stock||"").toLowerCase()))
      &&d.waiting_line_ordinals.every(n=>waitingObserved(items.get(n).current_stock,order));
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
    return repFilter==="all"||repFilter==="review_leads"&&order.rep_scope!=="OTHER_REP"
      ||repFilter==="eligible"&&eligibleScope(order.rep_scope)
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
      &&(splitFilter==="all"||o.split.status===splitFilter
      ||splitFilter==="review_leads"&&(o.split.status==="APPARENT_SPLIT_CANDIDATE"||o.discovery.category==="HELD_MIXED_LABELS")
      ||["HELD_MIXED_LABELS","STOCK_COUNTER_CLUE"].includes(splitFilter)&&o.discovery.category===splitFilter
      ||splitFilter==="currency_conflict"&&o.currency[2]==="CONFLICT"||splitFilter==="missing_evidence"&&!o.evidence_complete
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
      && s.schema === "doi-csv-review/v6" && natural(s.revision) && statuses.has(s.status)
      && natural(s.expires_in_seconds) && s.counts && Object.keys(countLabels).every(k => natural(s.counts[k]))
      && s.groups && natural(s.groups.review) && natural(s.groups.quarantined)
      && codeList(s.batch_holds) && (s.error_code === null || fixedCode(s.error_code))
      && Array.isArray(s.orders) && s.orders.length <= __DOI_ORDER_LIMIT__ && s.orders.every(o =>
        exactKeys(o,["order_id", "rep_scope", "currency", "summary_record_ordinals", "line_record_ordinals", "visible_coverage_complete", "evidence_complete", "decision_eligible", "holds", "reviewer_assignment", "sales_credit_observed", "sales_credit_entitlement", "split", "evidence", "discovery",...(o.rep_confirmation===undefined?[]:["rep_confirmation"])])
        && typeof o.rep_scope === "string" && Object.hasOwn(scopeLabels,o.rep_scope)
        && typeof o.order_id === "string" && /^[1-9][0-9]{0,127}$/.test(o.order_id)
        && references(o.summary_record_ordinals) && references(o.line_record_ordinals)
        && typeof o.visible_coverage_complete === "boolean" && o.evidence_complete === false
        && o.decision_eligible === false && codeList(o.holds)
        && (o.reviewer_assignment === "Jude" || o.reviewer_assignment === null)
        && ["OBSERVED", "UNKNOWN"].includes(o.sales_credit_observed)
        && o.sales_credit_entitlement === "UNINTERPRETED" && validSplit(o.split,o) && validEvidence(o.evidence) && validDiscovery(o.discovery,o,s.batch_holds.length>0)
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
    current = null; results.hidden = true; reviewedState=null; reviewedById=new Map();
    byId("doi-reviewed-count").textContent="";
    byId("doi-orders").replaceChildren(); byId("doi-counts").replaceChildren();
    byId("doi-triage-counts").replaceChildren(); byId("doi-triage-context").textContent = "";
    byId("doi-batch-holds").textContent = ""; byId("doi-session-label").textContent = "";
    byId("doi-ownership-summary").textContent = "";
    byId("doi-currency-summary").textContent = "";
  }
  function resetFiles() { summary.value = ""; lines.value = ""; }
  function controls() {
    newButton.disabled = busy || marksBusy || revision === null; clearButton.disabled = busy || marksBusy || revision === null;
    summary.disabled = busy || marksBusy || !preparing; lines.disabled = busy || marksBusy || !preparing;
    loadButton.disabled = busy || marksBusy || !preparing || !summary.files.length || !lines.files.length;
  }
  function add(parent, tag, text) { const node = document.createElement(tag); node.textContent = text; parent.append(node); return node; }
  function totalLabel(t,currency) {
    const code=currency[2]==="CONFLICT"?"currency conflict":"USD";
    if(t.status==="VALID") return `${t.displayed} (${code})`;
    return `${t.status.toLowerCase()}: ${t.displayed||"not captured"} (${code})`;
  }
  function nextCheck(order) {
    if(order.rep_scope==="OTHER_REP")return "Excluded: another confirmed rep. Reconciliation only; the assignment remains unchanged.";
    const prefix=(!eligibleScope(order.rep_scope)?scopeLabels[order.rep_scope]+". Reconcile the captured rep field. ":"")
      +(order.currency[2]==="CONFLICT"?"Currency conflict: review remains held. ":"");
    if(order.discovery.category==="HELD_MIXED_LABELS")return prefix+"Diagnostic purchased-line labels only. Resolve capture holds and verify remaining units, allocation and drop-ship scope before any split decision.";
    if(order.discovery.category==="STOCK_COUNTER_CLUE")return prefix+"Compare captured stock and ordered quantity with current line evidence. Remaining units and allocation are unknown; this is not a ready/waiting split pattern.";
    if(order.split.status==="CAPTURE_HELD") return prefix+"Resolve capture conflicts before split review.";
    if(order.split.status==="APPARENT_SPLIT_CANDIDATE") return prefix+"Verify outstanding quantity, DS scope and full allocation for each side.";
    if(order.split.status==="INSUFFICIENT_SPLIT_EVIDENCE") return prefix+"Verify missing stock or kit evidence and outstanding quantities.";
    return prefix+"Verify source scope; no distinct ready/waiting pattern is established.";
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
    const discovery=order.discovery;
    if(discovery.category==="HELD_MIXED_LABELS") {
      add(details,"p","Held review lead only. These diagnostic labels set aside only the assignment hold; the original classification and every hold remain unchanged.");
      side("Diagnostic ready purchased lines - not verified ready",discovery.ready_line_ordinals);
      side("Diagnostic waiting purchased lines - holds remain",discovery.waiting_line_ordinals);
      add(details,"p",discovery.kit_dependent?"Kit parent needed for this pattern. Verify the complete kit and component scope.":"The diagnostic pattern has independent non-kit purchased lines.");
    }
    if(discovery.category==="STOCK_COUNTER_CLUE") {
      add(details,"h3","Stock-counter clues only - no allocation established");
      const clues=add(details,"ul","");
      for(const clue of discovery.stock_clues)add(clues,"li",`Lines record ${clue.record_ordinal}: captured OH ${clue.oh}; captured ordered quantity ${clue.ordered}. Remaining units, allocation and drop-ship scope remain unverified.`);
    }
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
  function validReviewed(s) {
    if (!current || !exactKeys(s,["schema","revision","storage_revision","storage_available","orders"])
        || s.schema!=="doi-reviewed-split/v1" || s.revision!==revision
        || typeof s.storage_available!=="boolean"
        || (s.storage_available?!natural(s.storage_revision):s.storage_revision!==null)
        || !Array.isArray(s.orders) || s.orders.length!==current.orders.length) return false;
    const ids=new Set(current.orders.map(order=>order.order_id)), seen=new Set();
    for (const item of s.orders) {
      if (!exactKeys(item,["order_id","evidence_key","status"]) || !ids.has(item.order_id) || seen.has(item.order_id)
          || !["REVIEWED","UNREVIEWED","CHANGED","AMBIGUOUS","UNAVAILABLE"].includes(item.status)
          || (item.evidence_key!==null && (typeof item.evidence_key!=="string" || !/^[0-9a-f]{64}$/.test(item.evidence_key)))) return false;
      if (!s.storage_available && item.status!=="UNAVAILABLE") return false;
      if (s.storage_available && (item.status==="UNAVAILABLE" || (item.status==="AMBIGUOUS")!==(item.evidence_key===null))) return false;
      seen.add(item.order_id);
    }
    return true;
  }
  function applyReviewed(s) {
    if (!validReviewed(s)) throw new Error("INVALID_REVIEW_MARK_RESPONSE");
    reviewedState=s; reviewedById=new Map(s.orders.map(item=>[item.order_id,item]));
  }
  async function syncReviewed(run) {
    if (!current) return;
    try {
      const state=await request("reviewed-state");
      if (run!==epoch) return;
      applyReviewed(state);
    } catch {
      if (run!==epoch) return;
      reviewedState=null; reviewedById=new Map();
      marksError="";
    }
    if (run===epoch) renderOrders();
  }
  function isReviewed(order) {
    return reviewedState?.storage_available===true && reviewedById.get(order.order_id)?.status==="REVIEWED";
  }
  function renderReviewed(cell,order) {
    const record=reviewedById.get(order.order_id);
    const label=add(cell,"label","");label.className="doi-review-check";
    const checkbox=document.createElement("input"); checkbox.type="checkbox";
    checkbox.id="doi-reviewed-"+order.order_id;
    checkbox.setAttribute("aria-label",`Reviewed for split — order ${order.order_id}`);
    checkbox.checked=isReviewed(order);
    checkbox.disabled=marksBusy || !reviewedState?.storage_available || !record?.evidence_key;
    label.append(checkbox); add(label,"span","Reviewed for split");
    if (record?.status==="CHANGED") add(cell,"p","Evidence changed — review again.").className="doi-review-changed";
    if (record?.status==="AMBIGUOUS") add(cell,"p","Duplicate or conflicting record — resolve before checking.");
    if (!reviewedState?.storage_available) add(cell,"p","Review tracking unavailable.");
    const expectedRevision=revision, expectedStorageRevision=reviewedState?.storage_revision;
    checkbox.addEventListener("change",()=>void saveReviewed(record,checkbox.checked,expectedRevision,expectedStorageRevision));
  }
  async function saveReviewed(record,checked,expectedRevision,expectedStorageRevision) {
    if (busy || marksBusy || !record?.evidence_key || revision!==expectedRevision) {renderOrders();return;}
    const restoreFocus=document.activeElement?.id==="doi-reviewed-"+record.order_id;
    const run=++epoch; marksBusy=true; marksError=""; controls(); renderOrders();
    try {
      const state=await request("reviewed",{revision:expectedRevision,storage_revision:expectedStorageRevision,
        order_id:record.order_id,evidence_key:record.evidence_key,reviewed:checked});
      if (run!==epoch) return;
      applyReviewed(state);
      if (!state.storage_available || (reviewedById.get(record.order_id)?.status==="REVIEWED")!==checked)
        throw new Error("REVIEW_MARK_NOT_CONFIRMED");
    } catch {
      if (run!==epoch) return;
      marksError="Review status was not confirmed saved. Rechecking the current evidence and saved checks.";
    } finally {
      marksBusy=false; controls();
      if (run===epoch) {
        await sync();
        if(restoreFocus && (!document.activeElement?.id || document.activeElement.id.startsWith("doi-reviewed-")))
          (byId("doi-reviewed-"+record.order_id)||byId("doi-hide-reviewed")).focus();
      }
    }
  }
  function renderOrders() {
    const body=byId("doi-orders"), focused=document.activeElement?.id;
    const expanded=new Set([...body.querySelectorAll("tr[data-order-id]")].filter(row=>row.querySelector("details")?.open).map(row=>row.dataset.orderId));
    body.replaceChildren();if(!current)return;
    const repFilter=byId("doi-rep-scope").value;
    const scoped=worklistOrders(current.orders,repFilter,group.value,byId("doi-sort").value);
    const hide=byId("doi-hide-reviewed"); hide.disabled=!reviewedState?.storage_available;
    const picked=hide.checked?scoped.filter(order=>!isReviewed(order)):scoped;
    const reviewedCount=current.orders.filter(isReviewed).length;
    const changedCount=[...reviewedById.values()].filter(item=>item.status==="CHANGED").length;
    byId("doi-reviewed-count").textContent=marksBusy?"Saving reviewed status…":marksError || (!reviewedState?.storage_available?
      "Review tracking unavailable. No orders are hidden as reviewed.":
      `${reviewedCount} of ${current.orders.length} captured orders reviewed for split; ${changedCount} require re-review; ${scoped.length-picked.length} reviewed orders hidden. Checks do not approve splitting or fulfillment.`);
    const currencyCounts=currencyConflictCounts(current.orders,repFilter);
    byId("doi-currency-summary").textContent=`Currency conflicts: ${currencyCounts.selected_scope} in the selected rep scope; ${currencyCounts.total} across all captured orders. Choose the Currency conflicts review group to inspect them. Select All captured orders for reconciliation to include every rep scope. Currency conflicts remain held and do not change rep assignments or split classifications.`;
    byId("doi-group-count").textContent=`${picked.length} visible of ${current.orders.length} captured orders; ${current.ownership_review.eligible_count} eligible for your review. Default order: exact nominal full total, highest first; currencies are not converted.`;
    for(const order of picked) {
      const tr=add(body,"tr","");tr.dataset.orderId=order.order_id;const orderCell=add(tr,"td",order.order_id),draftButton=add(orderCell,"button","Alternate email");draftButton.type="button";draftButton.addEventListener("click",()=>window.dispatchEvent(new CustomEvent("ssa-alternate-order",{detail:{order_id:order.order_id,revision}})));renderReviewed(add(tr,"td",""),order);add(tr,"td",totalLabel(order.split.total,order.currency));
      const statusCell=add(tr,"td","");add(statusCell,"span",splitLabels[order.split.status]).className="dashboard-state";
      add(statusCell,"p",scopeLabels[order.rep_scope]);
      if(order.currency[2]==="CONFLICT")add(statusCell,"p","Currency conflict: review held").className="dashboard-warning";
      if(order.discovery.category!=="NONE")add(statusCell,"p",discoveryLabels[order.discovery.category]+" - review lead only").className="dashboard-state";
      const evidenceCell=add(tr,"td",`${order.split.ready_line_ordinals.length} apparent ready / ${order.split.waiting_line_ordinals.length} apparent waiting${order.split.unresolved_line_ordinals.length?" / "+order.split.unresolved_line_ordinals.length+" unresolved":""}`);
      if(order.discovery.category==="HELD_MIXED_LABELS")add(evidenceCell,"p",`Diagnostic purchased-line labels: ${order.discovery.ready_line_ordinals.length} ready / ${order.discovery.waiting_line_ordinals.length} waiting; holds remain.${order.discovery.kit_dependent?" Kit-dependent pattern.":""}`);
      if(order.discovery.category==="STOCK_COUNTER_CLUE")add(evidenceCell,"p",`${order.discovery.stock_clues.length} stock-counter clue${order.discovery.stock_clues.length===1?"":"s"}; allocation unverified.`);
      renderEvidence(add(tr,"td",""),order);
      if(expanded.has(order.order_id))tr.querySelector("details").open=true;
    }
    if(!picked.length){const tr=add(body,"tr","");add(tr,"td","No orders match these review filters.").colSpan=6;}
    if(focused?.startsWith("doi-reviewed-")) (document.getElementById(focused)||hide).focus();
  }
  function updateSessionLabel(s) {
    byId("doi-session-label").textContent=`Expires in ${Math.ceil(s.expires_in_seconds/60)} minutes from this load · ${s.batch_holds.length?"batch quarantined":s.status==="quarantined"?"coverage held":"evidence review loaded"}`;
  }
  function applyState(s, justLoaded = false) {
    if (!validState(s)) throw new Error("INVALID_RESPONSE");
    revision = s.revision; if(window.dispatchEvent)window.dispatchEvent(new CustomEvent("ssa-review-revision",{detail:revision})); blank(); marksError="";
    if (s.status === "loaded" || s.status === "quarantined") {
      current = s; results.hidden = false;
      updateSessionLabel(s);
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
        : s.status === "error" && s.error_code === "REVIEW_RESPONSE_LIMIT" ? "This pair produces more than 4 MiB of review data. Load smaller matching pairs. The displayed review was cleared; saved checkboxes were not deleted."
        : s.status === "error" ? "The pair could not be reviewed. The displayed review was cleared; saved checkboxes were not deleted. " + labelCode(s.error_code || "REVIEW_INTERNAL_ERROR") + ". Start a new pair and check the CSV format and limits."
        : "No pair is loaded. Start a new file pair to choose captures.";
    }
  }
  async function readReviewResponse(response) {
    const declared = response.headers.get("Content-Length");
    if (declared !== null && (!/^(0|[1-9][0-9]*)$/.test(declared) || Number(declared) > maxReviewResponseBytes)) {
      if (response.body) await response.body.cancel();
      throw new Error("REVIEW_RESPONSE_LIMIT");
    }
    if (!response.body) throw new Error("INVALID_RESPONSE");
    const reader = response.body.getReader(), chunks = [];
    let size = 0;
    try {
      while (true) {
        const {done, value} = await reader.read();
        if (done) break;
        size += value.byteLength;
        if (size > maxReviewResponseBytes) {
          await reader.cancel();
          throw new Error("REVIEW_RESPONSE_LIMIT");
        }
        chunks.push(value);
      }
    } finally { reader.releaseLock(); }
    const bytes = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
    return JSON.parse(new TextDecoder("utf-8", {fatal:true}).decode(bytes));
  }
  async function request(path, payload, signal) {
    const options = {method: payload === undefined ? "GET" : "POST", cache: "no-store", credentials: "same-origin", signal};
    if (payload !== undefined) { options.headers = {"Content-Type": "application/json", "X-SSA-CSRF-Token": csrf}; options.body = JSON.stringify(payload); }
    const response = await fetch(api + path, options);
    if (!response.ok) throw new Error("REQUEST_REJECTED");
    return readReviewResponse(response);
  }
  async function sync() {
    if (busy || marksBusy) return;
    const run = ++epoch;
    try { const state = await request("state"); if (run !== epoch) return;
      if (revision !== state.revision) { preparing = false; resetFiles(); applyState(state); }
      else if (current) {current=state; updateSessionLabel(state);}
      await syncReviewed(run);
      controls();
    } catch { if (run !== epoch) return; blank(); revision = null; preparing = false; resetFiles(); controls(); message.textContent = "Cannot confirm the current local session. Reconnect or reload this page before choosing files."; }
  }
  async function clearSession(beginPair) {
    if (busy || marksBusy || revision === null) return;
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
    event.preventDefault(); if (busy || marksBusy || !preparing || revision === null || !summary.files.length || !lines.files.length) return;
    const run = ++epoch; busy = true; preparing = false; blank(); controls();
    const left = summary.files[0], right = lines.files[0]; controller = new AbortController();
    message.textContent = "Loading and checking this pair…";
    try {
      if (left.size > __DOI_CSV_LIMIT_BYTES__ || right.size > __DOI_CSV_LIMIT_BYTES__) throw new Error("FILE_LIMIT");
      const decode = async file => new TextDecoder("utf-8", {fatal:true}).decode(await file.arrayBuffer());
      const [summary_csv, lines_csv] = await Promise.all([decode(left), decode(right)]);
      if (run !== epoch) return;
      const state = await request("load", {revision, summary_csv, lines_csv}, controller.signal);
      if (run !== epoch) return; applyState(state, true); await syncReviewed(run);
    } catch {
      if (run !== epoch) return; blank(); revision = null;
      message.textContent = "The load was not confirmed. Rechecking the session; the previous pair is not displayed.";
    } finally {
      if (run === epoch) { controller = null; resetFiles(); busy = false; controls(); if (revision === null) await sync(); }
    }
  });
  byId("doi-hide-reviewed").addEventListener("change", renderOrders);
  group.addEventListener("change", renderOrders);
  byId("doi-rep-scope").addEventListener("change", renderOrders);
  byId("doi-sort").addEventListener("change", renderOrders);
  window.addEventListener("pagehide", () => { ++epoch; if (controller) controller.abort(); controller = null; busy = false; preparing = false; revision = null; resetFiles(); blank(); });
  window.addEventListener("pageshow", () => { blank(); preparing = false; revision = null; resetFiles(); controls(); void sync(); });
  window.setInterval(() => { if (!document.hidden && !busy) void sync(); }, 10000);
  controls(); void sync();
})();
