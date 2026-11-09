/* Finance Intelligence Lab: 100 real signals + five editable operations workspaces. */
(() => {
  'use strict';
  const $ = selector => document.querySelector(selector);
  const $$ = selector => [...document.querySelectorAll(selector)];
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const dollars = cents => new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:0}).format(cents / 100);
  const niceDate = iso => iso ? new Date(`${iso.slice(0,10)}T12:00:00`).toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'}) : '—';
  const dateToday = () => {const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;};
  const state = { features:[], group:'All', search:'', limit:24, workspace:{resources:{},activity:[]}, reminders:[], resource:'cash', editId:null, query:'' };

  const configs = {
    cash:{name:'Cash movements',description:'Track actual income, expenses, and spending categories.',fields:[
      ['title','Description','text'],['kind','Movement type','select',['income','expense']],['amount','Amount (USD)','money'],['occurs_on','Transaction date','date'],['category','Category','text'],['notes','Notes','textarea',[],false]],columns:[['title','Description'],['kind','Type'],['amount_cents','Amount'],['occurs_on','Date'],['category','Category']]},
    budgets:{name:'Monthly budgets',description:'Set spending limits by category and monitor variance.',fields:[
      ['category','Expense category','text'],['monthly_limit','Monthly limit (USD)','money']],columns:[['category','Category'],['monthly_limit_cents','Monthly limit']]},
    tasks:{name:'Work tasks',description:'Prioritize collections, operational expenses, and follow-ups.',fields:[
      ['title','Task','text'],['category','Category','select',['collection','expense','general']],['customer','Customer','text',[],false],['due_on','Due date','date'],['priority','Priority','select',['low','medium','high']],['status','Status','select',['open','done','snoozed']],['assignee','Assigned to','text',[],false],['notes','Notes','textarea',[],false]],columns:[['title','Task'],['category','Type'],['due_on','Due'],['priority','Priority'],['status','Status']]},
    customers:{name:'Customer profiles',description:'Enrich customer accounts with terms, segments, and context.',fields:[
      ['name','Customer name','text'],['email','Email (optional)','email',[],false],['segment','Segment','select',['Standard','Strategic','Growth','Watch']],['payment_terms_days','Payment terms (days)','number'],['notes','Notes','textarea',[],false]],columns:[['name','Customer'],['email','Email'],['segment','Segment'],['payment_terms_days','Terms (days)']]},
    views:{name:'Saved views',description:'Save reusable searches across invoices and operations.',fields:[
      ['title','View name','text'],['resource','Applies to','select',['invoices','tasks','cash']],['search_text','Search words','text',[],false]],columns:[['title','View'],['resource','Resource'],['search_text','Search terms']]},
  };

  async function api(path,options={}) {
    const result=await (window.FloatwiseAuth?.fetch || fetch)(path,options);
    if(!result.ok){let detail;try{detail=(await result.json()).detail;}catch{detail=`HTTP ${result.status}`;}
      if(Array.isArray(detail))detail=detail.map(x=>x.msg||x.type||JSON.stringify(x)).join('; ');
      throw new Error(String(detail));}
    return result.status===204?null:result.json();
  }

  function announce(message,error=false){const toast=$('#toast');toast.textContent=message;toast.className=`toast visible${error?' error':''}`;setTimeout(()=>toast.classList.remove('visible'),4300);}

  async function load(){
    try {
      const [features,workspace,reminders]=await Promise.all([api('/api/v2/features'),api('/api/v2/workspace'),api('/api/v2/reminders')]);
      state.features=features.features;state.workspace=workspace;state.reminders=reminders.drafts;
      renderFeatures();renderOperations();renderActivity();renderReminders();
    } catch(error){announce(`The finance lab could not load: ${error.message}`,true);}
  }

  function displayFeature(feature){
    const value=feature.value;
    switch(feature.kind){case 'money':return dollars(value);case 'percent':return `${value}%`;case 'days':return `${value} d`;case 'decimal':return String(value);default:return Number(value).toLocaleString('en-US');}
  }

  function renderFeatures(){
    if(!state.features.length)return;
    const groups=['All',...new Set(state.features.map(item=>item.group))];
    $('#lab-categories').innerHTML=groups.map(group=>`<button data-group="${esc(group)}" class="${group===state.group?'active':''}" aria-pressed="${group===state.group}">${esc(group)} <small>${group==='All'?state.features.length:state.features.filter(item=>item.group===group).length}</small></button>`).join('');
    const search=state.search.trim().toLowerCase();
    const visible=state.features.filter(item=>(state.group==='All'||item.group===state.group)&&`${item.label} ${item.description} ${item.group}`.toLowerCase().includes(search));
    $('#lab-visible-count').textContent=`${Math.min(visible.length,state.limit)} of ${visible.length} matching signals`;
    $('#lab-features').innerHTML=visible.length ? visible.slice(0,state.limit).map(item=>`<article class="feature-card" aria-label="${esc(item.label)}: ${esc(displayFeature(item))}"><div class="feature-card-top"><span>${esc(item.group)}</span><strong>LIVE</strong></div><h3>${esc(item.label)}</h3><div class="feature-value">${esc(displayFeature(item))}</div><p class="feature-description">${esc(item.description)}</p></article>`).join('') : '<div class="lab-empty">No matching signals. Try a broader search or another category.</div>';
    $('#lab-more').classList.toggle('hidden',visible.length<=state.limit);
  }

  function formatCell(key,value){
    if(key.endsWith('_cents'))return `<strong>${dollars(value)}</strong>`;
    if(key.endsWith('_on'))return niceDate(value);
    if(['kind','status','priority','segment'].includes(key))return `<span class="ops-badge ${esc(value)}">${esc(value)}</span>`;
    return esc(value??'—');
  }

  function renderOperations(){
    if(!state.workspace.resources.cash)return;
    const r=state.workspace.resources;
    const sum=(items,key)=>items.reduce((a,b)=>a+(b[key]||0),0);
    const stats=[['Cash entries',r.cash.length],['Budgeted per month',dollars(sum(r.budgets,'monthly_limit_cents'))],['Open tasks',r.tasks.filter(t=>t.status==='open').length],['Customer profiles',r.customers.length]];
    $('#ops-overview').innerHTML=stats.map(([name,value])=>`<div class="ops-stat"><small>${esc(name)}</small><strong>${esc(value)}</strong></div>`).join('');
    $$('#ops-tabs button').forEach(button=>{button.classList.toggle('active',button.dataset.resource===state.resource);button.setAttribute('aria-pressed',String(button.dataset.resource===state.resource));});
    const cfg=configs[state.resource];
    $('#ops-title').textContent=cfg.name;$('#ops-description').textContent=cfg.description;
    $('#ops-export').href=`/api/v2/reports/${state.resource}?format=csv`;
    const cols=cfg.columns;
    $('#ops-table-head').innerHTML=`<tr>${cols.map(([,label])=>`<th>${esc(label)}</th>`).join('')}<th class="align-right">Actions</th></tr>`;
    let rows=r[state.resource]||[];
    const q=state.query.trim().toLowerCase();
    if(q)rows=rows.filter(row=>Object.values(row).some(value=>String(value??'').toLowerCase().includes(q)));
    $('#ops-table-body').innerHTML=rows.length ? rows.map(row=>`<tr>${cols.map(([key])=>`<td>${formatCell(key,row[key])}</td>`).join('')}<td class="align-right"><span class="ops-item-actions">${state.resource==='tasks'&&row.status!=='done'?`<button data-action="done" data-id="${row.id}">Done</button>`:''}${state.resource==='views'?`<button data-action="apply" data-id="${row.id}">Apply</button>`:''}<button data-action="edit" data-id="${row.id}">Edit</button><button class="danger" data-action="delete" data-id="${row.id}">Delete</button></span></td></tr>`).join('') : `<tr><td colspan="${cols.length+1}"><div class="ops-empty">No records ${q?'match this saved search':'yet'}. Create your first record to get started.</div></td></tr>`;
    $('#ops-count').textContent=`${rows.length} records${q?' (filtered)':''}`;
    if(q)$('#ops-description').textContent=`Saved view filter: "${state.query}" · ${cfg.description}`;
  }

  function renderActivity(){
    const rows=state.workspace.activity.slice(0,9);
    $('#ops-activity').innerHTML=rows.length?rows.map(item=>`<div class="ops-feed-item"><div><h3>${esc(item.action.replaceAll('_',' '))} · ${esc(item.resource)}</h3><p>Record ${esc(item.resource_id.slice(0,8))}</p></div><small>${niceDate(item.occurred_at.slice(0,10))}</small></div>`).join(''):'<div class="ops-empty">Actions will appear here as you work.</div>';
  }

  function renderReminders(){
    $('#ops-reminders').innerHTML=state.reminders.length?state.reminders.slice(0,6).map((row,index)=>`<div class="ops-feed-item"><div><h3>${esc(row.subject)}</h3><p>${esc(row.risk_level)} priority · Edit before sending</p></div><button data-draft-index="${index}">Copy</button></div>`).join(''):'<div class="ops-empty">No outstanding invoices to follow up.</div>';
  }

  function setResource(name){state.resource=name;state.query='';renderOperations();}

  function inputField(field,row){
    const [key,label,type,options=[],required=true]=field;
    let val=row?.[key];
    if(type==='money'){const cents=row?.[`${key}_cents`];val=typeof cents==='number'?(cents/100).toFixed(2):'';}
    if(!val&&val!==0&&type==='date')val=dateToday();
    if(!val&&val!==0&&type==='select')val=options[0];
    if(!val&&val!==0&&key==='payment_terms_days')val=30;
    const id=`op-${key}`;
    const attrs=`id="${id}" name="${esc(key)}" ${required?'required':''} ${type==='number'?'min="0" max="365"':''} ${type==='money'?'min="0" max="1000000000" step="0.01"':''}`;
    let input;
    if(type==='select')input=`<select ${attrs}>${options.map(option=>`<option value="${esc(option)}" ${val===option?'selected':''}>${esc(option)}</option>`).join('')}</select>`;
    else if(type==='textarea')input=`<textarea ${attrs}>${esc(val??'')}</textarea>`;
    else input=`<input type="${type==='money'?'number':type}" value="${esc(val??'')}" ${attrs}>`;
    return `<label class="ops-form-field" for="${id}"><span>${esc(label)}</span>${input}</label>`;
  }

  function openForm(row=null){
    state.editId=row?.id||null;
    const cfg=configs[state.resource];
    $('#ops-dialog-title').textContent=`${row?'Edit':'New'} ${cfg.name.toLowerCase().replace(/s$/,'')}`;
    $('#ops-form-fields').innerHTML=cfg.fields.map(field=>inputField(field,row)).join('');
    $('#ops-backdrop').classList.remove('hidden');
    $('#ops-form-fields input, #ops-form-fields select').focus();
  }
  function closeForm(){$('#ops-backdrop').classList.add('hidden');state.editId=null;}

  async function saveForm(event){
    event.preventDefault();
    const body=Object.fromEntries(new FormData(event.currentTarget));
    const resource=state.resource;
    try{
      await api(`/api/v2/${resource}${state.editId?`/${state.editId}`:''}`,{method:state.editId?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      closeForm();announce('Record saved. All intelligence signals updated.');await load();window.dispatchEvent(new Event('floatwise:updated'));
    }catch(error){announce(error.message,true);}
  }

  async function actOnResource(event){
    const button=event.target.closest('button[data-action]');if(!button)return;
    const action=button.dataset.action,id=button.dataset.id;
    const row=state.workspace.resources[state.resource].find(item=>item.id===id);if(!row)return;
    if(action==='edit'){openForm(row);return;}
    if(action==='apply'){
      const target=row.resource;
      if(target==='invoices'){
        document.querySelector('[data-view="invoices"]').click();
        const input=$('#search-invoices');input.value=row.search_text;input.dispatchEvent(new Event('input',{bubbles:true}));
      }else{setResource(target);state.query=row.search_text;renderOperations();}
      announce(`Applied saved view: ${row.title}`);return;
    }
    try {
      if(action==='delete'){
        if(!window.confirm(`Delete "${row.title||row.name||row.category}"? This cannot be undone.`))return;
        await api(`/api/v2/${state.resource}/${id}`,{method:'DELETE'});
      }else if(action==='done'){
        await api(`/api/v2/tasks/${id}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({...row,status:'done'})});
      }
      announce(action==='done'?'Task completed.':'Record removed.');await load();window.dispatchEvent(new Event('floatwise:updated'));
    } catch(error){announce(error.message,true);}
  }

  async function copyReminder(event){
    const button=event.target.closest('button[data-draft-index]');if(!button)return;
    const draft=state.reminders[Number(button.dataset.draftIndex)];if(!draft)return;
    const content=`Subject: ${draft.subject}\n\n${draft.body}`;
    try{await navigator.clipboard.writeText(content);announce('Reminder draft copied. Review before sending.');}
    catch{announce('Clipboard unavailable; select and copy the text from API /api/v2/reminders.',true);}
  }

  function setup(){
    $('#lab-search').addEventListener('input',e=>{state.search=e.target.value;state.limit=24;renderFeatures();});
    $('#lab-categories').addEventListener('click',e=>{const button=e.target.closest('button[data-group]');if(button){state.group=button.dataset.group;state.limit=24;renderFeatures();}});
    $('#lab-more').addEventListener('click',()=>{state.limit+=24;renderFeatures();});
    $('#ops-tabs').addEventListener('click',e=>{const button=e.target.closest('button[data-resource]');if(button)setResource(button.dataset.resource);});
    $('#ops-table-body').addEventListener('click',actOnResource);
    $('#ops-reminders').addEventListener('click',copyReminder);
    $('#new-resource-btn').addEventListener('click',()=>openForm());
    $('#ops-add').addEventListener('click',()=>openForm());
    $('#ops-close').addEventListener('click',closeForm);$('#ops-cancel').addEventListener('click',closeForm);
    $('#ops-backdrop').addEventListener('click',e=>{if(e.target.id==='ops-backdrop')closeForm();});
    $('#ops-form').addEventListener('submit',saveForm);
    document.addEventListener('keydown',e=>{if(e.key==='Escape')closeForm();});
    $$('.nav-link[data-view="lab"], .nav-link[data-view="operations"]').forEach(b=>b.addEventListener('click',load));
    window.addEventListener('floatwise:updated',load);
    load();
  }
  document.addEventListener('DOMContentLoaded',setup);
})();
