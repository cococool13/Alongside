"""Write the public site data. Holdings stay out of the account number."""

import json
from datetime import datetime
from pathlib import Path

from book import copy_fresh, net_notionals, positive_weights
from filings import INVESTORS, book_for, load_house, politician_rows

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "state"
SITE = ROOT / "site"


def _pilot(pilot_id, name, who, kind, weights, as_of, note):
    clean = {ticker: round(weight, 6) for ticker, weight in weights.items() if weight > 0}
    return {
        "id": pilot_id,
        "name": name,
        "who": who,
        "kind": kind,
        "as_of": as_of,
        "note": note,
        "weights": clean,
    }


def build(today=None):
    today = today or datetime.now().date().isoformat()
    house = load_house(STATE)
    grouped = {}
    for trade in house.get("trades", []):
        grouped.setdefault(trade["key"], []).append(trade)
    pilots = []
    for _cik, name, person, slug in INVESTORS:
        book = book_for("inv:" + slug, 100, STATE, today)
        pilots.append(
            _pilot(
                book["id"],
                book["name"],
                book["who"],
                "13f",
                {row["ticker"]: row["weight"] for row in book["holdings"]},
                book["as_of"],
                book["note"],
            )
        )
    for row in politician_rows(house.get("trades", []), today)[:24]:
        items = grouped[row["id"].removeprefix("house:")]
        weights = positive_weights(net_notionals(items, today))
        _orders, _left, info = copy_fresh(items, 100, today)
        pilots.append(
            _pilot(
                row["id"],
                row["name"],
                row["state"],
                "congress",
                weights,
                info.get("filed") or row["filed"],
                "Disclosed stock book. A new filing is copied into this mix on the next refresh.",
            )
        )
    SITE.mkdir(exist_ok=True)
    (SITE / "pilots.json").write_text(json.dumps({"as_of": today, "pilots": pilots}))
    print(f"pilots {len(pilots)}")
    return pilots


if __name__ == "__main__":
    build()
