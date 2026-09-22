import { DurableObject } from 'cloudflare:workers';
import { agenticAccount, callRobinhood } from './broker.js';

const REGISTER = 'https://agent.robinhood.com/oauth/trading/register';
const AUTHORIZE = 'https://robinhood.com/oauth';
const TOKEN = 'https://api.robinhood.com/oauth2/token/';
const RESOURCE = 'https://agent.robinhood.com/mcp/trading';
const COOKIE = 'alongside_session';
const TTL = 10 * 60 * 1000;

export class AccountSession extends DurableObject {
  async begin(flow) { await this.ctx.storage.put('flow', flow); }
  async consume(state) {
    const flow = await this.ctx.storage.get('flow');
    await this.ctx.storage.delete('flow');
    if (!flow || flow.state !== state || Date.now() - flow.started > TTL) return null;
    return flow;
  }
  async connect(token) { await this.ctx.storage.put('token', token); }
  async status() {
    const token = await this.ctx.storage.get('token');
    return { connected: Boolean(token?.access_token && token?.account_number), connected_at: token?.connected_at || null, account_last4: token?.account_last4 || null };
  }
  async saveSelection(picks) { await this.ctx.storage.put('selection', picks); }
  async selection() { return await this.ctx.storage.get('selection') || null; }
  async brokerRead(name, args = {}) {
    if (!['get_accounts', 'get_portfolio', 'get_equity_positions', 'get_equity_orders', 'get_equity_quotes', 'get_equity_tradability'].includes(name)) throw new Error('Unsupported broker read');
    let token = await this.ctx.storage.get('token');
    if (!token?.account_number) throw new Error('Not connected');
    if (token.expires_at && Date.now() > token.expires_at - 60_000) {
      const response = await fetch(TOKEN, {
        method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded', Accept: 'application/json' },
        body: new URLSearchParams({ grant_type: 'refresh_token', refresh_token: token.refresh_token, client_id: token.client_id, resource: RESOURCE }),
      });
      if (!response.ok) throw new Error('Robinhood connection expired');
      const fresh = await response.json();
      if (typeof fresh.access_token !== 'string') throw new Error('Robinhood token refresh failed');
      token = { ...token, ...fresh, refresh_token: fresh.refresh_token || token.refresh_token, expires_at: Date.now() + Number(fresh.expires_in || 3600) * 1000 };
      await this.ctx.storage.put('token', token);
    }
    return callRobinhood(token.access_token, name, args);
  }
  async disconnect() { await this.ctx.storage.deleteAll(); }
}

function b64url(bytes) {
  return btoa(String.fromCharCode(...bytes)).replaceAll('+', '-').replaceAll('/', '_').replaceAll('=', '');
}
function random() { return b64url(crypto.getRandomValues(new Uint8Array(32))); }
function cookie(request) {
  const match = request.headers.get('Cookie')?.match(/(?:^|;\s*)alongside_session=([A-Za-z0-9_-]{43})(?:;|$)/);
  return match?.[1] || null;
}
function newCookie(value) { return `${COOKIE}=${value}; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=2592000`; }
function json(value, status = 200) { return Response.json(value, { status, headers: { 'Cache-Control': 'no-store' } }); }
function redirect(path, session) {
  const headers = { Location: path, 'Cache-Control': 'no-store' };
  if (session) headers['Set-Cookie'] = newCookie(session);
  return new Response(null, { status: 302, headers });
}
function validOrigin(request) { return request.headers.get('Origin') === new URL(request.url).origin; }

export async function oauth(request, env) {
  const url = new URL(request.url);
  if (url.pathname === '/api/connection') {
    const session = cookie(request);
    if (!session) return json({ connected: false });
    return json(await env.ACCOUNT_SESSIONS.getByName(session).status());
  }
  if (url.pathname === '/api/selection') {
    const session = cookie(request);
    if (!session) return json({ error: 'Connect Robinhood first' }, 401);
    const account = env.ACCOUNT_SESSIONS.getByName(session);
    if (!(await account.status()).connected) return json({ error: 'Connect Robinhood first' }, 401);
    if (request.method === 'GET') return json({ picks: await account.selection() });
    if (request.method !== 'POST' || !validOrigin(request)) return json({ error: 'Invalid request' }, 403);
    if (Number(request.headers.get('Content-Length')) > 2048) return json({ error: 'Request too large' }, 413);
    const body = await request.json();
    if (!Array.isArray(body.picks) || body.picks.length < 1 || body.picks.length > 2) return json({ error: 'Choose one or two portfolios' }, 400);
    const data = await (await env.ASSETS.fetch(new URL('/pilots.json', url))).json();
    const available = new Set(data.pilots.map(row => row.id));
    const ids = body.picks.map(row => row.id);
    if (new Set(ids).size !== ids.length || ids.some(id => typeof id !== 'string' || !available.has(id))) return json({ error: 'Invalid portfolio' }, 400);
    const percents = body.picks.map(row => row.percent);
    if (percents.some(n => !Number.isInteger(n) || n < 1 || n > 100) || percents.reduce((a, b) => a + b, 0) !== 100) return json({ error: 'Portfolio shares must total 100%' }, 400);
    await account.saveSelection(body.picks.map(({ id, percent }) => ({ id, percent })));
    return json({ saved: true });
  }
  if (url.pathname === '/api/connect' && request.method === 'GET') {
    if (url.protocol !== 'https:') return json({ error: 'HTTPS required' }, 400);
    const session = cookie(request) || random();
    const verifier = random();
    const challenge = b64url(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier))));
    const state = random();
    const redirectUri = `${url.origin}/api/callback`;
    const registration = await fetch(REGISTER, {
      method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ client_name: 'Alongside', redirect_uris: [redirectUri], grant_types: ['authorization_code', 'refresh_token'], response_types: ['code'], token_endpoint_auth_method: 'none', scope: 'internal' }),
    });
    if (!registration.ok) return json({ error: 'Robinhood did not accept the connection request' }, 502);
    const client = await registration.json();
    if (typeof client.client_id !== 'string') return json({ error: 'Robinhood did not provide a client ID' }, 502);
    await env.ACCOUNT_SESSIONS.getByName(session).begin({ state, verifier, client_id: client.client_id, redirectUri, started: Date.now() });
    const authorization = new URL(AUTHORIZE);
    authorization.searchParams.set('response_type', 'code');
    authorization.searchParams.set('client_id', client.client_id);
    authorization.searchParams.set('redirect_uri', redirectUri);
    authorization.searchParams.set('code_challenge', challenge);
    authorization.searchParams.set('code_challenge_method', 'S256');
    authorization.searchParams.set('state', state);
    authorization.searchParams.set('resource', RESOURCE);
    authorization.searchParams.set('scope', 'internal');
    return redirect(authorization.toString(), session);
  }
  if (url.pathname === '/api/callback' && request.method === 'GET') {
    const session = cookie(request);
    if (!session || !url.searchParams.get('state') || !url.searchParams.get('code') || (url.searchParams.get('iss') && url.searchParams.get('iss') !== RESOURCE)) return redirect('/?connection=failed');
    const account = env.ACCOUNT_SESSIONS.getByName(session);
    const flow = await account.consume(url.searchParams.get('state'));
    if (!flow || flow.redirectUri !== `${url.origin}/api/callback`) return redirect('/?connection=failed');
    const response = await fetch(TOKEN, {
      method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded', Accept: 'application/json' },
      body: new URLSearchParams({ grant_type: 'authorization_code', code: url.searchParams.get('code'), redirect_uri: flow.redirectUri, client_id: flow.client_id, code_verifier: flow.verifier, resource: RESOURCE }),
    });
    if (!response.ok) return redirect('/?connection=failed');
    const token = await response.json();
    if (typeof token.access_token !== 'string' || typeof token.refresh_token !== 'string') return redirect('/?connection=failed');
    let agentic;
    try { agentic = await agenticAccount(token.access_token); }
    catch { return redirect('/?connection=failed'); }
    await account.connect({ ...token, client_id: flow.client_id, account_number: agentic.number, account_last4: agentic.last4, account_type: agentic.type, connected_at: new Date().toISOString(), expires_at: Date.now() + Number(token.expires_in || 3600) * 1000 });
    return redirect('/portfolios.html?connected=1');
  }
  if (url.pathname === '/api/disconnect' && request.method === 'POST') {
    if (!validOrigin(request)) return json({ error: 'Invalid origin' }, 403);
    const session = cookie(request);
    if (session) await env.ACCOUNT_SESSIONS.getByName(session).disconnect();
    return json({ connected: false });
  }
  return json({ error: 'Not found' }, 404);
}
