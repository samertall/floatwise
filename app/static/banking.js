/* Human-in-the-loop transaction review. Imports never post money automatically. */
(() => {
  'use strict';
  const $ = selector => document.querySelector(selector);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const money = (cents, currency='USD') => new Intl.NumberFormat('en-US', {
    style:'currency', currency, maximumFractionDigits:2
  }).format(cents / 100);
  const state = { transactions:[], selected:null, suggestions:[], invoiceId:null };

  async function request(path, options={}) {
    const response = await (window.FloatwiseAuth?.fetch || fetch)(path, options);
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(typeof error.detail === 'string' ? error.detail : `Request failed (${response.status})`);
    }
    return response.status === 204 ? null : response.json();
  }

  function notify(message, isError=false) {
    const element = $('#toast');
    element.textContent = message;
    element.className = `toast visible${isError?' error':''}`;
    setTimeout(() => element.classList.remove('visible'), 4500);
  }

  async function refresh() {
    try {
      const [transactions, provider] = await Promise.all([
        request('/api/v3/bank-transactions'),request('/api/v3/plaid/status')
      ]);
      state.transactions = transactions.items;
      renderPlaid(provider);
      render();
    } catch(error) { notify(error.message,true); }
  }

  function renderPlaid(provider) {
    $('#plaid-connect').disabled = !provider.configured;
    $('#plaid-availability').textContent = provider.configured
      ? `Plaid ${provider.environment} is configured. Bank transactions enter the same manual review inbox.`
      : 'Bank API credentials are not configured on this server. You can still import bank, QuickBooks, and Xero exports below.';
    $('#plaid-connections').innerHTML = provider.connections.map((item,index) => `
      <div class="plaid-item"><span><strong>Connected institution ${index+1}</strong><small>${item.last_synced_at ? `Last synced: ${esc(item.last_synced_at.slice(0,19).replace('T',' '))}` : 'Not yet synced'}</small></span><button class="btn btn-outline" data-sync-id="${esc(item.id)}">↻ Sync</button></div>`).join('');
  }

  function loadPlaidScript() {
    if (window.Plaid?.create) return Promise.resolve();
    return new Promise((resolve,reject) => {
      const script=document.createElement('script');
      script.src='https://cdn.plaid.com/link/v2/stable/link-initialize.js';
      script.async=true;
      script.onload=resolve;
      script.onerror=()=>reject(new Error('Unable to load Plaid Link. Check internet access.'));
      document.head.appendChild(script);
    });
  }

  async function connectPlaid() {
    try {
      const {link_token} = await request('/api/v3/plaid/link-token',{method:'POST'});
      await loadPlaidScript();
      const handler=window.Plaid.create({
        token:link_token,
        onSuccess:async publicToken=>{
          try {
            await request('/api/v3/plaid/exchange',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({public_token:publicToken})});
            notify('Bank connection added. Select Sync to stage recent transactions.');
            await refresh();
          } catch(error) { notify(error.message,true); }
        },
        onExit: error => { if(error) notify('Bank connection was not completed.',true); }
      });
      handler.open();
    } catch(error) { notify(error.message,true); }
  }

  async function syncPlaid(id) {
    try {
      const outcome=await request(`/api/v3/plaid/${encodeURIComponent(id)}/sync`,{method:'POST'});
      notify(`Bank sync complete: ${outcome.new} new, ${outcome.updated} updated; all awaiting review.`);
      $('#bank-status-filter').value='unreviewed';
      await refresh();
    } catch(error) { notify(error.message,true); }
  }

  function render() {
    const rows = state.transactions;
    const waiting = rows.filter(row => row.status === 'unreviewed');
    const matched = rows.filter(row => row.status === 'matched');
    const inflows = rows.filter(row => row.signed_amount_cents > 0 && row.currency === 'USD');
    const stats = [
      ['Transactions imported', rows.length, 'All staged and reviewed records'],
      ['Awaiting review', waiting.length, 'Nothing posts until approved'],
      ['Matched invoices', matched.length, 'Human-confirmed reconciliations'],
      ['USD deposits', money(inflows.reduce((total,row)=>total+row.signed_amount_cents,0)), 'Imported statement credits']
    ];
    $('#bank-stats').innerHTML = stats.map(([label,value,detail]) => `<div class="ops-stat"><small>${esc(label)}</small><strong>${esc(value)}</strong><span>${esc(detail)}</span></div>`).join('');
    const status = $('#bank-status-filter').value;
    const filtered = rows.filter(row => status === 'all' || row.status === status);
    $('#bank-count').textContent = `${filtered.length} of ${rows.length} transactions`;
    $('#bank-table-body').innerHTML = filtered.map(row => `
      <tr><td>${esc(row.booking_date)}</td>
        <td><strong>${esc(row.description)}</strong><small class="bank-reference">${esc(row.external_id.slice(0,12))}</small></td>
        <td>${esc(row.source)}</td>
        <td><strong class="bank-amount ${row.signed_amount_cents >= 0 ? 'incoming':'outgoing'}">${row.signed_amount_cents>0?'+':''}${esc(money(row.signed_amount_cents,row.currency))}</strong></td>
        <td><span class="status-pill ${esc(row.status)}">${esc(row.status)}</span></td>
        <td class="align-right">${row.status === 'unreviewed' ? `<button class="table-action" data-review-id="${esc(row.id)}">Review ↗</button>` : '—'}</td></tr>`).join('') || `<tr><td colspan="6"><div class="empty-state">${rows.length?'No transactions match your filter.':'Import a statement to begin your review.'}</div></td></tr>`;
  }

  async function openReview(id) {
    state.selected = state.transactions.find(item => item.id === id);
    if (!state.selected) return;
    state.invoiceId = null;
    $('#bank-review').classList.remove('hidden');
    $('#bank-review-title').textContent = state.selected.description;
    $('#bank-review-desc').textContent = `${state.selected.booking_date} · ${money(state.selected.signed_amount_cents,state.selected.currency)} · ${state.selected.source}`;
    $('#bank-match').disabled = true;
    $('#bank-post').disabled = state.selected.currency !== 'USD' || state.selected.signed_amount_cents === 0;
    $('#bank-suggestions').innerHTML = '<p class="bank-review-hint">Finding potential invoice matches…</p>';
    try {
      state.suggestions = (await request(`/api/v3/bank-transactions/${encodeURIComponent(id)}/suggestions`)).matches;
      renderSuggestions();
    } catch(error) { notify(error.message,true); }
    $('#bank-review').scrollIntoView({behavior:'smooth',block:'center'});
  }

  function renderSuggestions() {
    const allowed = state.selected.signed_amount_cents > 0 && state.selected.currency === 'USD';
    const list = state.suggestions;
    $('#bank-suggestions').innerHTML = !allowed
      ? '<p class="bank-review-hint">Matching is available for incoming USD payments. You can post or ignore this entry.</p>'
      : list.length
        ? `<p class="bank-review-hint">Suggested invoice matches are ranked heuristically. Confirm the invoice before posting.</p><div class="bank-matches">${list.map(item=>`<label class="bank-match-row"><input type="radio" name="bank-match-choice" value="${esc(item.invoice_id)}"><span><strong>${esc(item.invoice_number)}</strong><small>${esc(item.customer)}</small></span><span class="bank-match-end"><strong>${esc(money(item.remaining_cents))}</strong><small>${item.confidence_pct}% similarity</small></span></label>`).join('')}</div>`
        : '<p class="bank-review-hint">No strong matches found. Review the invoices or post this as a separate cash movement.</p>';
  }

  async function perform(action) {
    if (!state.selected) return;
    const row = state.selected;
    if (action === 'reconcile' && !state.invoiceId) return;
    const message = action === 'reconcile'
      ? `Reconcile ${money(row.signed_amount_cents)} against the selected invoice and post a cash movement?`
      : action === 'post'
        ? `Post ${money(row.signed_amount_cents,row.currency)} to your cash book?`
        : 'Ignore this imported transaction?';
    if (!window.confirm(message)) return;
    try {
      await request(`/api/v3/bank-transactions/${encodeURIComponent(row.id)}/review`,{
        method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({action,invoice_id:action==='reconcile'?state.invoiceId:null})
      });
      $('#bank-review').classList.add('hidden');
      state.selected=null;
      notify(action === 'reconcile'?'Invoice matched and payment recorded.':action==='post'?'Cash movement posted.':'Transaction ignored.');
      await refresh();
      window.dispatchEvent(new Event('floatwise:updated'));
    } catch(error) { notify(error.message,true); }
  }

  async function importFile(event) {
    const file=event.target.files?.[0];
    if(!file) return;
    const format=$('#bank-format').value;
    try {
      if(file.size>2_000_000) throw new Error('Statements must be smaller than 2 MB');
      const result=await request(`/api/v3/import/${format}`,{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:await file.arrayBuffer()});
      notify(`${result.imported} transactions staged for review (${result.duplicates} already imported).`);
      $('#bank-status-filter').value='unreviewed';
      await refresh();
      window.dispatchEvent(new Event('floatwise:updated'));
    } catch(error) { notify(error.message,true); }
    finally { event.target.value=''; }
  }

  document.addEventListener('DOMContentLoaded', () => {
    $('#bank-upload').addEventListener('click',()=>$('#bank-file').click());
    $('#bank-file').addEventListener('change',importFile);
    $('#bank-refresh').addEventListener('click',refresh);
    $('#plaid-connect').addEventListener('click',connectPlaid);
    $('#plaid-connections').addEventListener('click',event=>{
      const button=event.target.closest('button[data-sync-id]');
      if(button) syncPlaid(button.dataset.syncId);
    });
    $('#bank-status-filter').addEventListener('change',render);
    $('#bank-table-body').addEventListener('click',event=>{
      const button=event.target.closest('[data-review-id]');
      if(button) openReview(button.dataset.reviewId);
    });
    $('#bank-suggestions').addEventListener('change',event=>{
      if(event.target.name==='bank-match-choice') {
        state.invoiceId=event.target.value;
        $('#bank-match').disabled=false;
      }
    });
    $('#bank-close-review').addEventListener('click',()=>$('#bank-review').classList.add('hidden'));
    $('#bank-ignore').addEventListener('click',()=>perform('ignore'));
    $('#bank-post').addEventListener('click',()=>perform('post'));
    $('#bank-match').addEventListener('click',()=>perform('reconcile'));
    document.querySelector('[data-view="banking"]').addEventListener('click',refresh);
    window.addEventListener('floatwise:updated',refresh);
    refresh();
  });
})();
