/* Floatwise's tiny framework-free client: accessible interactions, no CDN or tracker. */
(() => {
  'use strict';

  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => [...document.querySelectorAll(selector)];
  const state = { dashboard: null, invoices: [], view: 'overview', scenario: 'base', filter: 'all', search: '' };
  const money = (cents) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(cents / 100);
  const compact = (cents) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', notation: 'compact', maximumFractionDigits: 1 }).format(cents / 100);
  const decimal = (cents) => (cents / 100).toFixed(2);
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const formatDate = (date) => new Date(`${date}T12:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  const todayString = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`; };
  let toastTimer;

  async function api(path, options = {}) {
    const response = await fetch(path, options);
    if (!response.ok) {
      let details;
      try { details = (await response.json()).detail; } catch { details = `Request failed (${response.status})`; }
      if (Array.isArray(details)) details = details.map(d => d.msg).join('; ');
      throw new Error(String(details || `Request failed (${response.status})`));
    }
    return response.status === 204 ? null : response.json();
  }

  function toast(message, error = false) {
    const element = $('#toast');
    element.textContent = message;
    element.className = `toast visible${error ? ' error' : ''}`;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => element.classList.remove('visible'), 4200);
  }

  async function refresh() {
    try {
      const [dashboard, invoices] = await Promise.all([api('/api/dashboard'), api('/api/invoices')]);
      state.dashboard = dashboard;
      state.invoices = invoices.items;
      render();
    } catch (error) {
      toast(`Couldn't load workspace: ${error.message}`, true);
    }
  }

  function render() {
    if (!state.dashboard) return;
    $('#nav-count').textContent = state.dashboard.summary.total_invoices;
    $('#today-date').textContent = formatDate(state.dashboard.today);
    renderMetrics();
    renderChart();
    renderInsights();
    renderPriorities();
    renderInvoices();
    renderScenarios();
    $('#opening-balance').value = decimal(state.dashboard.settings.opening_balance_cents);
    $('#monthly-expenses').value = decimal(state.dashboard.settings.monthly_expenses_cents);
  }

  function renderMetrics() {
    const s = state.dashboard.summary;
    const entries = [
      { name: 'Outstanding invoices', value: money(s.outstanding_cents), icon: '↗', className: '', note: `${s.total_invoices - s.paid_count} awaiting payment` },
      { name: 'Past due', value: money(s.overdue_cents), icon: '!', className: 'amber', note: `${s.overdue_count} overdue invoices` },
      { name: 'Due in 7 days', value: money(s.due_soon_cents), icon: '◷', className: 'blue', note: 'Upcoming collection opportunity' },
      { name: 'Collection rate', value: `${s.collection_rate_pct}%`, icon: '✓', className: 'purple', note: `${s.paid_count} invoices paid` },
    ];
    $('#summary-grid').innerHTML = entries.map(x => `<article class="metric-card"><div class="metric-head"><span>${x.name}</span><span class="metric-icon ${x.className}">${x.icon}</span></div><div class="metric-value">${x.value}</div><div class="metric-sub">${esc(x.note)}</div></article>`).join('');
  }

  function svgElement(tag, attrs, text) {
    const element = document.createElementNS('http://www.w3.org/2000/svg', tag);
    Object.entries(attrs || {}).forEach(([name, value]) => element.setAttribute(name, String(value)));
    if (text !== undefined) element.textContent = text;
    return element;
  }

  function renderChart() {
    const projected = state.dashboard.forecast.scenarios;
    const current = projected[state.scenario];
    const initial = state.dashboard.settings.opening_balance_cents;
    $('#chart-end').textContent = money(current.end_balance_cents);
    const diff = current.end_balance_cents - initial;
    const delta = $('#chart-change');
    delta.textContent = `${diff >= 0 ? '↗ +' : '↘ −'}${compact(Math.abs(diff))} vs. today`;
    delta.classList.toggle('negative', diff < 0);
    const svg = $('#cash-chart');
    svg.replaceChildren();
    const allValues = Object.values(projected).flatMap(s => s.points.map(p => p.balance_cents));
    let min = Math.min(...allValues, 0), max = Math.max(...allValues, 0);
    const padding = (max - min || 100000) * .13;
    min -= padding; max += padding;
    const left = 65, top = 12, width = 758, height = 228, baseY = top + height;
    const x = i => left + (i / 90) * width;
    const y = value => top + (max - value) / (max - min) * height;
    for (let i = 0; i <= 4; i++) {
      const value = min + (max - min) * (4 - i) / 4;
      const yy = y(value);
      svg.appendChild(svgElement('line', { x1:left, x2:left+width, y1:yy, y2:yy, stroke:'#ecf1ee','stroke-dasharray':i===4?'0':'4 6' }));
      svg.appendChild(svgElement('text', { x:left-12, y:yy+4, 'text-anchor':'end', fill:'#9aaaaf','font-size':11 }, compact(value)));
    }
    const zeroY = y(0);
    if (zeroY >= top && zeroY <= baseY) svg.appendChild(svgElement('line',{x1:left,x2:left+width,y1:zeroY,y2:zeroY,stroke:'#c7d3cb','stroke-dasharray':'6 4'}));
    [0,30,60,90].forEach(day => svg.appendChild(svgElement('text', {x:x(day),y:baseY+26,'text-anchor':day===0?'start':day===90?'end':'middle',fill:'#9aaaaf','font-size':11},day===0?'Today':`Day ${day}`)));
    const points = current.points;
    const path = points.map((point, index) => `${index ? 'L' : 'M'}${x(index).toFixed(1)},${y(point.balance_cents).toFixed(1)}`).join(' ');
    const defs = svgElement('defs');
    const gradient = svgElement('linearGradient', {id:'fill-cash','x1':'0','y1':'0','x2':'0','y2':'1'});
    gradient.appendChild(svgElement('stop', {offset:'0%', 'stop-color':state.scenario==='stress'?'#eaa66d':'#36bf8d','stop-opacity':'.18'}));
    gradient.appendChild(svgElement('stop', {offset:'100%', 'stop-color':'#fff','stop-opacity':'0'}));
    defs.appendChild(gradient); svg.appendChild(defs);
    svg.appendChild(svgElement('path', {d:`${path} L${x(90)},${baseY} L${x(0)},${baseY} Z`,fill:'url(#fill-cash)'}));
    const stroke = state.scenario==='stress'?'#df9b64':state.scenario==='optimistic'?'#719fd5':'#25b77e';
    svg.appendChild(svgElement('path', {d:path,fill:'none',stroke,'stroke-width':3,'stroke-linecap':'round','stroke-linejoin':'round'}));
    const endpoint = points[points.length-1];
    svg.appendChild(svgElement('circle',{cx:x(90),cy:y(endpoint.balance_cents),r:5,fill:stroke,stroke:'white','stroke-width':3}));
    const title = svgElement('title',{},`The ${state.scenario} scenario ends at ${money(endpoint.balance_cents)} on ${formatDate(endpoint.date)}.`);
    svg.appendChild(title);
    $$('#chart-control button').forEach(button => { button.classList.toggle('active', button.dataset.scenario === state.scenario); button.setAttribute('aria-pressed', String(button.dataset.scenario === state.scenario)); });
  }

  function renderInsights() {
    $('#insights-list').innerHTML = state.dashboard.insights.map(item => `<article class="insight"><span class="insight-icon ${esc(item.type)}" aria-hidden="true">${item.type==='success'?'✓':item.type==='danger'?'!':item.type==='info'?'i':'↗'}</span><div><h3>${esc(item.title)}</h3><p>${esc(item.description)}</p></div></article>`).join('');
  }

  function renderPriorities() {
    const list = state.dashboard.priorities.slice(0,5);
    if (!list.length) { $('#priority-list').innerHTML = '<div class="empty-state"><div class="empty-icon">✓</div>All caught up — no unpaid invoices.</div>'; return; }
    $('#priority-list').innerHTML = list.map(i => `<div class="priority-row"><div class="priority-customer"><span class="customer-initial">${esc(i.customer.slice(0,2).toUpperCase())}</span><span><strong>${esc(i.customer)}</strong><small>${esc(i.invoice_number)}</small></span></div><strong class="priority-amount">${money(i.amount_cents)}</strong><span class="priority-overdue ${i.days_overdue?'urgent':''}">${i.days_overdue ? `${i.days_overdue}d overdue` : 'Due '+formatDate(i.due_on)}</span><span class="risk-pill ${i.risk_level.toLowerCase()}">${esc(i.risk_level)} · ${i.risk_score}</span><span class="priority-action">${esc(i.recommended_action)}</span></div>`).join('');
  }

  function invoiceStatus(i) {
    if (i.paid_on) return 'paid';
    return i.due_on < state.dashboard.today ? 'overdue' : 'open';
  }

  function renderInvoices() {
    const search = state.search.trim().toLowerCase();
    const filtered = state.invoices.filter(i => {
      const status = invoiceStatus(i);
      const matchesFilter = state.filter === 'all' || (state.filter === 'open' ? status !== 'paid' : status === state.filter);
      return matchesFilter && `${i.invoice_number} ${i.customer}`.toLowerCase().includes(search);
    });
    const tbody = $('#invoice-table-body');
    if (!filtered.length) tbody.innerHTML = '<tr><td colspan="6"><div class="empty-state"><div class="empty-icon">⌕</div>No invoices match your current filter.</div></td></tr>';
    else tbody.innerHTML = filtered.map(i => {
      const status = invoiceStatus(i);
      return `<tr><td><strong>${esc(i.invoice_number)}</strong></td><td>${esc(i.customer)}</td><td>${formatDate(i.due_on)}</td><td><strong>${money(i.amount_cents)}</strong></td><td><span class="status-pill ${status}">${status==='overdue'?'Overdue':status==='paid'?'Paid':'Open'}</span></td><td class="align-right"><button class="table-action ${status==='paid'?'paid-action':''}" data-pay-id="${i.id}" data-paid="${status==='paid'}">${status==='paid'?'Undo payment':'Mark paid'}</button></td></tr>`;
    }).join('');
    $('#invoice-count').textContent = `${filtered.length} of ${state.invoices.length} invoices`;
    $$('.filter-btn').forEach(button => { button.classList.toggle('active',button.dataset.filter===state.filter); button.setAttribute('aria-pressed', String(button.dataset.filter===state.filter)); });
  }

  function renderScenarios() {
    const scenarios = state.dashboard.forecast.scenarios;
    const labels = [
      ['optimistic','Best case','Earlier collections · higher realization'],
      ['base','Expected','Historical customer patterns · moderate realization'],
      ['stress','Stress test','Delayed collections · reduced realization'],
    ];
    $('#scenario-cards').innerHTML = labels.map(([name, label, description]) => {
      const result = scenarios[name];
      const note = result.cash_gap_date ? `Cash gap ${formatDate(result.cash_gap_date)}` : `Lowest balance ${money(result.low_balance_cents)}`;
      return `<div class="scenario-result"><div><h3><span class="scenario-dot ${name}"></span>${label}</h3><p>${description}</p></div><div><strong>${money(result.end_balance_cents)}</strong><small>${note}</small></div></div>`;
    }).join('');
  }

  function showView(view) {
    state.view = view;
    $$('.view').forEach(element => element.classList.toggle('hidden',element.id!==`view-${view}`));
    $$('.nav-link[data-view]').forEach(element => {
      const active = element.dataset.view===view;
      element.classList.toggle('active',active);
      if (active) element.setAttribute('aria-current','page'); else element.removeAttribute('aria-current');
    });
    $('#breadcrumb-view').textContent = ({overview:'Overview',invoices:'Receivables',forecast:'Forecast studio'})[view];
    window.scrollTo({top:0,behavior:'smooth'});
  }

  function openDialog() {
    $('#invoice-form').reset();
    $('#issued-date').value = state.dashboard?.today || todayString();
    const next = new Date(`${$('#issued-date').value}T12:00:00`);
    next.setDate(next.getDate()+30);
    $('#due-date').value = `${next.getFullYear()}-${String(next.getMonth()+1).padStart(2,'0')}-${String(next.getDate()).padStart(2,'0')}`;
    $('#invoice-backdrop').classList.remove('hidden');
    $('#invoice-form [name="invoice_number"]').focus();
  }
  function closeDialog() { $('#invoice-backdrop').classList.add('hidden'); }

  async function handleCreate(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const payload = Object.fromEntries(new FormData(form));
    try {
      await api('/api/invoices', { method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload) });
      closeDialog(); toast('Invoice created. Forecast updated.'); await refresh();
    } catch (error) { toast(error.message,true); }
  }

  async function handlePayment(event) {
    const button = event.target.closest('button[data-pay-id]');
    if (!button) return;
    const isPaid = button.dataset.paid==='true';
    if (isPaid && !window.confirm('Mark this invoice as unpaid again?')) return;
    try {
      await api(`/api/invoices/${button.dataset.payId}/payment`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({paid_on:isPaid?null:state.dashboard.today})});
      toast(isPaid?'Payment reversed.':'Invoice marked paid.'); await refresh();
    } catch(error) {toast(error.message,true);}
  }

  async function handleImport(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      if (file.size > 1_000_000) throw new Error('CSV must be under 1 MB');
      const response = await api('/api/import',{method:'POST',headers:{'Content-Type':'text/csv'},body:await file.text()});
      toast(`${response.imported} invoices imported successfully.`);
      showView('invoices'); await refresh();
    } catch(error) {toast(error.message,true);}
    finally {event.target.value='';}
  }

  async function handleSettings(event) {
    event.preventDefault();
    try {
      await api('/api/settings',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({opening_balance:$('#opening-balance').value,monthly_expenses:$('#monthly-expenses').value})});
      toast('Financial assumptions saved.'); await refresh();
    } catch(error) {toast(error.message,true);}
  }

  function setup() {
    $('#footer-year').textContent = new Date().getFullYear();
    $$('.nav-link[data-view]').forEach(b => b.addEventListener('click',() => showView(b.dataset.view)));
    $$('[data-go-view]').forEach(b => b.addEventListener('click',() => showView(b.dataset.goView)));
    $$('[data-open-invoice]').forEach(b => b.addEventListener('click',openDialog));
    $('#close-dialog').addEventListener('click',closeDialog);
    $('#cancel-dialog').addEventListener('click',closeDialog);
    $('#invoice-backdrop').addEventListener('click',e => {if (e.target.id==='invoice-backdrop') closeDialog();});
    document.addEventListener('keydown',e => {if(e.key==='Escape')closeDialog();});
    $('#invoice-form').addEventListener('submit',handleCreate);
    $('#settings-form').addEventListener('submit',handleSettings);
    $('#invoice-table-body').addEventListener('click',handlePayment);
    $('#search-invoices').addEventListener('input',e => {state.search=e.target.value;renderInvoices();});
    $$('.filter-btn').forEach(b => b.addEventListener('click',() => {state.filter=b.dataset.filter;renderInvoices();}));
    $$('#chart-control button').forEach(b => b.addEventListener('click',() => {state.scenario=b.dataset.scenario;renderChart();}));
    ['#side-import','#import-invoices'].forEach(s => $(s).addEventListener('click',()=>$('#csv-file').click()));
    ['#side-export','#export-invoices'].forEach(s => $(s).addEventListener('click',()=>{window.location.href='/api/export';}));
    $('#csv-file').addEventListener('change',handleImport);
    refresh();
  }

  document.addEventListener('DOMContentLoaded',setup);
})();
