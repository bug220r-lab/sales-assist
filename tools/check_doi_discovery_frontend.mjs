// Shipped JavaScript with synthetic responses and a minimal DOM. No network or browser.
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const input=JSON.parse(readFileSync(0,'utf8'));
const state=input.discovery.state, reviewed=input.discovery.reviewed;
const clone=value=>JSON.parse(JSON.stringify(value));
let assertions=0;
const check=(value,label)=>{assert.ok(value,label);assertions++;};
const fragment=input.js.slice(input.js.indexOf('  const statuses ='),input.js.indexOf('  const labelCode ='));
const {validState,validDiscovery,worklistOrders}=new Function(fragment+';return {validState,validDiscovery,worklistOrders};')();
check(validState(state),'Generated synthetic v6 discovery state validates');
const order=id=>state.orders.find(o=>o.order_id===id);
const held=order('90000102'), stock=order('90000103');
check(held.discovery.category==='HELD_MIXED_LABELS'&&held.split.status==='CAPTURE_HELD','Held discovery never replaces split status');
check(stock.discovery.category==='STOCK_COUNTER_CLUE','Stock clue remains a separate category');
check(order('90000108').discovery.kit_dependent,'Kit dependency retained');
for(const mutate of [
 d=>d.decision_eligible=true,d=>d.quantity_verified=true,d=>d.category='READY',
 d=>d.category=['HELD_MIXED_LABELS'],d=>d.unexpected='SYN-PRIVATE',
 d=>d.ready_line_ordinals.push(d.waiting_line_ordinals[0]),
 d=>d.ready_line_ordinals.push(5002),d=>d.ready_line_ordinals.push(999),
 d=>d.stock_clues.push({record_ordinal:d.ready_line_ordinals[0],ordered:'5',oh:'2'}),
 d=>d.ready_line_ordinals=[],
]){const d=clone(held.discovery);mutate(d);check(!validDiscovery(d,held),'Reject forged held discovery');}
for(const mutate of [
 d=>d.stock_clues[0].oh='0',d=>d.stock_clues[0].oh='5',d=>d.stock_clues[0].oh='6',
 d=>d.stock_clues[0].oh='02',d=>d.stock_clues[0].oh='NaN',
 d=>d.stock_clues[0].ordered='1e3',d=>d.stock_clues[0].ordered='1.0000001',
 d=>d.stock_clues[0].ordered='1000000000000000000',
 d=>d.stock_clues.push(clone(d.stock_clues[0])),d=>d.kit_dependent=true,
 d=>d.waiting_line_ordinals.push(d.stock_clues[0].record_ordinal),d=>d.stock_clues=[],
]){const d=clone(stock.discovery);mutate(d);check(!validDiscovery(d,stock),'Reject forged stock-counter clue');}
for(const mutate of [o=>o.split.line_items[0].ds='YES',o=>o.split.status='APPARENT_SPLIT_CANDIDATE',o=>o.holds=[],
 o=>o.holds.push('ORDER_CAPTURE_INCOMPLETE'),o=>o.holds.push('DUPLICATE_LINE_ID'),
 o=>o.visible_coverage_complete=false,o=>o.evidence.snapshot_age_status='FUTURE_CAPTURE',
 o=>o.split.reason_codes.push('TERMINAL_ORDER_OBSERVED')]){
 const o=clone(held);mutate(o);check(!validDiscovery(o.discovery,o),'Reject discovery detached from original held evidence');
}
check(!validDiscovery(held.discovery,held,true),'Global input hold blocks all discovery');
const stale=clone(state);stale.schema='doi-csv-review/v5';check(!validState(stale),'Reject prior transient schema');
const missing=clone(state);delete missing.orders[0].discovery;check(!validState(missing),'Reject omitted discovery');
const picked=(scope,group)=>worklistOrders(state.orders,scope,group,'source').map(o=>o.order_id);
check(picked('review_leads','review_leads').join(',')==='90000101,90000102,90000105,90000107,90000108,90000109','Default combines apparent and held patterns including currency holds');
check(picked('review_leads','STOCK_COUNTER_CLUE').join(',')==='90000103,90000106','Stock clues never enter default group');
check(picked('eligible','APPARENT_SPLIT_CANDIDATE').join(',')==='90000101','Existing eligible view retains currency exclusion');
check(picked('other','all').join(',')==='90000104','Confirmed other rep remains reconciliation only');
check(picked('all','all').length===9,'All orders retained for reconciliation');

class Element {
 constructor(tag='div'){this.tagName=tag;this.children=[];this.files=[];this.value='';this._text='';this.listeners=new Map();this.dataset={};this.checked=false;this.disabled=false;this.open=false;this.hidden=false;}
 set textContent(value){this._text=String(value);this.children=[];}get textContent(){return this._text+this.children.map(n=>n.textContent).join('\n');}
 set innerHTML(value){throw Error('Evidence must remain inert text');}
 append(...nodes){this.children.push(...nodes);}replaceChildren(...nodes){this.children=[...nodes];this._text='';}
 setAttribute(name,value){this[name]=value;}addEventListener(type,fn){this.listeners.set(type,fn);}focus(){active=this;}
 querySelectorAll(selector){const all=this.children.flatMap(n=>[n,...n.querySelectorAll('*')]);return selector==='*'?all:all.filter(n=>selector==='tr[data-order-id]'?n.tagName==='tr'&&n.dataset.orderId:selector==='details'?n.tagName==='details':false);}
 querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
}
const roots=new Map(), calls=[];let active=null;
const root=id=>{if(!roots.has(id)){const node=new Element();node.id=id;roots.set(id,node);}return roots.get(id);};
for(const id of ['doi-results','doi-orders','doi-group','doi-rep-scope','doi-sort','doi-session-label','doi-hide-reviewed','doi-reviewed-count','doi-message','doi-load-form','doi-summary-file','doi-lines-file','doi-new-pair','doi-clear','doi-load','doi-counts','doi-triage-counts','doi-triage-context','doi-batch-holds','doi-ownership-summary','doi-currency-summary','doi-group-count'])root(id);
root('doi-group').value='review_leads';root('doi-rep-scope').value='review_leads';root('doi-sort').value='source';root('doi-hide-reviewed').checked=true;
const document={hidden:false,get activeElement(){return active;},getElementById:id=>roots.get(id)||[...roots.values()].flatMap(e=>e.querySelectorAll('*')).find(e=>e.id===id)||null,createElement:tag=>new Element(tag),querySelector:()=>({content:'a'.repeat(64)})};
const fetch=async (path,options={})=>{
 assert.equal(options.method,'GET');assert.ok(['/api/v1/doi-csv-review/state','/api/v1/doi-csv-review/reviewed-state'].includes(path));
 calls.push(path);return new Response(JSON.stringify(path.endsWith('/reviewed-state')?reviewed:state),{headers:{'Content-Type':'application/json'}});
};
vm.runInNewContext(input.js,{document,window:{addEventListener(){},setInterval(){}},fetch,AbortController,TextDecoder,console},{timeout:3000});
for(let i=0;i<10;i++)await new Promise(setImmediate);
const rows=()=>root('doi-orders').children.filter(r=>r.dataset.orderId);
const ids=()=>rows().map(r=>r.dataset.orderId).join(',');
const visible=node=>node.tagName==='details'?'':node._text+'\n'+node.children.map(visible).join('\n');
check(!root('doi-results').hidden,'Synthetic state rendered');
check(ids()==='90000101,90000102,90000107,90000108,90000109','Saved held review hidden in default view');
check(root('doi-hide-reviewed').checked,'Hide reviewed retains its selected value');
const heldText=visible(rows().find(r=>r.dataset.orderId==='90000102'));
check(heldText.includes('Capture held')&&heldText.includes('Held: capture provenance unverified'),'Original capture and rep holds visible outside details');
check(heldText.includes('Held ready/waiting pattern - review lead only'),'Advisory label visible');
check(heldText.includes('Diagnostic purchased-line labels:')&&heldText.includes('holds remain'),'Diagnostic counts labeled without readiness approval');
check(!heldText.includes('Outside the default worklist'),'Held lead no longer claims to be outside default');
check(visible(rows().find(r=>r.dataset.orderId==='90000107')).includes('Currency conflict: review held'),'Currency hold visible in expanded default');
check(visible(rows().find(r=>r.dataset.orderId==='90000108')).includes('Kit-dependent pattern'),'Kit dependency visible');
const before=JSON.stringify({state,reviewed}), beforeCalls=calls.length;
for(const [scope,group,expected] of [
 ['review_leads','HELD_MIXED_LABELS','90000102,90000107,90000108'],
 ['review_leads','STOCK_COUNTER_CLUE','90000103'],
 ['eligible','APPARENT_SPLIT_CANDIDATE','90000101'],
 ['held','all','90000102,90000107,90000108'],
 ['all','all','90000101,90000102,90000103,90000104,90000107,90000108,90000109'],
 ['review_leads','review_leads','90000101,90000102,90000107,90000108,90000109'],
]){
 root('doi-rep-scope').value=scope;root('doi-rep-scope').listeners.get('change')();
 root('doi-group').value=group;root('doi-group').listeners.get('change')();
 check(ids()===expected,'Actual group/scope handlers filter '+scope+'/'+group);
 check(root('doi-hide-reviewed').checked,'Changing views preserves Hide reviewed');
}
root('doi-group').value='STOCK_COUNTER_CLUE';root('doi-group').listeners.get('change')();
check(visible(rows()[0]).includes('Stock-counter clue only')&&visible(rows()[0]).includes('allocation unverified'),'Stock-only row has explicit uncertainty');
check(rows()[0].textContent.includes('captured OH 2; captured ordered quantity 5'),'Exact captured counters shown in source evidence');
check(!ids().includes('90000106'),'Saved stock-clue review remains hidden');
check(JSON.stringify({state,reviewed})===before,'Views preserve source projection and saved marks');
check(calls.length===beforeCalls,'View changes perform no API calls or mark writes');
console.log(JSON.stringify({success:true,assertions,browser_interaction_tested:false,network_accessed:false}));
