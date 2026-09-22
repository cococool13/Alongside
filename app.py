"""Alongside server. Serves the site and saves a rebalance plan. It does not send orders."""

import json
import re
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from book import fit_to_cash
from filings import INVESTORS, book_for, load_13f, politician_rows, refresh_house, ticker_index
from publish import build
from planner import build_proposal
from mandate import request_mandate

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "state"
SITE = ROOT / "site"
MAX_DOLLARS = 1_000_000
HOST = "127.0.0.1"
PORT = 8765
LOCK = threading.Lock()
CACHE = {"mtime": None, "house": {"trades": []}, "rows": []}
TYPES = {".html": "text/html; charset=utf-8", ".json": "application/json", ".css": "text/css", ".js": "text/javascript"}


def cached_house():
    path = STATE / "house" / "trades.json"
    with LOCK:
        mtime = path.stat().st_mtime if path.exists() else None
        if CACHE["mtime"] != mtime:
            house = json.loads(path.read_text()) if path.exists() else {"trades": [], "refreshed": None}
            CACHE["house"] = house
            CACHE["rows"] = politician_rows(house.get("trades", []), datetime.now().date().isoformat())
            CACHE["mtime"] = mtime
        return CACHE["house"], CACHE["rows"]


def load_broker():
    path = STATE / "broker.json"
    if not path.exists():
        return {"label": "Your account", "updated": None, "equity": 0, "buying_power": 0, "positions": []}
    raw = json.loads(path.read_text())
    return {
        "label": "Agentic account",
        "updated": raw.get("updated"),
        "equity": raw.get("equity", 0),
        "buying_power": raw.get("buying_power", 0),
        "positions": raw.get("positions", []),
    }


def live_book(pilot_id, dollars):
    book = book_for(pilot_id, dollars, STATE)
    broker = load_broker()
    fitted, _left = fit_to_cash(book["orders"], broker["buying_power"])
    book["cash_orders"] = fitted
    book["buying_power"] = broker["buying_power"]
    return book


def read_dollars(value):
    dollars = float(value)
    if dollars < 1 or dollars > MAX_DOLLARS:
        raise ValueError(f"Allocation has to be between $1 and ${MAX_DOLLARS:,.0f}")
    return dollars


def clean_orders(raw):
    orders = []
    for order in raw[:60]:
        symbol = str(order.get("symbol", "")).upper()
        side = order.get("side")
        amount = float(order.get("dollar_amount", 0))
        if not re.fullmatch(r"[A-Z.]{1,6}", symbol) or side not in {"buy", "sell"}:
            continue
        if amount < 1 or amount > MAX_DOLLARS:
            continue
        orders.append({
            "symbol": symbol,
            "side": side,
            "type": "market",
            "dollar_amount": f"{amount:.2f}",
            "market_hours": "regular_hours",
            "time_in_force": "gfd",
        })
    return orders


def save_plan(body):
    orders = clean_orders(body.get("orders") or [])
    payload = {
        "armed_at": datetime.now(timezone.utc).isoformat(),
        "sent": False,
        "name": str(body.get("name") or "Mix")[:120],
        "dollars": body.get("dollars"),
        "sell_holdings": bool(body.get("sell")),
        "orders": orders,
        "note": "Saved on this Mac. Not sent to Robinhood.",
    }
    path = STATE / "armed.json"
    path.write_text(json.dumps(payload, indent=2))
    return payload


class Handler(BaseHTTPRequestHandler):
    def _trusted_host(self):
        return self.headers.get("Host") in {f"{HOST}:{PORT}", f"localhost:{PORT}"}

    def _send(self, code, body, content_type):
        data = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, code, payload):
        self._send(code, json.dumps(payload), "application/json")

    def log_message(self, fmt, *args):
        return

    def do_GET(self):
        if not self._trusted_host():
            self._json(403, {"error": "Local host required"})
            return
        parsed = urlparse(self.path)
        if parsed.path == "/api/account":
            self._json(200, load_broker())
            return
        if parsed.path == "/api/book":
            query = parse_qs(parsed.query)
            try:
                self._json(200, live_book(query.get("id", [""])[0], read_dollars(query.get("dollars", ["1000"])[0])))
            except (KeyError, StopIteration):
                self._json(404, {"error": "Unknown pilot"})
            except ValueError as error:
                self._json(400, {"error": str(error)})
            except Exception as error:
                self._json(502, {"error": f"Filing fetch failed: {error}"})
            return
        rel = "index.html" if parsed.path == "/" else parsed.path.lstrip("/")
        file = (SITE / rel).resolve()
        if file.is_file() and file.is_relative_to(SITE.resolve()):
            self._send(200, file.read_bytes(), TYPES.get(file.suffix, "application/octet-stream"))
            return
        self._json(404, {"error": "Not found"})

    def do_POST(self):
        if not self._trusted_host():
            self._json(403, {"error": "Local host required"})
            return
        if self.headers.get("Origin") not in (None, f"http://{HOST}:{PORT}"):
            self._json(403, {"error": "Local origin required"})
            return
        if urlparse(self.path).path == "/api/mandate":
            try:
                size = int(self.headers.get("content-length", "0"))
                if not 0 < size <= 4096:
                    raise ValueError("Invalid request size")
                body = json.loads(self.rfile.read(size))
                self._json(200, request_mandate(SITE, STATE, body))
            except (ValueError, TypeError, KeyError) as error:
                self._json(400, {"error": str(error)})
            return
        if urlparse(self.path).path == "/api/proposal":
            try:
                size = int(self.headers.get("content-length", "0"))
                if not 0 < size <= 4096:
                    raise ValueError("Invalid request size")
                body = json.loads(self.rfile.read(size))
                proposal = build_proposal(SITE, load_broker(), body.get("picks", []))
                if body.get("save") is True:
                    (STATE / "alongside_draft.json").write_text(json.dumps(proposal, indent=2))
                self._json(200, proposal)
            except (ValueError, TypeError, KeyError) as error:
                self._json(400, {"error": str(error)})
            return
        if urlparse(self.path).path != "/api/arm":
            self._json(404, {"error": "Not found"})
            return
        try:
            size = int(self.headers.get("content-length", "0"))
            body = json.loads(self.rfile.read(min(size, 200_000)) or b"{}")
            self._json(200, save_plan(body))
        except (ValueError, TypeError) as error:
            self._json(400, {"error": str(error)})


def watch():
    import time
    while True:
        try:
            refresh_house(STATE)
            CACHE["mtime"] = None
        except Exception as error:
            print("watch", error)
        time.sleep(600)


def warm_investors():
    index = ticker_index(STATE)
    for cik, name, _person, _slug in INVESTORS:
        try:
            filing = load_13f(cik, STATE, index)
            print(f"{name}: {filing['as_of']} filed {filing['filed']}")
        except Exception as error:
            print(f"{name} failed: {error}")


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else "serve"
    if command == "refresh":
        refresh_house(STATE)
        warm_investors()
        build()
        return
    if command == "preview":
        book = live_book(sys.argv[2], read_dollars(sys.argv[3]))
        print(json.dumps({key: book[key] for key in ("name", "buying_power", "orders", "cash_orders")}, indent=2))
        return
    if command != "serve":
        raise SystemExit("use refresh, preview <slug> <dollars>, or serve")
    threading.Thread(target=watch, daemon=True).start()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
