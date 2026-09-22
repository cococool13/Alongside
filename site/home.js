const status = document.querySelector('#snapshot-status');
const action = document.querySelector('.actions .btn');
const connectionLink = document.querySelector('#connection-link');
const fine = document.querySelector('.fine');
if (new URLSearchParams(location.search).get('connection') === 'failed') {
  status.textContent = 'Robinhood could not complete the connection. Your account has not been linked.';
  status.hidden = false;
}
fetch('/api/connection').then(response => response.json()).then(connection => {
  if (connection.connected) {
    status.textContent = `Robinhood Agentic ••••${connection.account_last4} connected`;
    status.hidden = false;
    action.textContent = 'Choose a portfolio →';
    fine.textContent = 'Your connection is stored on the server. Disconnect here to remove Alongside’s token, then revoke Alongside in Robinhood to remove its grant.';
    const disconnect = document.createElement('button');
    disconnect.type = 'button'; disconnect.className = 'text-link'; disconnect.textContent = 'Disconnect Robinhood';
    disconnect.addEventListener('click', async () => {
      const response = await fetch('/api/disconnect', { method: 'POST' });
      if (response.ok) location.reload();
    });
    connectionLink.replaceWith(disconnect);
  } else if (connection.available) {
    connectionLink.href = '/api/connect';
    connectionLink.removeAttribute('target');
    connectionLink.removeAttribute('rel');
    connectionLink.textContent = 'Connect Robinhood →';
    fine.textContent = 'Robinhood handles sign-in. Alongside never sees your password.';
  }
}).catch(() => {});
