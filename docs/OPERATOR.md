# Alongside Agentic operator

This runbook replaces QCC-1 when `state/mandate.json` has `"status": "requested"`
or `"status": "active"`. Otherwise the existing QCC-1 operator remains in charge.
It applies only to Robinhood Agentic ••••5634. The public Worker is research
only; broker calls happen through the authenticated Robinhood Trading MCP in
the scheduled agent, never from browser JavaScript or Python credentials.

## Each scheduled run

1. Read `state/mandate.json`. Stop unless its status is requested or active and
   its portfolio, cadence, and order-type fields are complete. Claim a
   run with `python3 operator_journal.py claim`. If an order is unresolved,
   claim with `--reconcile`, inspect the broker's order history, record the
   known broker outcome against its original reference ID, then stop.
2. Call `get_accounts` and verify the designated account is active, cash type,
   and available to this agent. Read `get_portfolio`, all pages of
   `get_equity_positions`, and recent `get_equity_orders`. Stop on any open,
   partially filled, or uncertain order until its broker state is reconciled.
   For a journaled submission with a final broker state, run
   `python3 operator_journal.py settle RUN_ID REF_ID BROKER_STATE`.
3. Check US regular market hours and a fresh, active quote for every held and
   target symbol. Check `get_equity_tradability` for all planned symbols. Use
   the broker's live buying power. Require `site/pilots.json` to be at most
   three calendar days old; selected 13Fs at most 150 days old and House
   disclosures at most 60 days old. Reject a stale dataset, an invalid
   target, or any non-equity positions. Never infer a tradable account from a
   nickname. For a requested transition, call `python3 mandate.py promote`
   only after these checks pass. Then re-read the active mandate.
4. Build target weights from the saved portfolio IDs and percentages against
   current `site/pilots.json`; apply `allocation.cap_weights` (20% per name).
   On a routine run, rebalance only when the selected portfolio fingerprint changes, and
   skip a rebalance when weights and positions are within the code's drift
   threshold. The initial strategy transition runs once after activation.
   Write `state/live_snapshot.json` from these MCP reads with `account_number`,
   `account_type: "cash"`, current UTC `updated`, broker `total_value` as
   `account_value`, broker `buying_power`, all `open_orders`, and `positions`
   with `symbol`, `quantity`, `shares_available_for_sells`, and the verified
   live `price`. Run `python3 operator_plan.py RUN_ID`. Treat the result
   as one leg only. A sell result means submit sells and stop for the run. A
   settlement result means wait and check again at the next scheduled slot.
5. Before every real order, use `operator_journal.py prepare` to persist a
   UUID `ref_id` and intended parameters. Call `review_equity_order` with exactly those
   parameters (`market_hours: regular_hours`, `time_in_force: gfd`). Stop on a
   non-empty broker alert. Call `place_equity_order`
   once with the same parameters and `ref_id`. Read the resulting order state
   and use `operator_journal.py record` with its broker ID/status. On uncertain
   response, read broker orders before
   any retry; reuse the same `ref_id` if a retry is justified.
6. Re-read live positions and buying power after fills. Do not use projected
   sale proceeds for buys. The cash account's sells and buys can span trading
   days. Recompute the buy leg only when the broker reports spendable funds.
7. Release the journal lease. Record the run time, filing date, target weights,
   account value, fills, and any stop reason in the journal. Notify Cohen on
   a trade, failure, meaningful drift, or required input; include the broker's
   market-data disclosure verbatim when an order was reviewed.

## Hard stops

- No active mandate, unclear account, stale quotes, market closed, stale local
  filing dataset, open orders, uncertain previous submission, insufficient
  buying power, broker alert, untradable symbol, or position cap violation.
- No options, crypto, margin, leverage, transfers, or trades in another account.
- No new order from a website request. A browser may save a mandate; only the
  scheduled operator can trade after live checks.

The live order type and filing-update trigger are recorded in the mandate. Dollar
buys need regular-hours market orders; whole-share limit orders need a separate
sizing path. Until those fields and selected portfolios are set, the operator
must stop.
