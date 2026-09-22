"""Build an unsent Alongside proposal from public weights and a local snapshot."""

import json
from datetime import datetime, timezone
from pathlib import Path

from book import blend_weights, fit_to_cash, rebalance_to
from allocation import cap_weights


def portfolio_index(site: Path):
    data = json.loads((site / "pilots.json").read_text())
    return {row["id"]: row for row in data["pilots"]}, data["as_of"]


def build_proposal(site: Path, broker: dict, picks: list[dict]):
    if not 1 <= len(picks) <= 2:
        raise ValueError("Choose one or two portfolios")
    pilots, data_date = portfolio_index(site)
    ids = [item.get("id") for item in picks]
    if len(set(ids)) != len(ids) or any(identifier not in pilots for identifier in ids):
        raise ValueError("Invalid portfolio selection")
    shares = [float(item.get("percent", 0)) for item in picks]
    if any(not 0 < share <= 100 for share in shares) or abs(sum(shares) - 100) > 0.01:
        raise ValueError("Portfolio shares must total 100%")
    if not broker.get("updated"):
        raise ValueError("No local Agentic account snapshot is available")
    updated = datetime.fromisoformat(str(broker["updated"]).replace("Z", "+00:00"))
    if updated.tzinfo is None:
        raise ValueError("Account snapshot needs a timezone")
    age_hours = (datetime.now(timezone.utc) - updated).total_seconds() / 3600
    if age_hours < -1 or age_hours > 24:
        raise ValueError("Account snapshot is stale; refresh it before planning")
    held = {}
    for position in broker.get("positions", []):
        symbol = str(position.get("symbol", "")).upper()
        value = float(position.get("value", 0))
        if symbol and value > 0:
            held[symbol] = held.get(symbol, 0) + value
    buying_power = float(broker.get("buying_power", 0))
    if buying_power < 0:
        raise ValueError("Invalid account buying power")
    weights = cap_weights(blend_weights((share / 100, pilots[identifier]["weights"]) for identifier, share in zip(ids, shares)))
    orders = rebalance_to(held, weights, extra_cash=buying_power)
    sells = [order for order in orders if order["side"] == "sell"]
    buys = [order for order in orders if order["side"] == "buy"]
    buy_now, cash_left = fit_to_cash(buys, buying_power)
    now_by_symbol = {order["symbol"]: float(order["dollar_amount"]) for order in buy_now}
    buy_later = []
    for order in buys:
        remaining = round(float(order["dollar_amount"]) - now_by_symbol.get(order["symbol"], 0), 2)
        if remaining >= 1:
            buy_later.append({**order, "dollar_amount": f"{remaining:.2f}"})
    return {
        "status": "draft_only", "created_at": datetime.now(timezone.utc).isoformat(),
        "account_snapshot_at": broker["updated"], "filings_as_of": data_date,
        "portfolios": [{"id": identifier, "name": pilots[identifier]["name"], "percent": share} for identifier, share in zip(ids, shares)],
        "target_weights": weights, "account_value_estimate": round(sum(held.values()) + buying_power, 2),
        "buying_power": buying_power, "sell_orders": sells, "buy_orders_after_settlement": buy_later,
        "buy_orders_now": buy_now, "cash_left_now": cash_left,
        "note": "Unsent research draft. Does not change the active QCC-1 strategy or place orders.",
    }
