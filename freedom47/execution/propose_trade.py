#!/usr/bin/env python3
"""Price a paper trade and write the proposal. Writes no state, logs nothing.

One job: gate on the trade window, fetch a reference price, and emit the order
that *would* be logged. Deciding whether to log it is log_trade.py's job, and
that needs your explicit approval.

    python execution/propose_trade.py --symbol XRP-USD --action buy --amount 50
    python execution/propose_trade.py --symbol XRP-USD --action buy --amount 50 \\
        --trade-window-start 7 --trade-window-end 19

Exits 3 when the trade window is closed, so a caller can tell "gated" apart
from "broken". Nothing here places an order, touches the portfolio, or contacts
an exchange — this build is TradingView-data-only.
"""

import argparse
import datetime as dt
import json
import sys

import _common as C


# --------------------------------------------------------------------------- #
# Trade window gate -- moved verbatim from fitzz/trading.py (L551-562)
# --------------------------------------------------------------------------- #

def check_trade_window(start_h, end_h, ignore):
    now = dt.datetime.now()
    if ignore:
        return True, f"trade-window bypassed (--ignore-trade-window); now {now:%H:%M}"
    if start_h <= now.hour < end_h:
        return True, f"within trade window {start_h:02d}:00-{end_h:02d}:00 (now {now:%H:%M})"
    return False, (f"outside trade window {start_h:02d}:00-{end_h:02d}:00 "
                  f"(now {now:%H:%M}). Use --ignore-trade-window to override.")


# --------------------------------------------------------------------------- #
# Proposal
# --------------------------------------------------------------------------- #

def reference_price(bridge, symbol):
    """Reference price from the bridge. Same key precedence as the monolith."""
    quote = bridge.get_quote(symbol)
    if isinstance(quote, dict):
        return quote.get("price") or quote.get("last") or quote.get("close")
    return None


def build_order(symbol, action, amount, price):
    """The order dict cmd_trade builds, minus the write."""
    return {
        "ts": dt.datetime.now().isoformat(timespec="seconds"),
        "symbol": symbol,
        "action": action,
        "amount": amount,
        "ref_price": price,
        "est_units": round(amount / price, 8) if price else None,
        "mode": "SIMULATED",
        "note": "No real order placed — TradingView-data-only build.",
    }


def build_parser():
    p = argparse.ArgumentParser(
        description="Price a paper trade and write the proposal. Logs nothing.")
    p.add_argument("--symbol", required=True, help="Symbol to trade.")
    p.add_argument("--action", required=True, choices=["buy", "sell"], help="Order side.")
    p.add_argument("--amount", required=True, type=float,
                   help="Quote-currency amount.")
    p.add_argument("--trade-window-start", type=int, default=0,
                   help="Window start hour, local time (default 0 = 24/7).")
    p.add_argument("--trade-window-end", type=int, default=24,
                   help="Window end hour, local time (default 24 = 24/7).")
    p.add_argument("--ignore-trade-window", action="store_true",
                   help="Bypass the window gate for this one command.")
    p.add_argument("--out", help="Write the proposal here. "
                                 "Default: .tmp/proposed_trade.json")
    p.add_argument("--stdout", action="store_true", help="Also print the JSON.")
    p.add_argument("--tv-repo", help="Path to the tradingview-mcp checkout.")
    p.add_argument("--settle", type=float, default=1.5, help="Chart settle seconds.")
    p.add_argument("-v", "--verbose", action="store_true", help="Echo bridge commands.")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)

    if args.amount <= 0:
        print("! --amount must be positive.", file=sys.stderr)
        return 2

    ok, reason = check_trade_window(
        args.trade_window_start, args.trade_window_end, args.ignore_trade_window)
    print(f"[trade-window] {reason}", file=sys.stderr)
    if not ok:
        return 3

    symbol = C.normalize_symbol(args.symbol)
    bridge = C.get_bridge(tv_repo=args.tv_repo, settle=args.settle,
                          verbose=args.verbose)
    price = reference_price(bridge, symbol)
    if not price:
        print(f"! no reference price for {symbol} (is TradingView reachable?). "
              f"Not proposing a trade without one.", file=sys.stderr)
        return 1

    order = build_order(symbol, args.action, args.amount, price)
    order["requested_symbol"] = args.symbol
    order["window"] = reason

    path = C.write_json(args.out or ".tmp/proposed_trade.json", order)
    print(f"proposal -> {path}", file=sys.stderr)
    print(f"  {args.action.upper()} {args.amount:g} of {symbol} @ {price} "
          f"= {order['est_units']} units  (SIMULATED, nothing logged)",
          file=sys.stderr)
    print(f"  to record it: python execution/log_trade.py --proposal {path}",
          file=sys.stderr)

    if args.stdout:
        print(json.dumps(order, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
