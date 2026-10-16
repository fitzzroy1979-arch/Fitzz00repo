#!/usr/bin/env python3
"""Snapshot BTCC perpetual-futures marks, fees and funding. Public, no account.

Reads `https://www.btcc.com/api/futures` — the endpoint BTCC's own trading page
calls. It needs no API key, no cookie and no login; one unauthenticated GET
returns every listed instrument.

    python execution/fetch_btcc_prices.py --symbols XRP,BTC,ETH
    python execution/fetch_btcc_prices.py --env-watchlist --out .tmp/btcc.json
    python execution/fetch_btcc_prices.py --all --out .tmp/btcc_all.json
    python execution/fetch_btcc_prices.py --symbol XRPUSDT --stdout

**This is a snapshot, not history.** It returns the current mark, bid/ask,
index, fee rates and funding for each instrument — there are no OHLCV bars, so
it cannot feed run_backtest.py or run_simulation.py. Use fetch_prices.py
(TradingView) for bars. What this is good for: a live mark when TradingView is
not running, and BTCC's own fee and funding numbers for paper-trading realism.

**Fee and funding units are unconfirmed.** BTCC returns `taker_fee: 0.01` and
`funding_rate: 0.0144` as bare numbers with no unit. 0.01 could mean 0.01% or
1% — two orders of magnitude apart in PnL. Values are passed through exactly as
received and flagged `"units": "unconfirmed"`; do not multiply them into a PnL
until the meaning is confirmed against BTCC's published fee schedule.

Read-only. Places no orders, holds no credentials, contacts nothing but that
one public URL.
"""

import argparse
import datetime as dt
import json
import sys
import urllib.error
import urllib.request

import _common as C

BTCC_FUTURES_URL = "https://www.btcc.com/api/futures"

# The endpoint 403s a bare urllib request; it wants a browser-ish agent.
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0 Safari/537.36")

# Fields carried through per instrument, in report order.
FIELDS = ("name", "baseCurrency", "quoteCurrency", "type", "perpetual", "enabled",
          "last", "bid", "ask", "index", "lowerBound", "upperBound",
          "maker_fee", "taker_fee", "funding_rate", "next_funding_rate",
          "next_funding_rate_timestamp", "openInterest", "openInterestUsd",
          "volumeUsd24h")


class BtccError(RuntimeError):
    """Raised when the public endpoint can't be reached or returns junk."""


def fetch_all(timeout=30):
    """One unauthenticated GET. Returns the instrument list."""
    req = urllib.request.Request(BTCC_FUTURES_URL,
                                 headers={"User-Agent": USER_AGENT,
                                          "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise BtccError(f"BTCC returned HTTP {e.code} for {BTCC_FUTURES_URL}")
    except urllib.error.URLError as e:
        raise BtccError(f"BTCC unreachable: {e.reason}")
    except json.JSONDecodeError:
        raise BtccError("BTCC returned a non-JSON body.")

    if not payload.get("success"):
        raise BtccError(f"BTCC reported failure: {json.dumps(payload)[:200]}")
    result = payload.get("result")
    if not isinstance(result, list):
        raise BtccError("BTCC response had no 'result' list — the shape changed.")
    return result, payload


def btcc_symbol(symbol, index):
    """Resolve a loose symbol to a BTCC instrument name.

    Accepts what the rest of this workspace uses -- 'XRP-USD' (Yahoo form, from
    .env), 'XRPUSD' (TradingView form) or a bare 'XRP' -- and finds the matching
    perpetual, which BTCC names 'XRPUSDT'. Returns None when nothing matches.
    """
    raw = str(symbol).strip().upper()
    names = {i["name"].upper(): i["name"] for i in index}

    base = raw.split(":")[-1].replace("-", "")
    candidates = [raw, base]
    for stem in (base, base[:-3] if base.endswith("USD") else base):
        candidates += [f"{stem}USDT", f"{stem}T"]
    for c in candidates:
        if c in names:
            return names[c]
    return None


def select(instruments, args):
    """Which instruments to report, and which requested symbols missed."""
    if args.all:
        return instruments, []

    if args.env_watchlist:
        wanted = C.watchlist()
    elif args.symbols:
        wanted = [s.strip() for s in args.symbols.split(",") if s.strip()]
    else:
        wanted = [args.symbol]

    by_name = {i["name"]: i for i in instruments}
    chosen, missing = [], []
    for w in wanted:
        name = btcc_symbol(w, instruments)
        if name:
            hit = dict(by_name[name])
            hit["requested_symbol"] = w
            chosen.append(hit)
        else:
            missing.append(w)
    return chosen, missing


def trim(instrument):
    row = {k: instrument.get(k) for k in FIELDS if k in instrument}
    if "requested_symbol" in instrument:
        row["requested_symbol"] = instrument["requested_symbol"]
    row["price_suspect"] = is_price_suspect(instrument)
    return row


def is_price_suspect(instrument):
    """True when the quoted price cannot be trusted despite the instrument trading.

    BTCC lists instruments that are `enabled` and carry real open interest and
    24h volume while reporting last/bid/ask/index as exactly 0 -- ZAMAUSDT does
    this, with 138M open interest and a lowerBound/upperBound band around
    0.0512 but a zero price. Consuming that silently means a division by zero or
    a phantom crash to nothing, so it is flagged rather than passed through as
    if it were a real quote.
    """
    if not instrument.get("enabled"):
        return False
    quoted = [instrument.get(k) or 0 for k in ("last", "bid", "ask", "index")]
    has_activity = (instrument.get("openInterest") or 0) > 0 or \
                   (instrument.get("volumeUsd24h") or 0) > 0
    return all(q <= 0 for q in quoted) and has_activity


def build_parser():
    p = argparse.ArgumentParser(
        description="Snapshot BTCC perpetual marks, fees and funding. "
                    "Public endpoint, no account, read-only.")
    sel = p.add_mutually_exclusive_group(required=True)
    sel.add_argument("--symbol", help="One symbol, e.g. XRPUSDT / XRP-USD / XRP.")
    sel.add_argument("--symbols", help="Comma-separated symbols.")
    sel.add_argument("--env-watchlist", action="store_true",
                     help="Use WATCHLIST from .env.")
    sel.add_argument("--all", action="store_true",
                     help="Every listed instrument (177 at last count).")
    p.add_argument("--out", help="Write JSON here. Default: .tmp/btcc_marks.json")
    p.add_argument("--stdout", action="store_true", help="Also print the JSON.")
    p.add_argument("--quiet", action="store_true", help="Suppress the table.")
    return p


def print_table(rows):
    print(f"{'symbol':<14}{'last':>12}{'bid':>12}{'ask':>12}"
          f"{'maker':>8}{'taker':>8}{'funding':>10}")
    for r in rows:
        flag = "  ! price_suspect" if r.get("price_suspect") else ""
        print(f"{r['name']:<14}{r.get('last', 0):>12.6g}{r.get('bid', 0):>12.6g}"
              f"{r.get('ask', 0):>12.6g}{r.get('maker_fee', 0):>8}"
              f"{r.get('taker_fee', 0):>8}{r.get('funding_rate', 0):>10}{flag}")
    print("\n  fee and funding units are UNCONFIRMED — passed through as received.")


def main(argv=None):
    args = build_parser().parse_args(argv)

    try:
        instruments, payload = fetch_all()
    except BtccError as e:
        print(f"! {e}", file=sys.stderr)
        return 1

    chosen, missing = select(instruments, args)
    for m in missing:
        print(f"! no BTCC instrument matches {m!r}", file=sys.stderr)
    if not chosen:
        print("! nothing to report.", file=sys.stderr)
        return 1

    rows = [trim(i) for i in chosen]
    suspect = [r["name"] for r in rows if r.get("price_suspect")]
    for name in suspect:
        print(f"! {name}: BTCC reports last/bid/ask/index as 0 while the "
              f"instrument is enabled and has open interest. Flagged "
              f"price_suspect; do not use this quote.", file=sys.stderr)
    out_payload = {
        "source": BTCC_FUTURES_URL,
        "authenticated": False,
        "fetched_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "instruments_listed": len(instruments),
        "instruments_returned": len(rows),
        "total_volume_usd_24h": payload.get("totalVolumeUsd24h"),
        "units": "unconfirmed",
        "units_note": ("maker_fee / taker_fee / funding_rate are passed through "
                       "exactly as BTCC returned them. BTCC does not label the "
                       "unit; 0.01 may mean 0.01% or 1%. Confirm against BTCC's "
                       "published fee schedule before using these in any PnL."),
        "snapshot_only": ("Point-in-time marks, not OHLCV bars. Cannot feed "
                          "run_backtest.py or run_simulation.py; use "
                          "fetch_prices.py for history."),
        "price_suspect_count": len(suspect),
        "instruments": rows,
    }

    path = C.write_json(args.out or ".tmp/btcc_marks.json", out_payload)
    print(f"{len(rows)} instrument(s) -> {path}", file=sys.stderr)

    if not args.quiet and not args.stdout:
        print_table(rows)
    if args.stdout:
        print(json.dumps(out_payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
