# Alongside

Local research app. It turns public House periodic transaction reports and SEC 13F filings into a weighted book and a Robinhood order list. The list is written to `state/staged.json`. This app does not send orders.

## Stack

Python 3 standard library. House PDFs need `pdftotext` from Poppler. No package install. Cache lives in `state/` and stays uncommitted.

## Commands

```bash
python3 book.py
python3 filings.py
python3 app.py refresh
python3 app.py preview berkshire 1000
python3 app.py
```

The server is http://127.0.0.1:8765
The public site is https://alongside.cohencool.workers.dev
`python3 publish.py && python3 returns.py`, then `npx wrangler deploy`.

## Rails

- Do not place Robinhood orders from this folder until Cohen explicitly says to send the saved plan. Then `review_equity_order` before every `place_equity_order` on the Agentic account.
- A saved plan may sell the current holdings and buy a mix of portfolios. Do not send that plan unless he asked to place it.
- The Agentic account runs QCC-1 in `~/Projects/Agentic Account`.
- Congress amounts are bands. 13Fs are quarter-end and late. Say that when quoting a book.
- Do not print secrets. Do not commit `state/`.
