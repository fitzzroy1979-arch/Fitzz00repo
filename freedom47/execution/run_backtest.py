#!/usr/bin/env python3
"""Run the SMA-crossover backtest over bars and write metrics as JSON.

One job: bars in, metrics out. No rendering (see render_backtest_report.py),
no LLM call, no state written.

Takes prices either from files produced by fetch_prices.py, or fetches them
itself for a symbol / the watchlist:

    python execution/fetch_prices.py --symbol XRP-USD --interval 1d --out .tmp/xrp.json
    python execution/run_backtest.py --prices .tmp/xrp.json

    python execution/run_backtest.py --symbol XRP-USD --interval 1d --period 1y
    python execution/run_backtest.py --watchlist --interval 1d --stop-loss 5 --trend-filter 200

`--watchlist` reads TradingView's own watchlist panel (what the monolith does);
`--env-watchlist` reads WATCHLIST from .env instead. The two are not the same
list -- see the note at the top of execution/README.md.

Output: a JSON list, one metrics object per symbol, each carrying `symbol`,
`return_pct`, `buy_hold_pct`, `trades`, `win_rate_pct`, `max_drawdown_pct`,
`final_equity`, `strategy`, `from`, `to`, `bars` -- or `error`.
"""

import argparse
import datetime as dt
import json
import sys

import _common as C
from _common import fmt_time, sma  # noqa: F401  (used by the copied backtest below)


# --------------------------------------------------------------------------- #
# Strategy + backtest -- moved verbatim from fitzz/trading.py (L416-533)
# --------------------------------------------------------------------------- #

def backtest_sma_cross(bars, starting_capital, fast=20, slow=50,
                       stop_loss_pct=0.0, take_profit_pct=0.0, trend_filter=0):
    """
    Long-only SMA crossover with optional risk controls.

      * Base rule: enter fully when the fast SMA crosses above the slow SMA,
        exit to cash when it crosses below.
      * trend_filter (bars): only enter when price is above SMA(trend_filter).
      * stop_loss_pct / take_profit_pct: exit early if price falls/rises this %
        from the entry. 0 disables each control.

    Returns a metrics dict (or {"error": ...} if there aren't enough bars).
    """
    closes = [float(b["close"]) for b in bars]
    n = len(closes)
    warmup = max(slow, trend_filter)
    if n < warmup + 2:
        return {"error": f"not enough bars ({n}) for windows (slow {slow}, trend {trend_filter})"}

    fast_ma = sma(closes, fast)
    slow_ma = sma(closes, slow)
    trend_ma = sma(closes, trend_filter) if trend_filter else [None] * n

    cash = float(starting_capital)
    units = 0.0
    in_pos = False
    entry_price = 0.0
    trades = []          # (entry_price, exit_price, return_pct)
    equity_curve = []

    for i in range(n):
        price = closes[i]
        f, s = fast_ma[i], slow_ma[i]
        pf, ps = fast_ma[i - 1], slow_ma[i - 1]
        crossed = f is not None and s is not None and pf is not None and ps is not None

        # Exits (checked before entries): stop-loss / take-profit / cross-down.
        if in_pos:
            exit_now = (
                (stop_loss_pct and price <= entry_price * (1 - stop_loss_pct / 100)) or
                (take_profit_pct and price >= entry_price * (1 + take_profit_pct / 100)) or
                (crossed and pf >= ps and f < s)
            )
            if exit_now:
                cash = units * price
                trades.append((entry_price, price, (price / entry_price - 1) * 100))
                units = 0.0
                in_pos = False

        # Entry: fresh cross-up, optionally gated by the trend filter.
        if not in_pos and crossed and pf <= ps and f > s:
            trend_ok = (not trend_filter) or (trend_ma[i] is not None and price > trend_ma[i])
            if trend_ok:
                units = cash / price
                cash = 0.0
                in_pos = True
                entry_price = price

        equity = cash + units * price
        equity_curve.append(equity)

    # Close any open position at the last bar for reporting.
    final_price = closes[-1]
    final_equity = cash + units * final_price
    if in_pos:
        trades.append((entry_price, final_price, (final_price / entry_price - 1) * 100))

    peak = equity_curve[0]
    max_dd = 0.0
    for e in equity_curve:
        peak = max(peak, e)
        if peak > 0:
            max_dd = min(max_dd, (e / peak - 1) * 100)

    wins = [t for t in trades if t[2] > 0]
    buy_hold = (final_price / closes[0] - 1) * 100

    return {
        "bars": n,
        "from": fmt_time(bars[0].get("time")),
        "to": fmt_time(bars[-1].get("time")),
        "starting_capital": round(float(starting_capital), 2),
        "final_equity": round(final_equity, 2),
        "return_pct": round((final_equity / starting_capital - 1) * 100, 2),
        "buy_hold_pct": round(buy_hold, 2),
        "trades": len(trades),
        "win_rate_pct": round(100 * len(wins) / len(trades), 1) if trades else 0.0,
        "max_drawdown_pct": round(max_dd, 2),
        "strategy": _strategy_label(fast, slow, stop_loss_pct, take_profit_pct, trend_filter),
    }


def _strategy_label(fast, slow, stop_loss_pct=0.0, take_profit_pct=0.0, trend_filter=0):
    label = f"sma_cross({fast}/{slow})"
    extras = []
    if trend_filter:
        extras.append(f"trend{trend_filter}")
    if stop_loss_pct:
        extras.append(f"sl{stop_loss_pct:g}%")
    if take_profit_pct:
        extras.append(f"tp{take_profit_pct:g}%")
    return label + ("+" + "+".join(extras) if extras else "")


def _is_proven(m, min_trades):
    """A symbol 'proves out' if its backtest made money over enough trades."""
    return ("error" not in m
            and m.get("return_pct", 0) > 0
            and m.get("trades", 0) >= min_trades)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def build_parser():
    p = argparse.ArgumentParser(
        description="Backtest the SMA crossover over bars; write metrics as JSON.")

    src = p.add_argument_group("price source (pick one)")
    src.add_argument("--prices", action="append", metavar="FILE",
                     help="Price JSON from fetch_prices.py. Repeatable.")
    src.add_argument("--symbol", help="Fetch this symbol, then backtest it.")
    src.add_argument("--watchlist", action="store_true",
                     help="Fetch every symbol in TradingView's watchlist panel.")
    src.add_argument("--env-watchlist", action="store_true",
                     help="Use WATCHLIST from .env instead of TradingView's panel.")

    win = p.add_argument_group("fetch window (ignored with --prices)")
    win.add_argument("--interval", default="1d", help="Bar interval (default 1d).")
    win.add_argument("--period", default="1y", help="Lookback, e.g. 1y, 6mo, 90d (default 1y).")

    st = p.add_argument_group("strategy")
    st.add_argument("--starting-capital", type=float, default=None,
                    help="Starting capital (default: DEFAULT_STARTING_CASH from .env).")
    st.add_argument("--fast", type=int, default=20, help="Fast SMA window (default 20).")
    st.add_argument("--slow", type=int, default=50, help="Slow SMA window (default 50).")
    st.add_argument("--stop-loss", type=float, default=0.0,
                    help="Stop-loss %% below entry (default 0 = off).")
    st.add_argument("--take-profit", type=float, default=0.0,
                    help="Take-profit %% above entry (default 0 = off).")
    st.add_argument("--trend-filter", type=int, default=0,
                    help="Only go long when price > SMA(N) (default 0 = off).")
    st.add_argument("--proven-only", action="store_true",
                    help="Keep only symbols with return > 0 and enough trades.")
    st.add_argument("--proven-min-trades", type=int, default=3,
                    help="Minimum trades to count as proven (default 3).")

    out = p.add_argument_group("output")
    out.add_argument("--out", help="Write JSON here. Default: .tmp/backtest_<interval>.json")
    out.add_argument("--stdout", action="store_true", help="Also print the JSON to stdout.")
    out.add_argument("--tv-repo", help="Path to the tradingview-mcp checkout.")
    out.add_argument("--settle", type=float, default=1.5, help="Chart settle seconds.")
    out.add_argument("-v", "--verbose", action="store_true", help="Echo bridge commands.")
    return p


def load_price_files(paths):
    """Read fetch_prices.py output files -> [(symbol, bars, meta), ...]."""
    series = []
    for path in paths:
        try:
            payload = C.read_json(path)
        except (OSError, json.JSONDecodeError) as e:
            print(f"! {path}: {e}", file=sys.stderr)
            continue
        bars = payload.get("bars")
        if not bars:
            print(f"! {path}: no bars in file", file=sys.stderr)
            continue
        series.append((payload.get("symbol", str(path)), bars, payload))
    return series


def fetch_series(args):
    """Fetch bars for --symbol / --watchlist / --env-watchlist."""
    resolution = C.resolve_interval(args.interval)
    capped, wanted = C.period_to_bars(args.period, resolution)
    if wanted > C.MAX_BARS:
        print(f"! {args.period}/{args.interval} ~ {wanted} bars; the bridge caps at "
              f"{C.MAX_BARS}. Using the most recent {capped}.", file=sys.stderr)

    bridge = C.get_bridge(tv_repo=args.tv_repo, settle=args.settle,
                          verbose=args.verbose)
    BridgeError = C.bridge_error()

    if args.env_watchlist:
        symbols = [C.normalize_symbol(s) for s in C.watchlist()]
    elif args.watchlist:
        try:
            symbols = bridge.get_watchlist()
        except BridgeError as e:
            print(f"! {e}", file=sys.stderr)
            return None
    else:
        symbols = [C.normalize_symbol(args.symbol)]

    series = []
    for sym in symbols:
        try:
            bars = bridge.load_bars(sym, resolution, capped)
            series.append((sym, bars, None))
        except BridgeError as e:
            series.append((sym, None, {"error": str(e)}))
    return series


def main(argv=None):
    args = build_parser().parse_args(argv)

    if not (args.prices or args.symbol or args.watchlist or args.env_watchlist):
        print("! need --prices FILE, --symbol SYMBOL, --watchlist or --env-watchlist",
              file=sys.stderr)
        return 2

    if args.prices:
        series = load_price_files(args.prices)
    else:
        try:
            series = fetch_series(args)
        except ValueError as e:
            print(f"! {e}", file=sys.stderr)
            return 2
    if series is None:
        return 1
    if not series:
        print("! no price series to backtest", file=sys.stderr)
        return 1

    capital = (args.starting_capital if args.starting_capital is not None
               else C.env_float("DEFAULT_STARTING_CASH", C.DEFAULT_STARTING_CASH))

    results = []
    for symbol, bars, meta in series:
        if bars is None:
            metrics = {"error": (meta or {}).get("error", "no bars")}
        else:
            metrics = backtest_sma_cross(
                bars, capital, fast=args.fast, slow=args.slow,
                stop_loss_pct=args.stop_loss, take_profit_pct=args.take_profit,
                trend_filter=args.trend_filter,
            )
        metrics["symbol"] = symbol
        if meta and meta.get("interval"):
            metrics["interval"] = meta["interval"]
        results.append(metrics)

    display = results
    if args.proven_only:
        display = [r for r in results if _is_proven(r, args.proven_min_trades)]
        print(f"proven-only: {len(display)}/{len(results)} symbol(s) passed "
              f"(return>0, trades>={args.proven_min_trades}).", file=sys.stderr)

    payload = {
        "ran_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "starting_capital": round(capital, 2),
        "strategy": _strategy_label(args.fast, args.slow, args.stop_loss,
                                    args.take_profit, args.trend_filter),
        "results": display,
    }
    # Name the default output after the interval the bars actually carry, not
    # --interval, which is meaningless when the prices came from a file.
    intervals = {r["interval"] for r in display if r.get("interval")}
    tag = intervals.pop() if len(intervals) == 1 else args.interval
    out = args.out or f".tmp/backtest_{tag}.json"
    path = C.write_json(out, payload)
    errors = sum(1 for r in display if "error" in r)
    print(f"{len(display)} result(s) ({errors} error) -> {path}", file=sys.stderr)

    if args.stdout:
        print(json.dumps(payload, indent=2))
    return 1 if errors and errors == len(display) else 0


if __name__ == "__main__":
    raise SystemExit(main())
