"""90-day price change of each portfolio's largest current holdings."""

import json
import re
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PILOTS = ROOT / "site" / "pilots.json"
UA = {"User-Agent": "Mozilla/5.0 (compatible; Alongside/1.0)"}


def top_weights(weights, n=8):
    ranked = sorted(weights.items(), key=lambda item: item[1], reverse=True)[:n]
    total = sum(weight for _ticker, weight in ranked)
    if total <= 0:
        return {}
    return {ticker: weight / total for ticker, weight in ranked}


def closes(symbol):
    if not re.fullmatch(r"[A-Z.]{1,5}", symbol):
        return None
    yahoo = symbol.replace(".", "-")
    now = int(time.time())
    start = now - 160 * 86400
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        + urllib.parse.quote(yahoo)
        + f"?period1={start}&period2={now}&interval=1d"
    )
    request = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.load(response)
        result = payload["chart"]["result"][0]
        series = result["indicators"]["quote"][0]["close"]
        stamps = result["timestamp"]
    except Exception:
        return None
    pairs = [(stamp, price) for stamp, price in zip(stamps, series) if price]
    if len(pairs) < 40:
        return None
    latest = pairs[-1][1]
    target = pairs[-1][0] - 90 * 86400
    then = min(pairs, key=lambda item: abs(item[0] - target))[1]
    if then <= 0:
        return None
    return latest / then - 1


def main():
    data = json.loads(PILOTS.read_text())
    needed = set()
    trimmed = {}
    for pilot in data["pilots"]:
        weights = top_weights(pilot.get("weights") or {})
        trimmed[pilot["id"]] = weights
        needed.update(weights)
    prices = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(closes, symbol): symbol for symbol in sorted(needed)}
        for future in as_completed(futures):
            prices[futures[future]] = future.result()
    scored = 0
    for pilot in data["pilots"]:
        weights = trimmed[pilot["id"]]
        usable = {ticker: weight for ticker, weight in weights.items() if prices.get(ticker) is not None}
        base = sum(usable.values())
        if base <= 0:
            pilot.pop("return_90d", None)
            continue
        change = sum((weight / base) * prices[ticker] for ticker, weight in usable.items())
        pilot["return_90d"] = round(change * 100, 1)
        pilot["return_coverage"] = round(base, 2)
        scored += 1
    import re
    kept = []
    for pilot in data["pilots"]:
        note = pilot.pop("note", "")
        match = re.search(r"\((\d+)% of the filed", note)
        book = int(match.group(1)) / 100 if match else 1
        weights = pilot.get("weights") or {}
        top = max(weights.values()) if weights else 1
        fresh = pilot.get("as_of", "") >= "2026-03-01"
        priced = pilot.get("return_coverage", 0) >= 0.75 and "return_90d" in pilot
        top5 = sum(weight for _ticker, weight in sorted(weights.items(), key=lambda item: item[1], reverse=True)[:5])
        focused = 4 <= len(weights) <= 25 and top <= 0.45 and top5 >= 0.4
        if focused and book >= 0.7 and fresh and priced:
            ranked = sorted(weights.items(), key=lambda item: item[1], reverse=True)[:10]
            pilot["weights"] = {ticker: round(weight, 4) for ticker, weight in ranked}
            pilot.pop("return_coverage", None)
            kept.append(pilot)
    data["pilots"] = kept
    data["return_window"] = "90-day price change of the largest current holdings"
    PILOTS.write_text(json.dumps(data))
    best = sorted(kept, key=lambda p: -p["return_90d"])[:5]
    print(f"scored {scored} symbols {len(needed)} priced {sum(v is not None for v in prices.values())}")
    for pilot in best:
        print(f"  {pilot['return_90d']:+6.1f}%  {pilot['name']}")


if __name__ == "__main__":
    main()
