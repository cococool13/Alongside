# Robinhood Trading MCP website authorization

Robinhood redirected the public Alongside OAuth attempt to
`https://robinhood.com/oauth/error` on 2026-09-22. The site does not have a
verified Agentic connection. Alongside now keeps `/api/connect` unavailable
until Robinhood approves a production client ID. Do not use a loopback callback,
copy an authorization code, or reuse another agent's OAuth token to bypass this.

Robinhood's public [third-party connections policy](https://robinhood.com/us/en/support/articles/third-party-connections/)
says trading API links require written Robinhood authorization. Its
[Agentic Trading guide](https://robinhood.com/us/en/support/articles/agentic-trading-overview/)
documents the Trading MCP endpoint and directs Robinhood-side errors to support.

Request through Robinhood's official support channel:

> I am building Alongside, a website for following portfolios derived from
> public House transaction disclosures and SEC 13F filings. I want to connect
> my Robinhood Agentic account through the Robinhood Trading MCP using OAuth.
> The site's OAuth authorization currently ends at
> `https://robinhood.com/oauth/error`. Please advise on written authorization
> and an approved production client for this HTTPS callback:
> `https://alongside.cohencool.workers.dev/api/callback`.
> The MCP resource is `https://agent.robinhood.com/mcp/trading`; the requested
> scope is `internal`. The site is for my own account first, with possible
> additional users later. Please confirm whether this use is permitted and
> provide the supported registration and redirect requirements.

Do not send a Robinhood password, authorization code, refresh token, or account
number in the request. Once approved, configure the issued client ID as a
Cloudflare Worker secret named `ROBINHOOD_CLIENT_ID`, then complete an
end-to-end OAuth callback and `get_accounts` check. A successful connection
alone does not enable trades: the portfolio update service, order reconciler,
QCC-1 cutover, and execution safeguards still need live verification.
