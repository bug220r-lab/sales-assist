/* SYNTHETIC-SALES-ASSIST-AUTHORED-M5 */
"use strict";
(() => {
  const $ = id => document.getElementById(id);
  const state = {offset:0, total:0, historyOffset:0, campaign:null, detail:null};
  const mode = location.pathname === "/replies" ? "replies" : location.pathname === "/writing-history" ? "history" : "campaigns";
  const el = (tag, text, className) => {const n=document.createElement(tag);if(text!==undefined)n.textContent=String(text);if(className)n.className=className;return n;};
  const message = text => {$('message').textContent=text;};
  const pretty = value => JSON.stringify(value,null,2);
  const money = cents => new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format((cents||0)/100);
  const button = (text, action) => {const b=el('button',text);b.type='button';b.addEventListener('click',()=>run(action));return b;};
  async function request(params, post=false) {
    const url='/api/v1/campaign-workspace'+(post?'/actions':'?'+new URLSearchParams(params));
    const options=post?{method:'POST',headers:{'Content-Type':'application/json','X-SSA-CSRF-Token':document.querySelector('meta[name="ssa-csrf-token"]').content},body:JSON.stringify(params)}:{};
    const response=await fetch(url,options);const data=await response.json();
    if(!response.ok)throw Error(data.error?.code||'Request rejected');return data.data;
  }
  async function run(action) {try {await action();}catch(error){message(error.message+' — your visible draft text is preserved. Reload source evidence before retrying a conflicting save.');}}
  const get = params => request(params);
  const post = (action,data={}) => request({action,...data},true);
  function facts(target, value) {const d=el('details');d.append(el('summary','Inspect complete evidence'),el('pre',pretty(value)));target.append(d);}
  function cards(counts) {const root=$('summary');root.replaceChildren();for(const [key,value] of Object.entries(counts||{})){if(typeof value!=='number')continue;const card=el('div',undefined,'workspace-card');card.append(el('strong',value),el('span',key.replaceAll('_',' ')));root.append(card);}}
  async function readFile(id) {const file=$(id).files[0];if(!file)throw Error('Select a synthetic JSON file');if(file.size>8*1024*1024)throw Error('File exceeds 8 MB');return JSON.parse(await file.text());}
  async function load() {
    if(mode==='campaigns')await loadCampaigns();else if(mode==='replies')await loadQueue();else await loadHistory();
  }
  async function loadCampaigns() {
    const data=await get({view:'campaigns'});const items=data.items||data;const root=$('campaign-list');root.replaceChildren();
    if(!items.length)root.append(el('p','No campaigns prepared. Load the generated synthetic demo or import a synthetic manifest.'));
    for(const item of items){const row=el('div',undefined,'workspace-card');row.append(button(item.campaign_id,()=>showCampaign(item.campaign_id)),el('p','Status: '+item.status));root.append(row);}
    if(state.campaign)await showCampaign(state.campaign);
  }
  async function showCampaign(id) {
    state.campaign=id;const data=await get({view:'campaign',id});cards(data.counts);const root=$('campaign-detail');root.replaceChildren(el('h2',id),el('p','Simulation state: '+data.status));
    const controls=el('div',undefined,'workspace-actions');
    for(const action of ['launch','pause','resume','step','reconcile'])controls.append(button(action==='step'?'Simulate next outreach':action[0].toUpperCase()+action.slice(1),async()=>{await post(action,{campaign_id:id});await showCampaign(id);message('Local simulation '+action+' completed.');}));
    controls.append(button('Simulate customer replies',async()=>{await post('demo-reply',{campaign_id:id});message('Generated customer replies are available in the Replies workspace.');}));root.append(controls);
    const table=el('table');const head=el('tr');for(const title of ['Rank / recipient','Recorded cart','Send state','Exact preview'])head.append(el('th',title));table.append(head);
    for(const record of (data.records||[]).slice(0,50)){const row=el('tr');row.append(el('td',(record.original_rank||record.rank)+' · '+record.email),el('td',money(record.cart_total_cents)),el('td',record.outcome||record.state||record.status||'untouched'));const cell=el('td');cell.append(button('Preview',async()=>{const preview=await get({view:'preview',id:record.queue_key,campaign_id:id});const d=el('details');d.open=true;d.append(el('summary','Exact simulated payload'),el('pre',pretty(preview)));root.append(d);}));row.append(cell);table.append(row);}root.append(table);facts(root,{...data,records:undefined});
  }
  async function loadQueue() {
    const params={view:'queue',offset:String(state.offset),sort:$('sort').value};for(const key of ['needs-reply','category','owner'])if($(key).value)params[key.replace('-','_')]=$(key).value;
    const data=await get(params);state.total=data.total;cards(data.metrics||data.counts);$('sync-status').textContent=(data.sync||[]).map(s=>s.campaign_id+': synced '+Math.floor(s.sync_age_seconds/60)+' min ago'+(s.last_error?' · Error: '+s.last_error:'')).join(' | ')+' · No background sync worker connected';
    const root=$('reply-queue');root.replaceChildren();const table=el('table');const head=el('tr');for(const title of ['Customer / category','Owner / age','Cart / review'])head.append(el('th',title));table.append(head);
    for(const item of data.items){const row=el('tr',undefined,/opt|complaint|bounce/i.test(item.category)?'attention':'');const first=el('td');first.append(button(item.email||item.conversation_id,()=>showConversation(item.conversation_id||item.current_conversation_id)),el('small',(item.category_label||item.category||'Review')+' · '+(item.needs_reply?'Needs reply':'Waiting / resolved')));const second=el('td',item.owner||item.owner_id||'Unassigned');second.append(el('small',(item.age_seconds==null?null:Math.floor(item.age_seconds/3600)+" h waiting")||item.age_label||item.age||item.latest_incoming_at||''));const third=el('td',money(item.cart_total_cents));third.append(el('small',item.review_state||'Unreviewed'));row.append(first,second,third);table.append(row);}root.append(table);if(!data.items.length)root.append(el('p','No matching conversations. Adjust filters or load the demo.'));
    $('page-info').textContent=(data.total?state.offset+1:0)+'–'+Math.min(state.offset+data.items.length,data.total)+' of '+data.total;$('previous').disabled=state.offset===0;$('next').disabled=state.offset+50>=data.total;
  }
  async function showConversation(id) {
    const data=await get({view:'conversation',id});state.detail=data;const root=$('conversation');root.replaceChildren(el('h2',data.email||id));
    root.append(el('p',(data.category||'Review')+' · '+(data.needs_reply?'Needs reply':'Waiting / resolved')),el('p','Classification evidence: '+(data.evidence||data.reason||data.summary||data.classification_reason||'Requires review')),el('p','Next action: '+(data.action||data.next_action||'Inspect evidence before reviewing.')));
    if(data.blockers?.length)root.append(el('p','Review blockers: '+data.blockers.join(', '),'workspace-message'));
    for(const thread of data.threads||data.source_threads||[]){const section=el('div',undefined,'workspace-thread');section.append(el('strong',(thread.type||'thread')+' · '+(thread.state||'')+' · '+(thread.createdAt||thread.created_at||'')),el('pre',thread.display_text||thread.body||thread.text||thread.body_text||'(No text; inspect attachment metadata)'));const attachments=thread._embedded?.attachments||thread.attachments||[];if(attachments.length)section.append(el('p','Attachments require review; their contents are unseen.'),el('pre',pretty(attachments)));root.append(section);}
    const proposal=data.proposal||{};root.append(el('h3','Local draft'),el('p','Suggestion source: '+(proposal.source||proposal.label||'Reusable starter')+' · No AI analysis'));
    for(const note of proposal.notes||[])root.append(el('p',note,'workspace-message'));
    const label=el('label','Reply text');const editor=el('textarea');editor.id='draft-text';editor.rows=9;editor.value=data.local_draft?.text??proposal.text??proposal.body??'';label.append(editor);root.append(label);
    const controls=el('div',undefined,'workspace-actions');for(const reviewed of [false,true])controls.append(button(reviewed?'Save and mark reviewed':'Save local draft',async()=>{
      const saved=await post('save-draft',{conversation_id:id,text:editor.value,expected_revision:data.local_draft?.revision||0,source_fingerprint:data.source_fingerprint,style_version:data.style_profile.version,reviewed});
      message('Local draft saved · revision '+(saved.revision||saved.local_draft?.revision||'updated')+(reviewed?' · reviewed':''));await showConversation(id);await loadQueue();
    }));controls.append(button('Inspect synthetic reviewed job',async()=>{const job=await post('synthetic-job',{conversation_id:id});facts(root,job);message('Synthetic contract preview only. This job is rejected by the production writer.');}));root.append(controls);
    facts(root,{...data,threads:undefined,proposal:undefined,local_draft:undefined});
  }
  async function loadHistory() {
    const data=await get({view:'history',offset:String(state.historyOffset)});cards(data.summary.counts);$('history-summary').replaceChildren(el('pre',pretty(data.summary)));
    $('history-candidates').replaceChildren();for(const item of data.candidates.items){const d=el('details');d.append(el('summary',item.thread_id+' · '+item.status+' · '+(item.reasons||[]).join(', ')),el('pre',item.candidate_text||''));facts(d,item);$('history-candidates').append(d);}
    $('history-page-info').textContent=(data.candidates.total?state.historyOffset+1:0)+'–'+Math.min(state.historyOffset+data.candidates.items.length,data.candidates.total)+' of '+data.candidates.total;$('history-previous').disabled=state.historyOffset===0;$('history-next').disabled=state.historyOffset+50>=data.candidates.total; $('style-profile').replaceChildren(el('pre',pretty(data.profile)));$('profile-json').value=pretty(data.profile);
  }
  $('load-demo').addEventListener('click',()=>run(async()=>{await post('demo');message('Generated synthetic demo loaded. Existing edits and send protections are preserved.');await load();}));
  $('filter').addEventListener('click',()=>run(async()=>{state.offset=0;await loadQueue();}));
  $('previous').addEventListener('click',()=>run(async()=>{state.offset=Math.max(0,state.offset-50);await loadQueue();}));
  $('next').addEventListener('click',()=>run(async()=>{state.offset+=50;await loadQueue();}));
  $('snapshot-import').addEventListener('click',()=>run(async()=>{await post('snapshot',{snapshot:await readFile('snapshot-file')});await loadQueue();message('Complete synthetic snapshot imported.');}));
  $('campaign-import').addEventListener('click',()=>run(async()=>{await post($('campaign-import-kind').value,{document:await readFile('campaign-file')});await loadCampaigns();message('Synthetic campaign input imported.');}));
  $('history-import').addEventListener('click',()=>run(async()=>{const files={};let report;const names=new Set();let size=0;for(const file of $('history-files').files){size+=file.size;if(size>8*1024*1024)throw Error('Combined files exceed 8 MB');if(names.has(file.name))throw Error('Duplicate filename');names.add(file.name);const text=await file.text();if(file.name==='report.json')report=JSON.parse(text);else files[file.name]=text;}if(!report)throw Error('Select report.json with sent-emails files');await post('history',{report,files});await loadHistory();message('Synthetic history prepared; inspect included, held and excluded reasons.');}));
  $('history-previous')?.addEventListener('click',()=>run(async()=>{state.historyOffset=Math.max(0,state.historyOffset-50);await loadHistory();})); $('history-next')?.addEventListener('click',()=>run(async()=>{state.historyOffset+=50;await loadHistory();})); $('profile-save').addEventListener('click',()=>run(async()=>{await post('profile',{profile:JSON.parse($('profile-json').value)});await loadHistory();message('Style profile saved. Review must be renewed for existing drafts.');}));
  $(mode==='campaigns'?'campaign-section':mode==='replies'?'reply-section':'history-section').hidden=false;
  $('page-title').textContent=mode==='campaigns'?'Campaigns':mode==='replies'?'Replies':'Writing history';
  $('page-description').textContent=mode==='campaigns'?'Prepare exact outreach and inspect every simulated send.':mode==='replies'?'Unanswered requests, source evidence, and durable local drafts.':'Prepare an inspectable candidate corpus and versioned style configuration.';
  for(const link of document.querySelectorAll('nav a'))if(link.pathname===location.pathname)link.setAttribute('aria-current','page');
  run(load);
})();
