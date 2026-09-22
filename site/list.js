const selected = new Set();
const list = document.querySelector('#list');
const mixLink = document.querySelector('#mix-link');
const count = document.querySelector('#selection-count');
fetch('/pilots.json').then(response => {
  if (!response.ok) throw new Error('Portfolio data unavailable');
  return response.json();
}).then(data => {
  list.replaceChildren();
  const dataDay = new Date(`${data.as_of}T00:00:00Z`);
  const ranked = data.pilots.filter(row => {
    const age = (dataDay - new Date(`${row.as_of}T00:00:00Z`)) / 86400000;
    return Number.isFinite(row.return_90d) && age >= 0 && age <= (row.kind === '13f' ? 150 : 60);
  }).sort((a, b) => b.return_90d - a.return_90d).slice(0, 5);
  ranked.forEach((row, index) => {
    const button = document.createElement('button');
    button.type = 'button'; button.className = 'portfolio-row'; button.setAttribute('aria-pressed', 'false');
    const ordinal = document.createElement('span'); ordinal.className = 'ordinal'; ordinal.textContent = String(index + 1).padStart(2, '0');
    const name = document.createElement('span'); name.className = 'portfolio-name'; name.textContent = row.name;
    const meta = document.createElement('small'); meta.textContent = row.kind === '13f' ? `13F · ${row.who}` : `House · ${row.who}`; name.append(meta);
    const ret = document.createElement('strong'); ret.className = row.return_90d >= 0 ? 'return positive' : 'return negative'; ret.textContent = `${row.return_90d >= 0 ? '+' : ''}${row.return_90d.toFixed(1)}%`;
    const mark = document.createElement('span'); mark.className = 'select-mark'; mark.setAttribute('aria-hidden', 'true'); mark.textContent = '+';
    button.append(ordinal, name, ret, mark);
    button.addEventListener('click', () => {
      if (selected.has(row.id)) selected.delete(row.id);
      else if (selected.size < 2) selected.add(row.id);
      else return;
      button.setAttribute('aria-pressed', String(selected.has(row.id)));
      mark.textContent = selected.has(row.id) ? '✓' : '+';
      count.textContent = selected.size ? `${selected.size} portfolio${selected.size === 1 ? '' : 's'} selected` : 'Choose up to two portfolios';
      mixLink.href = '/mix.html?' + [...selected].map(id => 'add=' + encodeURIComponent(id)).join('&');
      mixLink.classList.toggle('disabled', selected.size === 0);
      mixLink.setAttribute('aria-disabled', String(selected.size === 0));
    });
    list.append(button);
  });
  mixLink.classList.add('disabled'); mixLink.setAttribute('aria-disabled', 'true');
}).catch(() => { list.innerHTML = '<p class="note">Portfolios could not load. Please try again.</p>'; });
mixLink.addEventListener('click', event => { if (!selected.size) event.preventDefault(); });
