const status = document.querySelector('#snapshot-status');
const action = document.querySelector('.actions .btn');
const fine = document.querySelector('.fine');
if (new URLSearchParams(location.search).get('connection') === 'failed') {
  status.textContent = 'Robinhood connection did not complete. Please try again.';
  status.hidden = false;
}
fetch('/api/connection').then(response => response.json()).then(connection => {
  if (!connection.connected) return;
  status.textContent = 'Robinhood connection saved on this browser.';
  status.hidden = false;
  action.href = '/portfolios.html';
  action.innerHTML = 'Choose a portfolio <span aria-hidden="true">→</span>';
  fine.textContent = 'Your connection is stored securely on the server. You can disconnect it here at any time.';
  const disconnect = document.createElement('button');
  disconnect.type = 'button'; disconnect.className = 'text-link'; disconnect.textContent = 'Disconnect Robinhood';
  disconnect.addEventListener('click', async () => {
    const response = await fetch('/api/disconnect', { method: 'POST' });
    if (response.ok) location.reload();
  });
  document.querySelector('.actions').append(disconnect);
}).catch(() => {});
