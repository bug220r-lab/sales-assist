// SYNTHETIC-SALES-ASSIST-AUTHORED-M5
"use strict";
(() => {
  const byId = id => document.getElementById(id), panel = byId("alternate-editor");
  if (!panel) return;
  const checks = ["fitment","ownership","quantity","kit_scope","allocation","stock","finish_choice","price"];
  const strings = ["original_item","alternate_name","selected_line_ids","source_quantities_exact","alternate_id","alternate_quantity","alternate_observed_at","stock_wording","material_differences","technical_note","delay_note","product_url","product_note","product_verifier","product_observed_at","cart_url","cart_note","cart_verifier","cart_observed_at"];
  const flags = ["delay_verified","product_verified","cart_verified","technical_conflict"];
  const actions = ["generate","preview","save","copy-subject","copy-email","copy-review","export","delete"];
  const csrf = document.querySelector('meta[name="ssa-csrf-token"]').content;
  let selected=null, response=null, busy=false, dirty=false, needsPreview=false, stale=false;
  const message = text => {byId("alt-message").textContent=text;};
  function fields() {
    const value={checks:{}};
    for(const key of strings)value[key]=byId("alt-"+key).value;
    for(const key of flags)value[key]=byId("alt-"+key).checked;
    for(const key of checks)value.checks[key]={status:byId("alt-check-"+key).value,note:byId("alt-note-"+key).value};
    return value;
  }
  function entry() {return {fields:fields(),body:byId("alt-body").value,body_reviewed:byId("alt-body-reviewed").checked};}
  function controls() {
    for(const action of actions)byId("alt-"+action).disabled=busy||stale||!selected;
    byId("alt-fields").disabled=busy||stale;byId("alt-body").disabled=busy||stale;byId("alt-body-reviewed").disabled=busy||stale;
    byId("alt-copy-email").disabled=busy||stale||!selected;
    byId("alt-save").disabled=busy||stale||!response?.storage_available||!response?.evidence_key;
    byId("alt-delete").disabled=busy||stale||!response?.saved||!response?.storage_available||!response?.evidence_key;
    byId("alt-close").disabled=busy;
  }
  function list(id,values) {const root=byId(id);root.replaceChildren();for(const value of values){const li=document.createElement("li");li.textContent=value;root.append(li);}}
  function show(value) {
    if(value?.schema!=="doi-alternate-draft/v1"||value.order_id!==selected.order_id||value.revision!==selected.revision
      ||!["HELD_CANDIDATE","HELD_TECHNICAL_REVIEW","READY_FOR_HUMAN_REVIEW"].includes(value.draft?.status)||value.draft.send_ready!==false||value.draft.recipient_email!==null)throw Error("DRAFT_RESPONSE_INVALID");
    response=value;const e=value.draft.entry;
    for(const key of strings)byId("alt-"+key).value=e.fields[key];
    for(const key of flags)byId("alt-"+key).checked=e.fields[key];
    for(const key of checks){byId("alt-check-"+key).value=e.fields.checks[key].status;byId("alt-note-"+key).value=e.fields.checks[key].note;}
    byId("alt-body").value=e.body;byId("alt-body-reviewed").checked=e.body_reviewed;byId("alt-subject").value=value.draft.subject;
    byId("alt-status").textContent=value.draft.status==="HELD_TECHNICAL_REVIEW"?"Held for technical review":value.draft.status==="HELD_CANDIDATE"?"Held candidate — internal review only":"Ready for human review — not sent";
    list("alt-holds",value.draft.holds);list("alt-notices",value.draft.notices);list("alt-source-holds",value.context.source_holds);
    byId("alt-prior").hidden=!value.prior_body;byId("alt-prior-body").textContent=value.prior_body||"";
    needsPreview=false;controls();
  }
  async function request(payload) {
    const r=await fetch("/api/v1/doi-csv-review/alternate-draft",{method:"POST",cache:"no-store",credentials:"same-origin",
      headers:{"Content-Type":"application/json","X-SSA-CSRF-Token":csrf},body:JSON.stringify(payload)});
    const reader=r.body.getReader(),chunks=[];let size=0;
    try{while(true){const part=await reader.read();if(part.done)break;size+=part.value.byteLength;if(size>262144){await reader.cancel();throw Error("DRAFT_RESPONSE_TOO_LARGE");}chunks.push(part.value);}}
    finally{reader.releaseLock();}
    const bytes=new Uint8Array(size);let offset=0;for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.byteLength;}
    const value=JSON.parse(new TextDecoder("utf-8",{fatal:true}).decode(bytes));
    if(!r.ok)throw Error(value.error?.code||value.code||"DRAFT_REQUEST_REJECTED");
    return value;
  }
  async function act(action) {
    const payload={...selected,action};
    if(action==="generate")payload.fields=fields();
    if(["preview","save"].includes(action))payload.entry=entry();
    if(["save","delete"].includes(action)){payload.storage_revision=response.storage_revision;payload.evidence_key=response.evidence_key;}
    const value=await request(payload);show(value);
    if(["load","save","delete"].includes(action))dirty=false;
    if(action==="generate")dirty=true;
    return value;
  }
  function failure(error) {
    const code=String(error?.message||"");
    const conflict=/REVISION|EVIDENCE|ORDER_NOT_LOADED/.test(code);
    if(conflict)stale=true;
    message(conflict?"The capture or saved draft changed. Your unsaved text remains here; close and reselect the order before continuing.":
      /LINK/.test(code)?"A link is invalid or unverified. Use the exact HTTPS product/cart URL and record verification; remove other links from the customer body.":
      /CLIPBOARD/.test(code)?"Clipboard access was not available. Use Export review HTML instead; nothing was sent.":
      /STORAGE/.test(code)?"Draft storage is unavailable or full. Nothing was overwritten; your editor text remains available for review.":
      "This draft action could not be confirmed. Check the fields and retry; your editor text remains available.");
  }
  async function run(fn) {if(busy||stale||!selected)return;busy=true;controls();try{await fn();}catch(error){failure(error);}finally{busy=false;controls();}}
  async function open(order) {
    if(busy)return;
    if(dirty){message("Save or explicitly close this draft before selecting another order. Your edits have been kept.");return;}
    if(!order||!Number.isSafeInteger(order.revision)||!/^\d{1,128}$/.test(order.order_id))return;
    selected={order_id:order.order_id,revision:order.revision};stale=false;response=null;dirty=false;
    panel.hidden=false;byId("alt-heading").textContent="Alternate email — order #"+order.order_id;
    await run(async()=>{await act("load");message(!response.storage_available?"Draft storage is unavailable. Preview and export remain available; existing saved data was not changed.":response.changed_evidence?"Capture changed. Prior wording is preserved below; recheck the fields before generating a new draft.":response.saved?"Saved draft loaded.":"Enter the reviewed alternate details to start.");});
    panel.scrollIntoView?.({block:"start",behavior:"smooth"});
  }
  window.addEventListener("ssa-alternate-order",event=>{void open(event.detail);});
  window.addEventListener("ssa-review-revision",event=>{if(selected&&event.detail!==selected.revision){stale=true;message("The review session changed. Your unsaved text remains here; close and reselect an order.");controls();}});
  function changed(event) {
    dirty=true;needsPreview=true;
    if(event?.target===byId("alt-body"))byId("alt-body-reviewed").checked=false;
    byId("alt-status").textContent="Changes need preview — previous readiness no longer applies";
    controls();
  }
  for(const key of strings){byId("alt-"+key).addEventListener("input",event=>{
    if(key==="product_url"||key==="product_note")byId("alt-product_verified").checked=false;
    if(key==="cart_url"||key==="cart_note")byId("alt-cart_verified").checked=false;
    if(key==="alternate_id"||key==="alternate_quantity"){byId("alt-cart_verified").checked=false;byId("alt-check-quantity").value="unresolved";}
    if(key==="alternate_id"){byId("alt-product_verified").checked=false;byId("alt-check-fitment").value="unresolved";}
    if(key==="stock_wording"||key==="alternate_observed_at")byId("alt-check-stock").value="unresolved";
    byId("alt-body-reviewed").checked=false;
    if(key==="original_item"||key==="alternate_name"){
      for(const flag of ["delay_verified","product_verified","cart_verified"])byId("alt-"+flag).checked=false;
      for(const check of checks)byId("alt-check-"+check).value="unresolved";
    }
    changed(event);
  });}
  for(const key of flags)byId("alt-"+key).addEventListener("change",changed);
  for(const key of checks){byId("alt-check-"+key).addEventListener("change",changed);byId("alt-note-"+key).addEventListener("input",changed);}
  byId("alt-body").addEventListener("input",changed);byId("alt-body-reviewed").addEventListener("change",changed);
  byId("alt-generate").addEventListener("click",()=>run(async()=>{
    const oldBody=byId("alt-body").value,keep=oldBody&&oldBody!==response?.draft.template_body;
    await act("generate");
    if(keep){byId("alt-body").value=oldBody;byId("alt-body-reviewed").checked=false;changed();message("Your edited wording was preserved. Preview and review it against the updated alternate details before saving.");}
    else {dirty=true;message("Draft generated. Check the internal holds and customer wording, then save if wanted.");}
  }));
  byId("alt-preview").addEventListener("click",()=>run(async()=>{await act("preview");message("Preview checked. Nothing sent or saved.");}));
  byId("alt-save").addEventListener("click",()=>run(async()=>{await act("save");message("Draft saved locally. Reviewed for split is unchanged.");}));
  byId("alt-delete").addEventListener("click",()=>run(async()=>{
    if(!window.confirm("Delete this saved alternate draft? Reviewed for split and the capture will remain."))return;
    await act("delete");message("Saved draft deleted. Capture and reviewed checks are unchanged.");
  }));
  async function copy(value,rich) {
    try {
    if(rich&&window.ClipboardItem&&navigator.clipboard?.write){await navigator.clipboard.write([new window.ClipboardItem({"text/plain":new Blob([value.draft.email_text],{type:"text/plain"}),"text/html":new Blob([value.draft.email_html],{type:"text/html"})})]);}
    else if(navigator.clipboard?.writeText){await navigator.clipboard.writeText(rich?value.draft.email_text:value);}
    else throw Error("CLIPBOARD_UNAVAILABLE");
    } catch { throw Error("CLIPBOARD_UNAVAILABLE"); }
  }
  byId("alt-copy-subject").addEventListener("click",()=>run(async()=>{const value=await act("preview");await copy(value.draft.subject,false);message("Subject copied.");}));
  byId("alt-copy-email").addEventListener("click",()=>run(async()=>{const value=await act("preview");await copy(value,true);message(value.draft.status.replaceAll("_"," ")+" — draft copied for Jude’s review only. Internal checks remain here; nothing sent or approved.");}));
  byId("alt-copy-review").addEventListener("click",()=>run(async()=>{const value=await act("preview");await copy(value.draft.review_text,false);message("Review packet copied, including separate internal holds.");}));
  byId("alt-export").addEventListener("click",()=>run(async()=>{
    const value=await act("preview"),url=URL.createObjectURL(new Blob([value.draft.review_html],{type:"text/html;charset=utf-8"}));
    const link=document.createElement("a");link.href=url;link.download="order-"+selected.order_id+"-alternate-review.html";
    document.body.append(link);link.click();link.remove();window.setTimeout(()=>URL.revokeObjectURL(url),1000);message("Review HTML exported with internal checks separate from the customer email.");
  }));
  byId("alt-close").addEventListener("click",()=>{if(busy||dirty&&!window.confirm("Close without saving editor changes?"))return;panel.hidden=true;selected=null;response=null;dirty=false;stale=false;});
  window.addEventListener("beforeunload",event=>{if(dirty){event.preventDefault();event.returnValue="";}});
})();
