// Pure JavaScript checks. No DOM, browser, server, fetch, or subprocess execution.
import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';
assert.equal(process.argv.length, 3, 'Supply the generated synthetic input path');
const input=JSON.parse(readFileSync(process.argv[2],'utf8'));
const fragment=input.js.slice(input.js.indexOf('  const statuses ='),input.js.indexOf('  const labelCode ='));
const {validState,validSplit,validTotal,validCurrency,waitingObserved,worklistOrders,totalCompare,currencyConflictCounts}=new Function(fragment+';return {validState,validSplit,validTotal,validCurrency,waitingObserved,worklistOrders,totalCompare,currencyConflictCounts};')();
let assertions=0;
function check(value,description){assert.equal(value,true,description);assertions++;}
const clone=value=>JSON.parse(JSON.stringify(value));
new Function(input.js);check(true,'Complete UI JavaScript compiles without execution');
check(validState(input.state),'Synthetic loaded v6 response');
check(validState(input.empty),'Empty v6 response');
check(validState(input.discovery.state),'Synthetic v6 held-pattern and stock-clue response');
const order=input.state.orders[0];
for(const [field,value] of [['decision_eligible',true],['quantity_verified',true],['status','CONFIRMED_SPLIT_CRITERIA']]){
  const changed=clone(order.split);changed[field]=value;check(!validSplit(changed,order),'Reject forged '+field);
}
for(const reason of ['CAPTURE_COHERENCE_HOLD','TERMINAL_ORDER_OBSERVED']){
  const changed=clone(order.split);changed.reason_codes.push(reason);check(!validSplit(changed,order),'Hold reason requires held status '+reason);
}
for(const [index,field,value] of [[0,'ds','YES'],[0,'current_stock','Back Ordered'],[1,'current_stock','In Stock']]){
  const changed=clone(order.split);changed.line_items[index][field]=value;check(!validSplit(changed,order),'Reject inconsistent side '+field+index);
}
for(const field of ['ready_line_ordinals','waiting_line_ordinals','unresolved_line_ordinals']){
  const changed=clone(order.split);changed[field].push(999);check(!validSplit(changed,order),'Reject out-of-scope ordinal '+field);
}
for(const display of ['$12,34.50','<script>SYN-PRIVATE</script>','=1+2','@SYN-PRIVATE']){
  const t=clone(order.split.total);t.displayed=display;check(!validTotal(t),'Reject unsafe total '+display);
}
for(const amount of ['NaN','1e3','-1','9007199254740992.0000001','001234.5']){
  const t=clone(order.split.total);t.amount=amount;check(!validTotal(t),'Reject invalid or noncanonical amount '+amount);
}
for(const symbol of ['\u20ac','\u00a3','\u00a5']){
  check(validTotal({amount:'1',displayed:symbol+'1',currency_code:null,currency_symbol:symbol,status:'VALID'}),'Preserve unicode currency '+symbol);
}
check(validTotal({amount:'9007199254740992.000001',displayed:'$9007199254740992.000001',currency_code:null,currency_symbol:'$',status:'VALID'}),'Exact decimal above binary safe-integer range');
const mismatch=clone(order.split.total);mismatch.amount='9';check(!validTotal(mismatch),'Reject mismatched displayed full total');
for(const label of ['Ships on Oct 4, 2026','Ships on Oct 20, 1999','Ships on Feb 30, 2026'])check(!waitingObserved(label,order),'Reject invalid or past waiting date '+label);
check(waitingObserved('Ships on Oct 5, 2026',order),'Same New York capture day is valid');
check(waitingObserved('Ships in 3 days',order),'Relative waiting label');
for(const mutate of [s=>s.schema='doi-csv-review/v2',s=>s.split_review.confirmed_split_count=1,s=>s.orders[0].evidence.evidence_references[0].record_ordinal=999,s=>s.orders[0].evidence.evidence_references[0].observed_value='<img src=x>']){
  const s=clone(input.state);mutate(s);check(!validState(s),'Reject closed-state forgery');
}
for(const mutate of [s=>s.orders[0].rep_scope='synthetic_private_rep',s=>s.ownership_review.eligible_count=true,s=>s.ownership_review.excluded_count=1,s=>s.ownership_review.status_counts.OWNER=0]){
  const s=clone(input.state);mutate(s);check(!validState(s),'Reject rep-scope or reconciliation forgery');
}
const scoped=['OWNER','UNASSIGNED_WEB','OTHER_REP','REP_UNMAPPED','REP_MISSING'].map((scope,index)=>{
  const o=clone(order);o.order_id=String(90000010+index);o.rep_scope=scope;o.summary_record_ordinals=[2+index];
  const amount=['9007199254740992.000001','9007199254740992.000002','999999999999999999','999999999999999998','1'][index];
  o.split.total={amount,displayed:'$'+amount,currency_symbol:'$',currency_code:null,status:'VALID'};return o;
});
check(JSON.stringify(worklistOrders(scoped,'eligible','all','total').map(o=>o.order_id))===JSON.stringify(['90000011','90000010']),'Exact totals after ownership filter above binary safe-integer range');
check(worklistOrders(scoped,'other','all','total').length===1,'Other-rep reconciliation filter');
check(worklistOrders(scoped,'held','all','total').length===2,'Held ownership reconciliation filter');
check(worklistOrders(scoped,'all','all','total').length===5,'All records remain available for reconciliation');
check(worklistOrders(scoped,'eligible','APPARENT_SPLIT_CANDIDATE','total').every(o=>['OWNER','UNASSIGNED_WEB'].includes(o.rep_scope)),'Default apparent worklist excludes other and held scopes');
const unknown=clone(scoped[0]);unknown.split.total={amount:null,displayed:null,currency_symbol:null,currency_code:null,status:'UNKNOWN'};
for(const currency of [['UNKNOWN','$','OWNER_USD'],['USD','$','OBSERVED_USD'],['EUR','\u20ac','CONFLICT'],[null,null,'CONFLICT']])check(validCurrency(currency),'Currency provenance valid');
for(const currency of [['EUR','$','OWNER_USD'],['USD','\u20ac','OBSERVED_USD'],['PRIVATE@example.test','$','OWNER_USD']])check(!validCurrency(currency),'Reject unsafe or forged USD provenance');
const conflicting=clone(scoped[0]);conflicting.currency=['EUR','$','CONFLICT'];conflicting.holds.push('CURRENCY_CONFLICT');
check(worklistOrders([conflicting],'eligible','APPARENT_SPLIT_CANDIDATE','total').length===0,'Contradictory currency is held outside default worklist');
check(worklistOrders([conflicting],'all','all','total').length===1,'Currency conflict retained for reconciliation');
const currencyCases=scoped.map((o,index)=>{
  const c=clone(o);c.order_id=String(90000030+index);c.summary_record_ordinals=[20+index];
  c.currency=['EUR','$','CONFLICT'];c.holds.push('CURRENCY_CONFLICT');
  if(index===1)c.split.status='CAPTURE_HELD';
  return c;
});
const mixed=[...scoped,...currencyCases], mixedBefore=JSON.stringify(mixed);
for(const [scope,ids] of [['eligible',['90000031','90000030']],['other',['90000032']],['held',['90000033','90000034']],['all',['90000032','90000033','90000031','90000030','90000034']]]){
  const counts=currencyConflictCounts(mixed,scope);
  const picked=worklistOrders(mixed,scope,'currency_conflict','total');
  check(JSON.stringify(picked.map(o=>o.order_id))===JSON.stringify(ids),'Currency conflict group intersects '+scope+' scope and sorts exact totals');
  check(counts.total===5&&counts.selected_scope===ids.length,'Currency counts distinguish all captures and '+scope+' scope');
  check(picked.length===counts.selected_scope,'Currency group count agrees with '+scope+' scope counter');
}
check(worklistOrders(mixed,'eligible','APPARENT_SPLIT_CANDIDATE','total').length===2,'Default excludes conflicts even when rep scope is eligible');
check(worklistOrders(mixed,'eligible','all','total').length===2,'Eligible all-status worklist remains free of currency conflicts');
check(worklistOrders(mixed,'eligible','CAPTURE_HELD','total').length===0,'Currency group required for eligible currency conflicts with capture holds');
check(worklistOrders(mixed,'all','CAPTURE_HELD','total').map(o=>o.order_id).join(',')==='90000031','Capture-hold reconciliation remains separate from currency filter');
check(worklistOrders(mixed,'held','all','total').length===4,'Held-rep route retains only rep holds, without relabeling eligible currency conflicts');
check(worklistOrders(mixed,'all','all','total').length===10&&new Set(worklistOrders(mixed,'all','all','total').map(o=>o.order_id)).size===10,'Full reconciliation retains every order exactly once');
check(worklistOrders(mixed,'all','currency_conflict','source').map(o=>o.order_id).join(',')==='90000030,90000031,90000032,90000033,90000034','Currency conflicts support capture ordering');
check(worklistOrders(mixed,'all','currency_conflict','priority').at(-1).order_id==='90000031','Currency conflicts support split-status ordering');
check(currencyConflictCounts(scoped,'eligible').total===0&&currencyConflictCounts(scoped,'eligible').selected_scope===0,'No-conflict batch has zero currency counts');
check(currencyConflictCounts([],'all').total===0&&worklistOrders([],'all','currency_conflict','total').length===0,'Empty session has no conflicts or rows');
check(JSON.stringify(mixed)===mixedBefore,'Filters and counters preserve ownership, split classifications, evidence, totals and input order');
const discoveryOrders=input.discovery.state.orders, discoveryBefore=JSON.stringify(discoveryOrders);
const leads=worklistOrders(discoveryOrders,'review_leads','review_leads','source');
check(leads.some(o=>o.discovery.category==='HELD_MIXED_LABELS'),'New default includes held purchased-line patterns');
check(leads.some(o=>o.currency[2]==='CONFLICT'),'New default retains currency conflicts as held review leads');
check(leads.every(o=>o.rep_scope!=='OTHER_REP'&&o.discovery.category!=='STOCK_COUNTER_CLUE'),'New default excludes other reps and stock-only clues');
check(worklistOrders(discoveryOrders,'review_leads','STOCK_COUNTER_CLUE','source').length===2,'Stock-only clues have a separate explicit group');
check(worklistOrders(discoveryOrders,'eligible','APPARENT_SPLIT_CANDIDATE','source').length===1,'Existing eligible filter retains its prior currency behavior');
check(JSON.stringify(discoveryOrders)===discoveryBefore,'Discovery filtering preserves original evidence and classifications');
const fakeProof=clone(input.state);fakeProof.orders[0].rep_confirmation={confirmed_at:'2026-10-05T15:00:00Z',evidence_reference:'SYN-OWNER-CONFIRMED'};
check(!validState(fakeProof),'Owner confirmation cannot be attached to an eligible scope');
check(totalCompare(unknown,scoped[1])>0,'Unknown total sorts after valid total');
check(!JSON.stringify(input.state).includes('jlewis')&&!JSON.stringify(input.state).includes('displayed_sales_credit_value'),'Raw rep value is not projected');
check(input.utc_cross_midnight.orders[0].split.status==='CAPTURE_HELD','Summary UTC offset conflicting with New York source declaration is held');
check(validState(input.utc_cross_midnight),'Frontend accepts held timezone-conflict response');
for(const [name,result] of Object.entries(input.shell_checks))check(result,'Shell '+name);
console.log(JSON.stringify({success:true,pure_frontend_assertions:assertions-Object.keys(input.shell_checks).length,shell_render_checks:Object.keys(input.shell_checks).length,browser_interaction_tested:false,network_accessed:false}));
