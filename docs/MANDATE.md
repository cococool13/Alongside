# Mandate handoff

The active QCC-1 strategy remains in force until Cohen selects one or two
Alongside portfolios and activates a mandate. The user has authorized replacing
QCC-1, but has not yet chosen the actual holdings. Rebalancing is triggered
by a changed published holdings fingerprint, not a calendar date.

The transition uses the Agentic cash account only. Full-position sells happen
first. The operator reconciles their fills and waits for buying power before
placing buys. The selected portfolios are recomputed from public disclosure
weights at each allowed rebalance, with a 20% single-stock cap carried forward
from the current account risk rule. A 90-day holdings price change is a ranking
signal, not a forward return estimate.

`state/alongside_draft.json` is a research preview. It is never executable.
`state/mandate.json` will carry activation, portfolio IDs, percentages, cadence,
order type, and an activation timestamp. `state/execution.json` will be the
operator's order journal. Both files stay uncommitted in `state/`.
