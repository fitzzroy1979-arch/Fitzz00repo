#!/usr/bin/env python3
"""Fetch OHLCV bars for one symbol and write them as JSON.

One job: bars in, JSON out. No strategy math, no LLM call, no deliverable.

    python execution/fetch_prices.py --symbol XRP-USD --interval 4h --out .tmp/t.json
    python execution/fetch_prices.py --symbol BTCUSD --interval 1d --period 1y
    python execution/fetch_prices.py --symbol XRP-USD --interval 4h --days 90 --stdout

Prices come from TradingView Desktop through the `tv` bridge, so TradingView
must be running with its debug port open before this will return anything (see
tradingview-mcp/SETUP_GUIDE.md). Exits non-zero if the bridge can't be reached.

Output shape:
    {"symbol": "XRPUSD", "requested_symbol": "XRP-USD", "interval": "4h",
     "resolution": "240", "bars_requested": 540, "bars_returned": 540,
     "fetched_at": "2026-09-04T05:30:00Z",
     "bars": [{"time": ..., "open": ..., "high": ..., "low": ...,
               "close": ..., "volume": ...}, ...]}
"""

import argparse
import datetime as dt
import json
import sys

import _common as C


def build_parser():
    p = argparse.ArgumentParser(
        description="Fetch OHLCV bars for one symbol and write them as JSON.")
    p.add_argument("--symbol", required=True,
                   help="Symbol to fetch. Yahoo form ('XRP-USD') is normalised "
                        "to TradingView form ('XRPUSD').")
    p.add_argument("--interval", default="1d",
                   help=f"Bar interval. One of: "
                        f"{', '.join(sorted(C.INTERVAL_TO_TV))} (default: 1d)")

    window = p.add_mutually_exclusive_group()
    window.add_argument("--period", help="Look-back window, e.g. 1y, 6mo, 90d, 48h.")
    window.add_argument("--days", type=float, help="Look-back window in days.")
    window.add_argument("--bars", type=int, help="Exact number of bars to read.")

    p.add_argument("--out", help="Write JSON here (relative paths resolve inside "
                                 "freedom47/). Default: .tmp/prices_<symbol>_<interval>.json")
    p.add_argument("--stdout", action="store_true",
                   help="Also print the JSON to stdout.")
    p.add_argument("--tv-repo", help="Path to the tradingview-mcp checkout.")
    p.add_argument("--settle", type=float, default=1.5,
                   help="Seconds to let the chart load (default: 1.5).")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="Echo the bridge commands to stderr.")
    return p


def resolve_window(args, resolution):
    """Return (bars_to_read, bars_asked_for) from whichever window flag was given."""
    if args.bars:
        return min(args.bars, C.MAX_BARS), args.bars
    if args.period:
        return C.period_to_bars(args.period, resolution)
    if args.days:
        return C.days_to_bars(args.days, resolution)
    # Same default the monolith uses for a plain backtest: one year of bars.
    return C.period_to_bars("1y", resolution)


def main(argv=None):
    args = build_parser().parse_args(argv)

    try:
        resolution = C.resolve_interval(args.interval)
    except ValueError as e:
        print(f"! {e}", file=sys.stderr)
        return 2

    symbol = C.normalize_symbol(args.symbol)
    count, asked = resolve_window(args, resolution)
    if asked > count:
        print(f"! window truncated to the {C.MAX_BARS}-bar ceiling "
              f"({asked} bars requested).", file=sys.stderr)

    bridge = C.get_bridge(tv_repo=args.tv_repo, settle=args.settle,
                          verbose=args.verbose)
    BridgeError = C.bridge_error()

    try:
        bars = bridge.load_bars(symbol, resolution, count)
    except BridgeError as e:
        print(f"! {e}", file=sys.stderr)
        return 1

    payload = {
        "symbol": symbol,
        "requested_symbol": args.symbol,
        "interval": args.interval,
        "resolution": resolution,
        "bars_requested": count,
        "bars_returned": len(bars),
        "fetched_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "bars": bars,
    }

    out = args.out or f".tmp/prices_{symbol}_{args.interval}.json"
    path = C.write_json(out, payload)
    print(f"{len(bars)} bars -> {path}", file=sys.stderr)

    if args.stdout:
        print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
