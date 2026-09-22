"""Public House PTR filings and SEC 13F holdings. No broker calls."""

import json
import re
import shutil
import subprocess
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from book import copy_fresh, net_notionals, positive_weights, propose, weights_from_values

UA = "Alongside personal research cohen@cohencool.com"
HOUSE = "https://disclosures-clerk.house.gov/public_disc"
# Statutory PTR bands, plus the cap-gains column marker which is not a band.
BANDS = {
    1001, 15000, 15001, 50000, 50001, 100000, 100001, 250000, 250001, 500000,
    500001, 1000000, 1000001, 5000000, 5000001, 25000000, 25000001, 50000000,
}
HEADER = re.compile(
    r"^\s*(SP|JT|DC)?\s+(\S.*?)\s+(P|S(?:\s*\([^)]+\))?|E)\s+"
    r"(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})\s+(\$[\d,]+)"
)
TICKER = re.compile(r"\(([A-Z]{1,5}(?:[.\-][A-Z]{1,2})?)\)")
CODE = re.compile(r"\[([A-Z]{2,3})\]")
# ponytail: name match against SEC's ticker file. CUSIP map if a top holding stays unmapped.
STOP = {
    "INC", "INCORPORATED", "CORP", "CORPORATION", "CO", "COMPANY", "LTD", "LIMITED",
    "PLC", "LLC", "LP", "DEL", "DE", "NEW", "THE", "CLASS", "CL", "COMMON", "STOCK",
    "COM", "HOLDINGS", "HOLDING", "GROUP", "ORD", "SHS", "SHARES", "AND", "FORMERLY", "FKA",
}
INVESTORS = [
    ("1067983", "Berkshire Hathaway", "Warren Buffett", "berkshire"),
    ("1649339", "Scion Asset Management", "Michael Burry", "scion"),
    ("1336528", "Pershing Square", "Bill Ackman", "pershing"),
    ("1656456", "Appaloosa", "David Tepper", "appaloosa"),
    ("1536411", "Duquesne Family Office", "Stanley Druckenmiller", "duquesne"),
    ("1061768", "Baupost Group", "Seth Klarman", "baupost"),
    ("921669", "Icahn Capital", "Carl Icahn", "icahn"),
    ("1040273", "Third Point", "Daniel Loeb", "third-point"),
    ("1167483", "Tiger Global", "Tiger Global", "tiger"),
    ("1061165", "Lone Pine Capital", "Stephen Mandel", "lone-pine"),
    ("1541617", "Altimeter Capital", "Brad Gerstner", "altimeter"),
    ("1037389", "Renaissance Technologies", "Jim Simons", "renaissance"),
]


def get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def iso_mdy(value):
    month, day, year = value.split("/")
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"


def rh_symbol(ticker):
    ticker = ticker.upper().replace(".", "-")
    # Robinhood class shares use a dot: BRK.B, not BRK-B.
    if re.fullmatch(r"[A-Z]+-[A-Z]", ticker):
        return ticker.replace("-", ".")
    return ticker


def parse_ptr(text):
    lines = text.splitlines()
    rows = []
    index = 0
    while index < len(lines):
        match = HEADER.match(lines[index])
        if not match:
            index += 1
            continue
        block = [lines[index]]
        index += 1
        while index < len(lines) and not HEADER.match(lines[index]) and len(block) < 8:
            block.append(lines[index])
            index += 1
        side_raw = match.group(3)
        if side_raw == "E":
            continue
        window = "\n".join(block)
        codes = CODE.findall(window)
        asset_type = next((code for code in codes if code in {"ST", "OP"}), codes[0] if codes else "")
        if asset_type != "ST":
            continue
        tickers = TICKER.findall(window)
        if not tickers:
            continue
        amounts = []
        for raw in re.findall(r"\$([\d,]+)", window):
            number = int(raw.replace(",", ""))
            if number in BANDS or number > 50_000_000:
                amounts.append(number)
        if len(amounts) < 2 or amounts[1] <= amounts[0]:
            continue
        rows.append(
            {
                "ticker": rh_symbol(tickers[0]),
                "side": "buy" if side_raw == "P" else "sell",
                "asset_type": "ST",
                "transacted": iso_mdy(match.group(4)),
                "amount_min": amounts[0],
                "amount_max": amounts[1],
            }
        )
    return rows


def _member_name(last, first):
    return f"{first} {last}".strip()


def house_index(year, state_dir, refresh=False):
    cache = state_dir / "house" / f"{year}FD.zip"
    cache.parent.mkdir(parents=True, exist_ok=True)
    if refresh or not cache.exists():
        try:
            cache.write_bytes(get(f"{HOUSE}/financial-pdfs/{year}FD.zip"))
        except Exception:
            if not cache.exists():
                raise
    with zipfile.ZipFile(cache) as archive:
        xml_name = next(name for name in archive.namelist() if name.endswith(".xml"))
        root = ET.fromstring(archive.read(xml_name))
    rows = []
    for member in root:
        fields = {child.tag: (child.text or "").strip() for child in member}
        if fields.get("FilingType") != "P" or not fields.get("DocID"):
            continue
        rows.append(
            {
                "last": fields.get("Last", ""),
                "first": fields.get("First", ""),
                "state": fields.get("StateDst", ""),
                "doc_id": fields["DocID"],
                "year": int(fields.get("Year") or year),
                "filed": iso_mdy(fields["FilingDate"]) if fields.get("FilingDate") else "",
            }
        )
    return rows


def _pdf_text(path):
    if not shutil.which("pdftotext"):
        raise RuntimeError("pdftotext is not installed")
    try:
        return subprocess.check_output(
            ["pdftotext", "-layout", str(path), "-"], text=True, errors="replace", timeout=30
        )
    except subprocess.CalledProcessError:
        return ""


def _download_pdf(year, doc_id, dest):
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        dest.write_bytes(get(f"{HOUSE}/ptr-pdfs/{year}/{doc_id}.pdf", timeout=40))
    except Exception:
        if dest.exists():
            dest.unlink()
        return None
    return dest


def _attach_member(trade, row):
    trade.update(
        {
            "member": _member_name(row["last"], row["first"]),
            "key": f"{row['last']}|{row['first']}|{row['state']}",
            "state": row["state"],
            "doc_id": row["doc_id"],
            "year": row["year"],
            "filed": row["filed"],
            "source_url": f"{HOUSE}/ptr-pdfs/{row['year']}/{row['doc_id']}.pdf",
        }
    )
    return trade


def refresh_house(state_dir, years=(2026, 2025)):
    """Re-read the clerk's daily index and parse only filings we do not have yet."""
    previous = load_house(state_dir)
    filings = []
    for year in years:
        try:
            filings.extend(house_index(year, state_dir, refresh=True))
        except Exception as error:
            print(f"house {year} index skipped: {error}")
    pdf_dir = state_dir / "house" / "pdfs"
    new_rows = [
        row for row in filings
        if not (pdf_dir / str(row["year"]) / f"{row['doc_id']}.pdf").exists()
    ]
    jobs = []
    if new_rows:
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {
                pool.submit(
                    _download_pdf, row["year"], row["doc_id"], pdf_dir / str(row["year"]) / f"{row['doc_id']}.pdf"
                ): row
                for row in new_rows
            }
            for future in as_completed(futures):
                path = future.result()
                if path:
                    jobs.append((futures[future], path))
    added = []
    skipped = previous.get("skipped_pdfs", 0)
    for row, path in jobs:
        parsed = parse_ptr(_pdf_text(path))
        if not parsed and path.stat().st_size > 0:
            skipped += 1
        added.extend(_attach_member(trade, row) for trade in parsed)
    trades = list(previous.get("trades", [])) + added
    payload = {
        "refreshed": datetime.now(timezone.utc).isoformat(),
        "filings": len(filings),
        "parsed": len(trades),
        "new_filings": len(new_rows),
        "skipped_pdfs": skipped,
        "trades": trades,
    }
    out = state_dir / "house" / "trades.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload))
    print(f"house index {len(filings)} new pdfs {len(new_rows)} stock trades {len(trades)}")
    return payload


def load_house(state_dir):
    path = state_dir / "house" / "trades.json"
    if not path.exists():
        return {"trades": [], "refreshed": None}
    return json.loads(path.read_text())


def norm_name(value):
    words = re.sub(r"[^A-Z0-9 ]", " ", value.upper().replace("&", " AND ")).split()
    return " ".join(word for word in words if word not in STOP and not word.isdigit())


def ticker_index(state_dir):
    path = state_dir / "company_tickers.json"
    if not path.exists():
        path.write_bytes(get("https://www.sec.gov/files/company_tickers.json"))
    raw = json.loads(path.read_text())
    index = {}
    for row in raw.values():
        index.setdefault(norm_name(row["title"]), set()).add(row["ticker"].upper())
    return index


# Normalized 13F names whose abbreviation is not a safe prefix of the SEC title.
ALIASES = {
    "OCCIDENTAL PETE": "OXY",
    "ALLY FINL": "ALLY",
    "APPLIED MATLS": "AMAT",
    "CAPITAL ONE FINL": "COF",
    "SIRIUSXM": "SIRI",
    "LOUISIANA PAC": "LPX",
    "D R HORTON": "DHI",
    "UNION PAC": "UNP",
    "NORFOLK SOUTHN": "NSC",
    "ROBINHOOD MKTS": "HOOD",
    "HERTZ GLOBAL HLDGS": "HTZ",
    "GOODYEAR TIRE RUBR": "GT",
    "WESCO INTL": "WCC",
    "EAGLE MATLS": "EXP",
}


def pick_ticker(candidates, title):
    candidates = sorted(set(candidates))
    if len(candidates) == 1:
        return rh_symbol(candidates[0])
    title = title.upper()
    wanted = None
    if "CL A" in title or "CLASS A" in title:
        wanted = ("-A", "GOOGL", "BRK-A")
    elif "CL B" in title or "CLASS B" in title:
        wanted = ("-B", "GOOG", "BRK-B")
    elif "CL C" in title or "CLASS C" in title:
        wanted = ("-C", "GOOG")
    if wanted:
        hits = [item for item in candidates if item.endswith(wanted[0]) or item in wanted]
        if len(hits) == 1:
            return rh_symbol(hits[0])
    plain = [item for item in candidates if "-" not in item and "." not in item]
    bases = [
        item for item in plain
        if any(other.startswith(item + "-") for other in candidates)
    ]
    if len(bases) == 1:
        return rh_symbol(bases[0])
    if len(plain) == 1:
        return rh_symbol(plain[0])
    return None


def _token_ok(left, right):
    if left == right:
        return True
    short, long = (left, right) if len(left) <= len(right) else (right, left)
    if len(short) < 4 or not long.startswith(short):
        return False
    return True


def map_issuer(name, title, index):
    key = norm_name(name)
    if key in ALIASES:
        return ALIASES[key]
    if key in index:
        return pick_ticker(index[key], title)
    query = key.split()
    hits = []
    for label, tickers in index.items():
        words = label.split()
        if len(query) == len(words) and all(_token_ok(a, b) for a, b in zip(query, words)):
            hits.append(tickers)
    if len(hits) == 1:
        return pick_ticker(hits[0], title)
    return None


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def load_13f(cik, state_dir, index=None):
    cik = str(int(cik)).zfill(10)
    cache = state_dir / "thirteenf" / f"{cik}.json"
    if cache.exists():
        age = datetime.now(timezone.utc).timestamp() - cache.stat().st_mtime
        if age < 12 * 3600:
            return json.loads(cache.read_text())
    submissions = json.loads(get(f"https://data.sec.gov/submissions/CIK{cik}.json"))
    recent = submissions["filings"]["recent"]
    found = None
    for offset, form in enumerate(recent["form"]):
        if form == "13F-HR":
            found = offset
            break
    if found is None:
        raise RuntimeError(f"no 13F-HR for {cik}")
    accession = recent["accessionNumber"][found]
    report_date = recent["reportDate"][found]
    filing_date = recent["filingDate"][found]
    folder = accession.replace("-", "")
    listing = json.loads(get(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{folder}/index.json"))
    table_name = next(
        item["name"]
        for item in listing["directory"]["item"]
        if item["name"].lower().endswith(".xml") and item["name"] != "primary_doc.xml"
    )
    root = ET.fromstring(get(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{folder}/{table_name}"))
    rows = []
    for node in root.iter():
        if _local(node.tag) != "infoTable":
            continue
        fields = {_local(child.tag): child for child in node}
        title = (fields["titleOfClass"].text or "").upper()
        if any(word in title for word in ("PUT", "CALL", "NOTE", "DEBT", "BOND", "WARRANT", "PFD", "RIGHT")):
            continue
        if not title.startswith("COM") and "ETF" not in title and "ADR" not in title:
            continue
        shares_node = fields.get("shrsOrPrnAmt")
        share_fields = {_local(child.tag): (child.text or "") for child in shares_node} if shares_node is not None else {}
        if share_fields.get("sshPrnamtType", "SH") not in {"SH", ""}:
            continue
        rows.append(
            {
                "name": fields["nameOfIssuer"].text or "",
                "title": title,
                "cusip": (fields["cusip"].text or "").strip(),
                "value": int(float(fields["value"].text)),
                "shares": int(float(share_fields.get("sshPrnamt") or 0)),
            }
        )
    implied = sorted(row["value"] / row["shares"] for row in rows if row["shares"] > 0 and row["value"] > 0)
    # A median under $2 means the form still uses the old thousands column.
    scale = 1000 if implied and implied[len(implied) // 2] < 2 else 1
    index = index if index is not None else ticker_index(state_dir)
    merged = {}
    skipped = {}
    for row in rows:
        value = row["value"] * scale
        ticker = map_issuer(row["name"], row["title"], index)
        if not ticker:
            skipped[row["name"]] = skipped.get(row["name"], 0) + value
            continue
        slot = merged.setdefault(ticker, {"ticker": ticker, "value": 0, "name": row["name"]})
        slot["value"] += value
    weights, meta = weights_from_values([(item["ticker"], item["value"]) for item in merged.values()])
    gross = sum(item["value"] for item in merged.values()) + sum(skipped.values())
    kept_value = sum(item["value"] for item in merged.values() if item["ticker"] in weights)
    meta["coverage"] = kept_value / gross if gross else 0.0
    payload = {
        "cik": cik,
        "filer": submissions.get("name"),
        "filed": filing_date,
        "as_of": report_date,
        "source_url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{folder}/{accession}-index.html",
        "scale": scale,
        "holdings": [
            {"ticker": ticker, "weight": weight, "value": merged[ticker]["value"], "name": merged[ticker]["name"]}
            for ticker, weight in sorted(weights.items(), key=lambda item: item[1], reverse=True)
        ],
        "unmapped": [name for name, _value in sorted(skipped.items(), key=lambda item: item[1], reverse=True)[:8]],
        "meta": meta,
    }
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(payload))
    return payload


def politician_rows(trades, today):
    grouped = {}
    for trade in trades:
        grouped.setdefault(trade["key"], []).append(trade)
    rows = []
    for key, items in grouped.items():
        nets = net_notionals(items, today)
        weights = positive_weights(nets)
        sample = items[0]
        rows.append(
            {
                "id": "house:" + key,
                "name": sample["member"],
                "state": sample["state"],
                "kind": "congress",
                "trades": len(items),
                "names": len(weights),
                "gross": sum(value for value in nets.values() if value > 0),
                "filed": max(trade["filed"] for trade in items),
            }
        )
    rows = [row for row in rows if row["names"]]
    rows.sort(key=lambda row: (row["filed"], row["gross"]), reverse=True)
    return rows


def _thirteenf_note(filing, today):
    meta = filing["meta"]
    note = (
        f"Latest 13F common stock, top {meta['names_kept']} of {meta['names']} mapped names "
        f"({meta['coverage']:.0%} of the filed equity value)."
    )
    as_of = datetime.strptime(filing["as_of"], "%Y-%m-%d").date()
    current = datetime.strptime(today, "%Y-%m-%d").date() if isinstance(today, str) else today
    note += " Rebalance to this filing. The quarter-end itself is the part that cannot be shortened."
    if (current - as_of).days > 150:
        note += " This is the newest filing on EDGAR, and it is older than a normal quarter."
    return note


def book_for(pilot_id, dollars, state_dir, today=None):
    today = today or datetime.now().date().isoformat()
    if pilot_id.startswith("house:"):
        key = pilot_id.removeprefix("house:")
        trades = [trade for trade in load_house(state_dir).get("trades", []) if trade["key"] == key]
        if not trades:
            raise KeyError(pilot_id)
        weights = positive_weights(net_notionals(trades, today))
        orders, leftover, copied = copy_fresh(trades, dollars, today)
        lag = copied["lag_days"]
        when = "the last 45 days" if copied["mode"] == "fresh" else "the newest filing on file"
        note = (
            f"Copied from {when}, sized off the disclosed book. "
            f"Shortest gap from trade to filing in this batch: {lag} days. "
            "Sales are shown and not staged."
        )
        return {
            "id": pilot_id,
            "name": trades[0]["member"],
            "who": trades[0]["state"],
            "kind": "congress",
            "as_of": copied["filed"],
            "source_url": next((trade["source_url"] for trade in trades if trade["filed"] == copied["filed"]), trades[0]["source_url"]),
            "note": note,
            "lag_days": lag,
            "holdings": [
                {"ticker": ticker, "weight": weight, "dollars": round(weight * float(dollars), 2)}
                for ticker, weight in sorted(weights.items(), key=lambda item: item[1], reverse=True)
            ],
            "activity": copied["trades"][:12],
            "orders": orders,
            "leftover": leftover,
        }
    slug = pilot_id.removeprefix("inv:")
    match = next(row for row in INVESTORS if row[3] == slug or row[0] == slug)
    filing = load_13f(match[0], state_dir)
    weights = {row["ticker"]: row["weight"] for row in filing["holdings"]}
    orders, leftover = propose(weights, dollars)
    return {
        "id": "inv:" + match[3],
        "name": match[1],
        "who": match[2],
        "kind": "13f",
        "as_of": filing["as_of"],
        "filed": filing["filed"],
        "source_url": filing["source_url"],
        "note": _thirteenf_note(filing, today),
        "holdings": [
            {**row, "dollars": round(row["weight"] * float(dollars), 2)} for row in filing["holdings"]
        ],
        "activity": [],
        "orders": orders,
        "leftover": leftover,
        "unmapped": filing["unmapped"],
    }


def _demo():
    text = """
     SP    Apple Inc. - Common Stock (AAPL)         S (partial)       12/24/2025 12/24/2025           $5,000,001 -
           [ST]                                                                                       $25,000,000
           D           : Sold 45,000 shares.
     SP    Apple Inc. - Common Stock (AAPL)         P                 12/30/2025 12/30/2025           $250,001 -
           [OP]                                                                                       $500,000
           D           : Purchased 20 call options.
     SP    Tempus AI, Inc. - Class A Common         P                 01/16/2026 01/16/2026           $50,001 -
                       Stock (TEM) [ST]                                                                                $100,000
     SP    Vistra Corp. Common Stock (VST)             P                 01/16/2026 01/16/2026             $100,001 -
                      [ST]                                                                                            $250,000
     SP    Walt Disney Company (DIS) [ST]              S                 12/30/2025 12/30/2025             $1,000,001 -
                                                                                                                       $5,000,000
     SP    Versant Media Group, Inc. - Class A         E                 01/02/2026 01/02/2026             $15.00
                      Common Stock (VSNT) [ST]
"""
    rows = parse_ptr(text)
    got = {(row["ticker"], row["side"], row["amount_min"], row["amount_max"]) for row in rows}
    assert got == {
        ("AAPL", "sell", 5000001, 25000000),
        ("TEM", "buy", 50001, 100000),
        ("VST", "buy", 100001, 250000),
        ("DIS", "sell", 1000001, 5000000),
    }
    assert rh_symbol("BRK-B") == "BRK.B"
    sample = {
        "BANK OF AMERICA": {"BAC"},
        "OCCIDENTAL PETROLEUM": {"OXY"},
        "ALLY FINANCIAL": {"ALLY"},
        "APPLIED MATERIALS": {"AMAT"},
    }
    assert map_issuer("BANK OF AMER CORP", "COM", sample) == "BAC"
    assert map_issuer("OCCIDENTAL PETE CORP", "COM", sample) == "OXY"
    assert map_issuer("ALLY FINL INC", "COM", sample) == "ALLY"
    assert map_issuer("SIRIUSXM HOLDINGS INC", "COM", {"SIRIUSPOINT": {"SPNT"}, "SIRIUS XM": {"SIRI"}}) == "SIRI"
    assert map_issuer("VERISIGN INC", "COM", {"VERISIGN": {"VRSN"}, "VERU": {"VERU"}}) == "VRSN"
    assert pick_ticker({"BAC", "BAC-PB", "BACRP"}, "COM") == "BAC"
    assert map_issuer("TOTALLY DIFFERENT NAME", "COM", sample) is None
    print("filings ok")


if __name__ == "__main__":
    _demo()
