const status = document.querySelector('#snapshot-status');
const action = document.querySelector('.actions .btn');
const fine = document.querySelector('.fine');
if (new URLSearchParams(location.search).get('connection') === 'failed') {
  status.textContent = 'Robinhood connection did not complete. Please try again.';
  status.hidden = false;
}
fetch('/api/connection').then(response => response.json()).then(connection => {
  if (!connection.connected) return;
  status.textContent = `Robinhood Agentic ••••${connection.account_last4} connected`;
  status.hidden = false;
  action.href = '/portfolios.html';
  action.innerHTML = 'Choose a portfolio <span aria-hidden="true">→</span>';
  fine.textContent = 'Your connection is stored on the server. Disconnect here to remove Alongside’s local token, then revoke Alongside in Robinhood to remove its grant.';
  const disconnect = document.createElement('button');
  disconnect.type = 'button'; disconnect.className = 'text-link'; disconnect.textContent = 'Disconnect Robinhood';
  disconnect.addEventListener('click', async () => {
    const response = await fetch('/api/disconnect', { method: 'POST' });
    if (response.ok) location.reload();
  });
  document.querySelector('.actions').append(disconnect);
}).catch(() => {});
