const picked = new Map();
const choices = document.querySelector('#choices');
const mix = document.querySelector('#mix');
const result = document.querySelector('#result');
const proposalResult = document.querySelector('#proposal-result');

function equalize() {
  const rows = [...picked.values()];
  rows.forEach((row, index) => { row.percent = index ? 50 : rows.length === 1 ? 100 : 50; });
}

function currentWeights() {
  const weights = {};
  picked.forEach(row => Object.entries(row.weights).forEach(([symbol, weight]) => {
    weights[symbol] = (weights[symbol] || 0) + row.percent / 100 * weight;
  }));
  const total = Object.values(weights).reduce((sum, weight) => sum + weight, 0);
  return Object.entries(weights).map(([symbol, weight]) => [symbol, weight / total]).sort((a, b) => b[1] - a[1]);
}

function renderHoldings() {
  result.replaceChildren();
  const weights = currentWeights();
  const insight = document.querySelector('#mix-insight');
  if (picked.size === 2) {
    const [first, second] = [...picked.values()];
    const shared = Object.keys(first.weights).filter(symbol => symbol in second.weights);
    insight.textContent = shared.length ? `${shared.length} shared holding${shared.length === 1 ? '' : 's'}: ${shared.slice(0, 3).join(', ')}${shared.length > 3 ? '…' : ''}` : 'No shared holdings in these reported books.';
  } else insight.textContent = picked.size ? `${weights.length} holdings in this reported book.` : 'Select a portfolio to start.';
  weights.slice(0, 5).forEach(([symbol, weight]) => {
    const line = document.createElement('div'); line.className = 'row';
    const name = document.createElement('b'); name.textContent = symbol;
    const share = document.createElement('span'); share.textContent = `${Math.round(weight * 100)}%`;
    line.append(name, share); result.append(line);
  });
}

function render() {
  mix.replaceChildren();
  document.querySelectorAll('button.pilot').forEach(button => button.setAttribute('aria-pressed', String(picked.has(button.dataset.id))));
  picked.forEach(row => {
    const label = document.createElement('label'); label.textContent = `${row.name} · `;
    const input = document.createElement('input'); input.type = 'number'; input.min = '1'; input.max = '99'; input.step = '1';
    input.value = row.percent; input.setAttribute('aria-label', `${row.name} percentage`);
    input.disabled = picked.size === 1;
    input.addEventListener('change', () => {
      const value = Number(input.value);
      if (!Number.isFinite(value) || value < 1 || value > 99) { input.value = row.percent; return; }
      row.percent = value;
      for (const other of picked.values()) if (other !== row) other.percent = 100 - value;
      render(); proposalResult.replaceChildren(); document.querySelector('#activation').hidden = true;
    });
    label.append(input, '%'); mix.append(label);
  });
  renderHoldings();
}

function toggle(pilot) {
  if (picked.has(pilot.id)) picked.delete(pilot.id);
  else if (picked.size < 2) picked.set(pilot.id, {id: pilot.id, name: pilot.name, weights: pilot.weights, percent: 0});
  equalize(); render(); proposalResult.replaceChildren(); document.querySelector('#activation').hidden = true;
}

function orderList(title, orders) {
  const section = document.createElement('div'); section.className = 'order-list';
  const heading = document.createElement('h3'); heading.textContent = title; section.append(heading);
  if (!orders.length) { const empty = document.createElement('p'); empty.className = 'note'; empty.textContent = 'None'; section.append(empty); }
  orders.forEach(order => {
    const row = document.createElement('div'); row.className = 'row';
    const symbol = document.createElement('b'); symbol.textContent = order.symbol;
    const amount = document.createElement('span'); amount.textContent = `$${Number(order.dollar_amount).toLocaleString(undefined, {minimumFractionDigits: 2})}`;
    row.append(symbol, amount); section.append(row);
  });
  return section;
}

document.querySelector('#preview').addEventListener('click', async () => {
  proposalResult.replaceChildren();
  if (!picked.size) { proposalResult.textContent = 'Choose a portfolio first.'; return; }
  const button = document.querySelector('#preview'); button.disabled = true; button.textContent = 'Checking local snapshot…';
  try {
    const response = await fetch('/api/proposal', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({picks: [...picked.values()].map(({id, percent}) => ({id, percent}))})});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Preview unavailable');
    const status = document.createElement('p'); status.className = 'note'; status.textContent = `Snapshot ${new Date(data.account_snapshot_at).toLocaleString()} · Estimated account $${data.account_value_estimate.toLocaleString()}`;
    proposalResult.append(status, orderList('Sell current positions', data.sell_orders), orderList('Buy with current buying power', data.buy_orders_now), orderList('Buy after sales settle', data.buy_orders_after_settlement));
    const save = document.createElement('button'); save.type = 'button'; save.className = 'btn'; save.textContent = 'Save research draft';
    save.addEventListener('click', async () => {
      save.disabled = true;
      try {
        const saved = await fetch('/api/proposal', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({picks: [...picked.values()].map(({id, percent}) => ({id, percent})), save: true})});
        const payload = await saved.json(); if (!saved.ok) throw new Error(payload.error);
        save.textContent = 'Draft saved on this Mac';
      } catch (error) { save.disabled = false; save.textContent = error.message; }
    });
    proposalResult.append(save);
    document.querySelector('#activation').hidden = false;
  } catch (error) { proposalResult.textContent = error.message === 'Failed to fetch' ? 'Start the local Alongside app to preview your account. The public site cannot access it.' : error.message; }
  finally { button.disabled = false; button.innerHTML = 'Preview sells & buys <span aria-hidden="true">→</span>'; }
});

document.querySelector('#activate').addEventListener('click', async () => {
  const status = document.querySelector('#activation-status');
  status.textContent = '';
  if (!document.querySelector('#replace-confirm').checked) {
    status.textContent = 'Confirm the strategy switch first.';
    return;
  }
  const button = document.querySelector('#activate'); button.disabled = true;
  try {
    const response = await fetch('/api/mandate', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        picks: [...picked.values()].map(({id, percent}) => ({id, percent})),
        cadence: 'on_filing',
        order_type: 'market_regular', confirm: 'REPLACE QCC-1',
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Could not save the mandate');
    status.textContent = 'Strategy switch requested on this Mac. The agent will check the live account before any order.';
  } catch (error) {
    button.disabled = false;
    status.textContent = error.message;
  }
});

fetch('/pilots.json').then(response => response.json()).then(data => {
  const dataDay = new Date(`${data.as_of}T00:00:00Z`);
  const eligible = row => {
    const age = (dataDay - new Date(`${row.as_of}T00:00:00Z`)) / 86400000;
    return Number.isFinite(row.return_90d) && age >= 0 && age <= (row.kind === '13f' ? 150 : 60);
  };
  data.pilots.filter(eligible).sort((a, b) => b.return_90d - a.return_90d).slice(0, 5).forEach(pilot => {
    const button = document.createElement('button'); button.className = 'pilot'; button.type = 'button'; button.dataset.id = pilot.id; button.textContent = pilot.name;
    button.addEventListener('click', () => toggle(pilot)); choices.append(button);
  });
  new URLSearchParams(location.search).getAll('add').slice(0, 2).forEach(id => {
    const preset = data.pilots.find(row => row.id === id && eligible(row)); if (preset) toggle(preset);
  });
}).catch(() => { choices.textContent = 'Portfolios could not load.'; });

const follow = document.querySelector('#follow');
follow.addEventListener('click', async () => {
  const status = document.querySelector('#follow-status');
  if (!picked.size) { status.textContent = 'Choose a portfolio first.'; return; }
  follow.disabled = true;
  try {
    const response = await fetch('/api/selection', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ picks: [...picked.values()].map(({ id, percent }) => ({ id, percent })) }) });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Could not save your choice');
    status.textContent = 'Portfolio choice saved to your connection. Automatic trading is not active yet.';
  } catch (error) { status.textContent = error.message; }
  finally { follow.disabled = false; }
});

if (!['127.0.0.1', 'localhost'].includes(location.hostname)) document.querySelector('[data-local-only]').remove();
fetch('/api/connection').then(response => response.json()).then(connection => {
  const status = document.querySelector('#connection-status');
  status.textContent = connection.connected ? `Robinhood Agentic ••••${connection.account_last4} connected` : 'Connect Robinhood before saving a choice.';
  if (!connection.connected) {
    const button = document.querySelector('#follow');
    button.disabled = true;
    const link = document.createElement('a'); link.href = '/api/connect'; link.className = 'text-link'; link.textContent = 'Connect Robinhood →';
    status.after(link);
  }
}).catch(() => { document.querySelector('#connection-status').textContent = 'Connection status unavailable.'; });
