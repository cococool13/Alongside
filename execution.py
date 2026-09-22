"""Deterministic order intents for an Agentic-account Alongside mandate.

This module never calls Robinhood. An MCP operator must verify live state and
review each intent before submitting an order.
"""

from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN

EXPECTED_ACCOUNT = "565755634"
MIN_NOTIONAL = Decimal("1.00")
DRIFT_DOLLARS = Decimal("5.00")


def number(value):
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("Non-finite account value")
    return result


def live_snapshot(snapshot):
    if snapshot.get("account_number") != EXPECTED_ACCOUNT or snapshot.get("account_type") != "cash":
        raise ValueError("Only the designated Agentic cash account is supported")
    updated = datetime.fromisoformat(str(snapshot.get("updated", "")).replace("Z", "+00:00"))
    if updated.tzinfo is None or not 0 <= (datetime.now(timezone.utc) - updated).total_seconds() <= 300:
        raise ValueError("Live account snapshot must be less than five minutes old")
    if snapshot.get("open_orders"):
        raise ValueError("Reconcile open orders before planning")
    if number(snapshot.get("buying_power", 0)) < 0:
        raise ValueError("Invalid buying power")


def order_intents(target_weights, snapshot):
    """Return one leg at a time; buy leg is recomputed after sells settle."""
    live_snapshot(snapshot)
    if not target_weights or any(number(weight) <= 0 for weight in target_weights.values()):
        raise ValueError("Invalid target weights")
    total_weight = sum((number(weight) for weight in target_weights.values()), Decimal(0))
    if abs(total_weight - 1) > Decimal("0.0001"):
        raise ValueError("Target weights must total 100%")
    positions = {}
    for row in snapshot.get("positions", []):
        symbol = str(row["symbol"]).upper()
        if symbol in positions:
            raise ValueError("Duplicate position")
        quantity = number(row["quantity"])
        sellable = number(row["shares_available_for_sells"])
        price = number(row["price"])
        if quantity < 0 or sellable < 0 or sellable > quantity or price <= 0:
            raise ValueError("Invalid position")
        positions[symbol] = (quantity, sellable, price)
    buying_power = number(snapshot["buying_power"])
    account_value = number(snapshot["account_value"])
    if account_value <= 0:
        raise ValueError("Invalid account value")
    sells = []
    for symbol, (quantity, sellable, price) in positions.items():
        target = account_value * number(target_weights.get(symbol, 0))
        excess = quantity * price - target
        if excess < max(MIN_NOTIONAL, DRIFT_DOLLARS):
            continue
        if sellable <= 0:
            raise ValueError(f"{symbol} is not available for sale")
        shares = sellable if target == 0 else min(sellable, (excess / price).quantize(Decimal("0.000001"), rounding=ROUND_DOWN))
        if shares * price >= MIN_NOTIONAL:
            sells.append({"symbol": symbol, "side": "sell", "quantity": format(shares, "f"), "type": "market"})
    if sells:
        return {"phase": "sell", "orders": sorted(sells, key=lambda row: row["symbol"])}
    buys = []
    for symbol, weight in target_weights.items():
        held_value = positions.get(symbol, (Decimal(0), Decimal(0), Decimal(0)))[0] * positions.get(symbol, (Decimal(0), Decimal(0), Decimal(0)))[2]
        deficit = account_value * number(weight) - held_value
        if deficit >= max(MIN_NOTIONAL, DRIFT_DOLLARS):
            buys.append((symbol, deficit))
    needed = sum((amount for _, amount in buys), Decimal(0))
    if needed and buying_power < needed * Decimal("0.98"):
        return {"phase": "await_settlement", "orders": []}
    scale = min(Decimal(1), buying_power / needed) if needed else Decimal(1)
    orders = [{"symbol": symbol, "side": "buy", "dollar_amount": format((amount * scale).quantize(Decimal("0.01"), rounding=ROUND_DOWN), "f"), "type": "market"} for symbol, amount in sorted(buys) if (amount * scale).quantize(Decimal("0.01"), rounding=ROUND_DOWN) >= MIN_NOTIONAL]
    return {"phase": "buy" if orders else "complete", "orders": orders}
