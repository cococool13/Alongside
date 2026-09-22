import { oauth, AccountSession } from './oauth.js';
export { AccountSession };

export default {
  async fetch(request, env) {
    const path = new URL(request.url).pathname;
    if (path.startsWith('/api/')) {
      if (['/api/connect', '/api/callback', '/api/connection', '/api/disconnect', '/api/selection'].includes(path)) {
        try { return await oauth(request, env); }
        catch { return Response.json({ error: 'Connection unavailable' }, { status: 502, headers: { 'Cache-Control': 'no-store' } }); }
      }
      return Response.json({ error: 'Not available on the public site' }, { status: 404 });
    }
    return env.ASSETS.fetch(request);
  },
};
