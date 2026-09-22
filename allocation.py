"""Portfolio allocation rules shared by research previews and the live operator."""

from decimal import Decimal

MAX_NAME_WEIGHT = Decimal('0.20')


def cap_weights(raw, cap=MAX_NAME_WEIGHT):
    """Preserve relative weights while limiting each stock to a fixed share."""
    values = {symbol: Decimal(str(weight)) for symbol, weight in raw.items() if Decimal(str(weight)) > 0}
    if not values or len(values) * cap < 1:
        raise ValueError('Portfolio needs enough holdings for the position cap')
    if sum(values.values()) <= 0:
        raise ValueError('Empty portfolio')
    allocated = {}
    remaining = values.copy()
    remaining_share = Decimal(1)
    while remaining:
        total = sum(remaining.values())
        oversized = {symbol for symbol, weight in remaining.items() if weight / total * remaining_share > cap}
        if not oversized:
            allocated.update({symbol: weight / total * remaining_share for symbol, weight in remaining.items()})
            break
        for symbol in oversized:
            allocated[symbol] = cap
            remaining_share -= cap
            del remaining[symbol]
    return {symbol: float(weight) for symbol, weight in allocated.items()}
