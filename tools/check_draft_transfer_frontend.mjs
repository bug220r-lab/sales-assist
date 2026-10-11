import assert from "node:assert/strict";
import {readFileSync, writeFileSync} from "node:fs";
import vm from "node:vm";
const input = JSON.parse(readFileSync(process.argv[2], "utf8"));
const origin = new URL(input.origin);
assert.equal(origin.hostname, "127.0.0.1"); assert.notEqual(origin.port, "8907");
const roots = new Map(), calls = [], events = new Map();
let pending = 0, assertions = 0, failAfterCreate = false;
const check = (value, label) => { assert.ok(value, label); assertions++; };
class Element {
  constructor(tag="div") {
    this.tagName=tag; this.children=[]; this.listeners=new Map(); this._value="";
    this.checked=false; this.disabled=false; this.hidden=false; this.files=[]; this.textContent="";
  }
  set value(v) { this._value=this.tagName === "textarea" ? String(v).replace(/\r\n/g,"\n") : v; }
  get value() { return this._value; }
  set textContent(v) { this._text=String(v); this.children=[]; }
  get textContent() { return this._text+this.children.map(node=>node.textContent).join(""); }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this._text=""; this.children=[...nodes]; }
  addEventListener(name, fn) { this.listeners.set(name, fn); }
  async click() { if (!this.disabled) return this.listeners.get("click")?.({preventDefault(){}}); }
  input() { this.listeners.get("input")?.({}); }
  change() { this.listeners.get("change")?.({}); }
}
for (const match of input.html.matchAll(/<([a-z][a-z0-9]*)\b[^>]*\bid="([^"]+)"/g)) {
  const node=new Element(match[1]); node.id=match[2]; roots.set(match[2],node);
}
const el=id=>{assert.ok(roots.has(id),id); return roots.get(id);};
const document={getElementById:id=>roots.get(id),querySelector:()=>({content:input.csrf}),
  createElement:tag=>new Element(tag),createTextNode:text=>({textContent:text})};
async function localFetch(path,options={}) {
  assert.ok(path.startsWith("/api/v1/doi-draft-transfer/")); pending++;
  const payload=options.body ? JSON.parse(options.body) : null;
  try {
    const response=await fetch(new URL(path,origin),{...options,headers:{...options.headers,Origin:origin.origin}});
    calls.push({action:payload?.action||"state",status:response.status,payload});
    if (payload?.action === "transfer" && failAfterCreate) {
      failAfterCreate=false; throw new TypeError("SYN connection uncertainty after server accepted request");
    }
    return response;
  } finally {pending--;}
}
const context={document,fetch:localFetch,TextDecoder,TextEncoder,TypeError,
  confirm:()=>true,addEventListener:(name,fn)=>events.set(name,fn)};
vm.runInNewContext(input.js,context,{timeout:3000});
async function settle() {
  for(let i=0;i<300;i++) {
    await new Promise(r=>setTimeout(r,10));
    if(!pending) {await new Promise(r=>setTimeout(r,25)); if(!pending)return;}
  }
  throw Error("Frontend request did not settle");
}
await settle();
check(el("transfer-rows").children.length===0,"Initial worklist empty");
check(context.DraftTransferUI.preserveBody(input.selected_body,input.selected_body.replace(/\r\n/g,"\n"))===input.selected_body,
  "Textarea CRLF normalization does not silently change exact source bytes");
const upload=text=>{const bytes=new TextEncoder().encode(text);el("transfer-file").files=[{size:bytes.length,arrayBuffer:async()=>bytes.buffer}];el("transfer-file").change();};
upload("bad,header\r\n"); await el("transfer-preview").click(); await settle();
check(el("transfer-import-results").textContent.includes("EXACT_HEADER_REQUIRED"),"Malformed CSV helpful header error");
check(el("transfer-commit").disabled,"Malformed CSV cannot commit");
upload(input.csv_text); await el("transfer-preview").click(); await settle();
check(!el("transfer-commit").disabled,"Valid import preview can commit");
await el("transfer-cancel").click(); await settle(); await el("transfer-refresh").click(); await settle();
check(el("transfer-rows").children.length===0,"Canceled import leaves no persisted rows");
await el("transfer-preview").click(); await settle();
const commit=el("transfer-commit"); await Promise.all([commit.click(),commit.click()]); await settle();
check(calls.filter(c=>c.action==="commit_import").length===1,"Duplicate import click submits once");
check(el("transfer-rows").children.length===2,"Selected and held rows imported");
const open=async index=>{await el("transfer-rows").children[index].children.at(-1).children[0].click();await settle();};
await open(1);
check(el("transfer-body").value==="" && el("transfer-body").disabled,"Withheld row has no original fallback");
check(el("transfer-create").disabled,"Held row transfer disabled");
await open(0);
check(el("transfer-body-preview").textContent===input.expected_preview,
  "Saved preview shows exact visible labels without Markdown delimiters");
const previewLinks=el("transfer-body-preview").children.filter(node=>node.tagName==="a");
check(previewLinks.length===2 && previewLinks[0].textContent==="SYN bracket & washer",
  "Cart and CTA each have one labeled anchor without nesting");
check(previewLinks[0].href===input.expected_cart_url && previewLinks[0].target==="_blank"
  && previewLinks[0].rel==="noopener noreferrer","Preview preserves URL with safe user-click navigation");
check(!el("transfer-recipient-verified").checked,"Imported recipient verification never accepted as approval");
check(el("transfer-create").disabled,"Imported approved claim cannot transfer");
el("transfer-notes").value="SYN unsaved note";el("transfer-notes").input();await open(1);
check(el("transfer-order-heading").textContent.includes("90000001"),"Changing order preserves dirty edit");
await el("transfer-discard").click(); await settle();
check(el("transfer-notes").value==="","Explicit discard restores saved record");
function completeReview() {
  el("transfer-recipient-verified").checked=true; el("transfer-recipient-provenance").value="SYN verified example.test source";
  el("transfer-holds-reviewed").checked=true; el("transfer-holds-note").value="SYN reviewed source holds";
  el("transfer-duplicate-status").value="no_existing_draft";
  el("transfer-duplicate-evidence").value="SYN checked isolated fake records: no prior draft";
  el("transfer-customer-decision").value="pending_conditional_outreach";
  el("transfer-customer-evidence").value="SYN customer decision pending; exact copy asks for consent and claims no order change";
  el("transfer-customer-conditional").checked=true;
  for(const group of el("transfer-checks").children) {
    group.children[0].children[0].checked=true;group.children[1].children[0].value="SYN explicit evidence";
  }
  for(const block of el("transfer-carts").children.slice(1)) {
    const group=block.children[1];group.children[0].children[0].checked=true;
    group.children[1].children[0].value="SYN exact component review";
    group.children[2].children[0].value="2026-10-11T00:00:00Z";
  }
  el("transfer-holds-note").input();
}
completeReview(); await el("transfer-save").click(); await settle();
const customerReview=calls.filter(c=>c.action==="edit").at(-1).payload.review.checks.customer_approval;
check(customerReview.decision==="pending_conditional_outreach" && customerReview.conditional_copy_reviewed,
  "Explicit pending decision permits conditional outreach without asserting customer consent");
check(!("resolved" in customerReview),"Customer decision is separate from generic resolved checkboxes");
check(calls.filter(c=>c.action==="edit").at(-1).payload.fields.selected_body_text===input.selected_body,
  "Saving checks preserves raw multiline selected copy");
check(el("transfer-holds").textContent==="All review gates resolved.","All explicit checks resolve review");
el("transfer-exact-approval").checked=true;el("transfer-exact-approval").change();
await el("transfer-approve").click();await settle();check(!el("transfer-create").disabled,"Exact version approval enables transfer");
el("transfer-body").value += "\nSYN edited wording";el("transfer-body").input();
check(el("transfer-create").disabled,"Dirty edit disables transfer immediately");
check(el("transfer-preview-status").textContent.includes("Unsaved copy")
  && el("transfer-body-preview").children.length===0,
  "Unsaved edits clear saved link nodes and cannot masquerade as the exact approved preview");
await el("transfer-save").click();await settle();
check(el("transfer-preview-status").textContent.includes("Saved exact preview")
  && el("transfer-body-preview").textContent.endsWith("SYN edited wording"),
  "Saving refreshes the exact preview from server segments");
check(el("transfer-create").disabled && el("transfer-holds").textContent.includes("REVIEW_IDENTITY"),
  "Saved edit invalidates approval and resets review");
check(el("transfer-customer-decision").value==="unreviewed" && !el("transfer-customer-conditional").checked,
  "Changed copy resets conditional outreach review");
completeReview();await el("transfer-save").click();await settle();
el("transfer-exact-approval").checked=true;el("transfer-exact-approval").change();
await el("transfer-approve").click();await settle();
failAfterCreate=true;const create=el("transfer-create");await Promise.all([create.click(),create.click()]);await settle();
check(calls.filter(c=>c.action==="transfer").length===1,"Duplicate create clicks submit once");
check(el("transfer-message").textContent.includes("Refresh results"),"Uncertain frontend response requests journal refresh without retry");
await el("transfer-refresh").click();await settle();
check(el("transfer-result").textContent.includes('"CREATED"'),"Read-only refresh recovers durable created result");
check(el("transfer-create").disabled,"Created result blocks duplicate create");
check(el("transfer-link").children[0].href.includes("/conversation/99000001/1"),"Returned draft link is visible");
check(calls.every(c=>!String(c.action).includes("send")),"No customer send action exposed or invoked");
writeFileSync(input.report_path,JSON.stringify({status:"PASS",assertions,requests:calls.length,
  actual_frontend_to_http:true,visible_chrome_verified:false,synthetic_only:true},null,2));
console.log(`Frontend PASS: ${assertions} assertions`);
