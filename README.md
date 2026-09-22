# Alongside

Public portfolios from House disclosures and SEC 13Fs. Ranked by the 90-day price change of the current holdings.

https://alongside.cohencool.workers.dev

```bash
python3 book.py
python3 filings.py
python3 app.py
```

`state/` stays on this Mac. The public site uses Robinhood OAuth; it never sees
the Robinhood password. The OAuth token and selected portfolio are stored in a
per-browser Cloudflare Durable Object. Disconnect deletes that local token;
revoking the connection in Robinhood removes the Robinhood grant.

On the local server (`python3 app.py`), the mix page can compare selected portfolios
with a recent `state/broker.json` snapshot. It previews sell orders, buys covered by
current buying power, and buys that depend on settled sale proceeds. Saving writes
`state/alongside_draft.json`, an unsent research draft. It does not modify the
Agentic account's active QCC-1 plan or place trades. The public Worker cannot
read the local account snapshot or save a draft.

The local mix screen can also request a strategy switch. That writes
`state/mandate.json` with `status: requested`; the agent must verify live
Robinhood data before promoting it and sending orders. See
`docs/OPERATOR.md` for the scheduled two-leg execution path. A requested or
active mandate routes the existing Agentic operator away from QCC-1. There is
currently no running Alongside background operator; saving a mandate or a
hosted portfolio selection alone does not start autonomous trading. A
published portfolio change is the rebalance trigger once those services exist.
