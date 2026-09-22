"""Turn a disclosed book into weights and unsent Robinhood orders."""

from datetime import date, datetime, timedelta

MIN_ORDER = 1.0
# Filings posted inside this window are copied on the filing date.
# The trade itself can still be up to 45 days older. That clock is the STOCK Act.
FRESH_DAYS = 45


def parse_day(value):
    if isinstance(value, date):
        return value
    return datetime.strptime(value, "%Y-%m-%d").date()


def midpoint(amount_min, amount_max):
    lo = float(amount_min)
    hi = float(amount_max) if amount_max else lo
    return (lo + hi) / 2.0


def net_notionals(trades, today, lookback_days=365):
    """Net disclosed stock dollars by ticker. Buys add the band midpoint, sells subtract it."""
    today = parse_day(today)
    cutoff = today - timedelta(days=lookback_days)
    nets = {}
    for trade in trades:
        if trade.get("asset_type") != "ST" or not trade.get("ticker"):
            continue
        when = parse_day(trade["transacted"])
        if when < cutoff or when > today:
            continue
        sign = 1 if trade["side"] == "buy" else -1 if trade["side"] == "sell" else 0
        if not sign:
            continue
        nets[trade["ticker"]] = nets.get(trade["ticker"], 0.0) + sign * midpoint(
            trade["amount_min"], trade["amount_max"]
        )
    return nets


def positive_weights(notionals):
    kept = {ticker: value for ticker, value in notionals.items() if value > 0}
    total = sum(kept.values())
    if total <= 0:
        return {}
    return {ticker: value / total for ticker, value in kept.items()}


def weights_from_values(pairs, top_n=15):
    """pairs: (ticker, dollars). Returns weights, plus how much of the book the cut covers."""
    ranked = sorted((ticker, float(value)) for ticker, value in pairs if value > 0)
    ranked.sort(key=lambda item: item[1], reverse=True)
    total = sum(value for _, value in ranked)
    chosen = ranked[:top_n]
    chosen_total = sum(value for _, value in chosen)
    if chosen_total <= 0:
        return {}, {"names": 0, "names_kept": 0, "coverage": 0.0}
    weights = {ticker: value / chosen_total for ticker, value in chosen}
    return weights, {
        "names": len(ranked),
        "names_kept": len(chosen),
        "coverage": chosen_total / total if total else 0.0,
    }


def propose(weights, dollars, held=None, min_order=MIN_ORDER):
    """Opening buys, or sells when held dollars already exceed the target. Nothing is sent."""
    dollars = float(dollars)
    if dollars <= 0:
        raise ValueError("dollars must be positive")
    held = held or {}
    raw = []
    for ticker, weight in weights.items():
        target = weight * dollars
        delta = target - float(held.get(ticker, 0.0))
        if abs(delta) >= min_order:
            raw.append((ticker, delta))
    orders = []
    for ticker, delta in sorted(raw, key=lambda item: abs(item[1]), reverse=True):
        orders.append(
            {
                "symbol": ticker,
                "side": "buy" if delta > 0 else "sell",
                "type": "market",
                "dollar_amount": f"{abs(delta):.2f}",
                "market_hours": "regular_hours",
                "time_in_force": "gfd",
            }
        )
    spent = sum(float(order["dollar_amount"]) for order in orders if order["side"] == "buy")
    return orders, round(dollars - spent, 2)


def fit_to_cash(orders, cash, min_order=MIN_ORDER):
    """Scale buys so they do not ask for more cash than the account can spend."""
    cash = float(cash)
    buys = [order for order in orders if order["side"] == "buy"]
    needed = sum(float(order["dollar_amount"]) for order in buys)
    if needed <= cash:
        return buys, round(cash - needed, 2)
    if cash < min_order or needed <= 0:
        return [], round(cash, 2)
    scale = cash / needed
    fitted = []
    for order in buys:
        amount = float(order["dollar_amount"]) * scale
        if amount >= min_order:
            fitted.append({**order, "dollar_amount": f"{amount:.2f}"})
    used = sum(float(order["dollar_amount"]) for order in fitted)
    return fitted, round(cash - used, 2)


def blend_weights(parts):
    """parts: (fraction, {ticker: weight}). Fractions should sum to 1."""
    mixed = {}
    for fraction, weights in parts:
        for ticker, weight in weights.items():
            mixed[ticker] = mixed.get(ticker, 0.0) + float(fraction) * float(weight)
    total = sum(mixed.values())
    if total <= 0:
        return {}
    return {ticker: value / total for ticker, value in mixed.items()}


def rebalance_to(held_values, weights, extra_cash=0, min_order=MIN_ORDER):
    """Sell holdings down and buy the target mix. extra_cash is spent, not sold."""
    equity = sum(float(value) for value in held_values.values()) + float(extra_cash)
    targets = {ticker: float(weight) * equity for ticker, weight in weights.items()}
    sells, buys = [], []
    for symbol in set(held_values) | set(targets):
        delta = targets.get(symbol, 0.0) - float(held_values.get(symbol, 0.0))
        if delta <= -min_order:
            sells.append(_order(symbol, "sell", -delta))
        elif delta >= min_order:
            buys.append(_order(symbol, "buy", delta))
    sells.sort(key=lambda order: float(order["dollar_amount"]), reverse=True)
    buys.sort(key=lambda order: float(order["dollar_amount"]), reverse=True)
    return sells + buys


def _order(ticker, side, amount):
    return {
        "symbol": ticker,
        "side": side,
        "type": "market",
        "dollar_amount": f"{amount:.2f}",
        "market_hours": "regular_hours",
        "time_in_force": "gfd",
    }


def copy_fresh(trades, dollars, today, fresh_days=FRESH_DAYS, min_order=MIN_ORDER):
    """Copy a filing the day it is public.

    Each fresh stock buy is a slice of the allocation: band midpoint divided by
    the disclosed book. Sales are reported and not staged until the sleeve holds
    the shares. If nothing was filed inside the window, the newest filing is used.
    """
    dollars = float(dollars)
    stock = [trade for trade in trades if trade.get("asset_type") == "ST" and trade.get("ticker") and trade.get("filed")]
    if not stock:
        return [], round(dollars, 2), {"mode": "empty", "filed": None, "lag_days": None, "trades": []}
    today_d = parse_day(today)
    newest = max(trade["filed"] for trade in stock)
    cutoff = (today_d - timedelta(days=fresh_days)).isoformat()
    fresh = [trade for trade in stock if trade["filed"] >= cutoff]
    mode = "fresh"
    if not fresh:
        fresh = [trade for trade in stock if trade["filed"] == newest]
        mode = "latest"
    book = sum(value for value in net_notionals(stock, today, lookback_days=730).values() if value > 0)
    grouped = {}
    shown = []
    for trade in fresh:
        mid = midpoint(trade["amount_min"], trade["amount_max"])
        grouped[(trade["ticker"], trade["side"])] = grouped.get((trade["ticker"], trade["side"]), 0.0) + mid
        shown.append(
            {
                **trade,
                "lag_days": (parse_day(trade["filed"]) - parse_day(trade["transacted"])).days,
            }
        )
    if book <= 0:
        book = sum(mid for (_ticker, side), mid in grouped.items() if side == "buy") or 1.0
    raw = []
    for (ticker, side), mid in grouped.items():
        amount = dollars * min(1.0, mid / book)
        if amount >= min_order:
            raw.append((ticker, side, amount))
    buy_total = sum(amount for _ticker, side, amount in raw if side == "buy")
    scale = min(1.0, dollars / buy_total) if buy_total > dollars else 1.0
    orders = []
    for ticker, side, amount in sorted(raw, key=lambda item: item[2], reverse=True):
        if side != "buy":
            continue
        sized = amount * scale
        if sized >= min_order:
            orders.append(_order(ticker, side, sized))
    spent = sum(float(order["dollar_amount"]) for order in orders)
    lags = [trade["lag_days"] for trade in shown]
    return orders, round(dollars - spent, 2), {
        "mode": mode,
        "filed": max(trade["filed"] for trade in fresh),
        "lag_days": min(lags) if lags else None,
        "trades": sorted(shown, key=lambda trade: trade["transacted"], reverse=True),
    }


def _demo():
    weights, meta = weights_from_values([("AAPL", 70), ("MSFT", 30), ("X", 0)], top_n=15)
    assert abs(weights["AAPL"] - 0.7) < 1e-9 and abs(sum(weights.values()) - 1) < 1e-9
    assert meta["names_kept"] == 2
    orders, leftover = propose(weights, 1000)
    assert orders[0]["symbol"] == "AAPL" and orders[0]["dollar_amount"] == "700.00"
    assert leftover == 0
    sells, _ = propose({"AAPL": 1.0}, 100, {"AAPL": 150})
    assert sells == [
        {
            "symbol": "AAPL",
            "side": "sell",
            "type": "market",
            "dollar_amount": "50.00",
            "market_hours": "regular_hours",
            "time_in_force": "gfd",
        }
    ]
    dust, left = propose({"AAPL": 0.99, "TINY": 0.01}, 10)
    assert [order["symbol"] for order in dust] == ["AAPL"]
    assert left == 0.1
    nets = net_notionals(
        [
            {"ticker": "AAPL", "side": "buy", "amount_min": 1001, "amount_max": 15000, "asset_type": "ST", "transacted": "2026-01-01"},
            {"ticker": "AAPL", "side": "sell", "amount_min": 1001, "amount_max": 15000, "asset_type": "ST", "transacted": "2026-02-01"},
            {"ticker": "MSFT", "side": "buy", "amount_min": 15001, "amount_max": 50000, "asset_type": "ST", "transacted": "2026-02-01"},
            {"ticker": "OPT", "side": "buy", "amount_min": 1001, "amount_max": 15000, "asset_type": "OP", "transacted": "2026-02-01"},
            {"ticker": "OLD", "side": "buy", "amount_min": 15001, "amount_max": 50000, "asset_type": "ST", "transacted": "2024-01-01"},
        ],
        today="2026-09-22",
    )
    assert "AAPL" not in positive_weights(nets)
    assert list(positive_weights(nets)) == ["MSFT"]
    sample = [
        {"ticker": "MSFT", "side": "buy", "amount_min": 15001, "amount_max": 50000, "asset_type": "ST", "transacted": "2026-02-01", "filed": "2026-02-20"},
        {"ticker": "AAPL", "side": "buy", "amount_min": 1001, "amount_max": 15000, "asset_type": "ST", "transacted": "2026-08-20", "filed": "2026-09-10"},
        {"ticker": "AAPL", "side": "sell", "amount_min": 15001, "amount_max": 50000, "asset_type": "ST", "transacted": "2026-08-28", "filed": "2026-09-12"},
    ]
    orders, _left, info = copy_fresh(sample, 1000, "2026-09-22")
    assert info["mode"] == "fresh" and info["filed"] == "2026-09-12"
    assert info["lag_days"] == 15
    assert [order["symbol"] for order in orders] == ["AAPL"]
    assert all(order["side"] == "buy" for order in orders)
    assert float(orders[0]["dollar_amount"]) < 1000
    old = [dict(sample[0], filed="2026-01-15")]
    _orders, _left, info = copy_fresh(old, 1000, "2026-09-22")
    assert info["mode"] == "latest" and info["filed"] == "2026-01-15"
    fitted, left = fit_to_cash([_order("AAPL", "buy", 400), _order("MSFT", "buy", 400)], 1.50)
    assert fitted == [] and left == 1.50
    mixed = blend_weights([(0.5, {"AAPL": 1.0}), (0.5, {"MSFT": 1.0})])
    assert abs(mixed["AAPL"] - 0.5) < 1e-9 and abs(sum(mixed.values()) - 1) < 1e-9
    plan = rebalance_to({"AAPL": 100, "MSFT": 100}, {"AAPL": 0.5, "NVDA": 0.5})
    assert [(order["side"], order["symbol"], order["dollar_amount"]) for order in plan] == [
        ("sell", "MSFT", "100.00"),
        ("buy", "NVDA", "100.00"),
    ]
    funded = rebalance_to({"AAPL": 100}, {"NVDA": 1.0}, extra_cash=50)
    assert ("buy", "NVDA", "150.00") in [(order["side"], order["symbol"], order["dollar_amount"]) for order in funded]
    fitted, left = fit_to_cash([_order("AAPL", "buy", 60), _order("MSFT", "buy", 40)], 10)
    assert sum(float(order["dollar_amount"]) for order in fitted) <= 10
    print("book ok")


if __name__ == "__main__":
    _demo()
