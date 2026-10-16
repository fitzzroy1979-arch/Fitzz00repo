#!/usr/bin/env python3
"""Walk-forward paper simulation with portfolio risk management.

One job: bars in, simulation metrics + per-trade blotter out. Paper only —
nothing here places an order, writes portfolio state, or contacts an exchange.

Differs from run_backtest.py in what it models: a trailing stop, risk-based
position sizing off the tightest active stop, a max-drawdown circuit breaker
that liquidates and halts new entries, and a blotter recording why each trade
closed.

    python execution/fetch_prices.py --symbol XRP-USD --interval 1h --days 90 --out .tmp/xrp.json
    python execution/run_simulation.py --prices .tmp/xrp.json --trailing-stop-pct 8 --risk-pct 2

    python execution/run_simulation.py --symbol XRP-USD --interval 1h --days 90
    python execution/run_simulation.py --watchlist --interval 1h --max-drawdown-pct 20

Output: a JSON payload with `results[]`, each carrying the same metrics
run_backtest.py returns plus `halted` and `blotter[]`.
"""

import argparse
import datetime as dt
import json
import sys

import _common as C
from _common import fmt_time, sma  # noqa: F401  (used by the copied simulation below)


# --------------------------------------------------------------------------- #
# Simulation -- moved verbatim from fitzz/trading.py (L1160-1311)
# --------------------------------------------------------------------------- #

def _sim_label(fast, slow, stop_loss_pct, trailing_stop_pct, take_profit_pct,
               trend_filter, risk_pct, max_dd):
    label = f"sma_cross({fast}/{slow})"
    extras = []
    if trend_filter:
        extras.append(f"trend{trend_filter}")
    if stop_loss_pct:
        extras.append(f"sl{stop_loss_pct:g}%")
    if trailing_stop_pct:
        extras.append(f"trail{trailing_stop_pct:g}%")
    if take_profit_pct:
        extras.append(f"tp{take_profit_pct:g}%")
    if risk_pct:
        extras.append(f"risk{risk_pct:g}%")
    if max_dd:
        extras.append(f"maxDD{max_dd:g}%")
    return label + ("+" + "+".join(extras) if extras else "")


def simulate_strategy(bars, starting_capital, fast=20, slow=50, stop_loss_pct=0.0,
                      trailing_stop_pct=0.0, take_profit_pct=0.0, trend_filter=0,
                      risk_pct=0.0, max_drawdown_pct=0.0):
    """
    Walk-forward long-only SMA-crossover simulation with portfolio risk controls:
    hard stop, trailing stop, take-profit, risk-based position sizing, and a
    max-drawdown circuit breaker that liquidates and halts new entries.
    Returns a metrics dict with a per-trade blotter.
    """
    closes = [float(b["close"]) for b in bars]
    times = [b.get("time") for b in bars]
    n = len(closes)
    warmup = max(slow, trend_filter)
    if n < warmup + 2:
        return {"error": f"not enough bars ({n}) for windows (slow {slow}, trend {trend_filter})"}

    fast_ma = sma(closes, fast)
    slow_ma = sma(closes, slow)
    trend_ma = sma(closes, trend_filter) if trend_filter else [None] * n

    # For risk sizing, the tightest active stop defines per-trade risk.
    stops = [d for d in (stop_loss_pct, trailing_stop_pct) if d]
    stop_distance = min(stops) if stops else None

    cash = float(starting_capital)
    units = 0.0
    in_pos = False
    entry_price = entry_frac = peak_price = 0.0
    entry_i = 0
    peak_equity = float(starting_capital)
    halted = False
    trades = []
    equity_curve = []

    def close_position(i, price, reason):
        nonlocal cash, units, in_pos
        gross = units * price
        cost = units * entry_price
        trades.append({
            "entry_date": fmt_time(times[entry_i]),
            "exit_date": fmt_time(times[i]),
            "entry_price": round(entry_price, 6),
            "exit_price": round(price, 6),
            "size_pct": round(entry_frac * 100, 1),
            "pnl_pct": round((price / entry_price - 1) * 100, 2),
            "pnl_cash": round(gross - cost, 2),
            "reason": reason,
        })
        cash += gross
        units = 0.0
        in_pos = False

    for i in range(n):
        price = closes[i]
        f, s = fast_ma[i], slow_ma[i]
        pf, ps = fast_ma[i - 1], slow_ma[i - 1]
        crossed = f is not None and s is not None and pf is not None and ps is not None

        # Per-position exits (priority: hard stop, trailing, take-profit, signal).
        if in_pos:
            peak_price = max(peak_price, price)
            reason = None
            if stop_loss_pct and price <= entry_price * (1 - stop_loss_pct / 100):
                reason = "stop-loss"
            elif trailing_stop_pct and price <= peak_price * (1 - trailing_stop_pct / 100):
                reason = "trailing-stop"
            elif take_profit_pct and price >= entry_price * (1 + take_profit_pct / 100):
                reason = "take-profit"
            elif crossed and pf >= ps and f < s:
                reason = "cross-down"
            if reason:
                close_position(i, price, reason)

        equity = cash + units * price
        peak_equity = max(peak_equity, equity)

        # Portfolio circuit breaker: liquidate and stop trading.
        if (max_drawdown_pct and not halted
                and equity <= peak_equity * (1 - max_drawdown_pct / 100)):
            halted = True
            if in_pos:
                close_position(i, price, "max-drawdown")

        # Entry: fresh cross-up, optional trend gate, risk-based sizing.
        if not halted and not in_pos and crossed and pf <= ps and f > s:
            trend_ok = (not trend_filter) or (trend_ma[i] is not None and price > trend_ma[i])
            if trend_ok:
                if risk_pct and stop_distance:
                    frac = min(1.0, (risk_pct / 100) / (stop_distance / 100))
                else:
                    frac = 1.0
                invest = cash * frac
                units = invest / price
                cash -= invest
                in_pos = True
                entry_price = price
                entry_frac = frac
                entry_i = i
                peak_price = price

        equity_curve.append(cash + units * price)

    final_price = closes[-1]
    if in_pos:
        close_position(n - 1, final_price, "end")
    final_equity = cash

    peak = equity_curve[0]
    max_dd = 0.0
    for e in equity_curve:
        peak = max(peak, e)
        if peak > 0:
            max_dd = min(max_dd, (e / peak - 1) * 100)

    wins = [t for t in trades if t["pnl_pct"] > 0]
    return {
        "bars": n,
        "from": fmt_time(times[0]),
        "to": fmt_time(times[-1]),
        "starting_capital": round(float(starting_capital), 2),
        "final_equity": round(final_equity, 2),
        "return_pct": round((final_equity / starting_capital - 1) * 100, 2),
        "buy_hold_pct": round((final_price / closes[0] - 1) * 100, 2),
        "trades": len(trades),
        "win_rate_pct": round(100 * len(wins) / len(trades), 1) if trades else 0.0,
        "max_drawdown_pct": round(max_dd, 2),
        "halted": halted,
        "strategy": _sim_label(fast, slow, stop_loss_pct, trailing_stop_pct,
                               take_profit_pct, trend_filter, risk_pct, max_drawdown_pct),
        "blotter": trades,
    }


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def build_parser():
    p = argparse.ArgumentParser(
        description="Walk-forward paper simulation; write metrics + blotter as JSON.")

    src = p.add_argument_group("price source (pick one)")
    src.add_argument("--prices", action="append", metavar="FILE",
                     help="Price JSON from fetch_prices.py. Repeatable.")
    src.add_argument("--symbol", help="Fetch this symbol, then simulate it.")
    src.add_argument("--watchlist", action="store_true",
                     help="Fetch every symbol in TradingView's watchlist panel.")
    src.add_argument("--env-watchlist", action="store_true",
                     help="Use WATCHLIST from .env instead of TradingView's panel.")

    win = p.add_argument_group("fetch window (ignored with --prices)")
    win.add_argument("--interval", default="1h", help="Bar interval (default 1h).")
    win.add_argument("--days", type=int, default=90,
                     help="Lookback window in days (default 90).")

    st = p.add_argument_group("strategy + risk")
    st.add_argument("--starting-capital", type=float, default=None,
                    help="Starting capital (default: DEFAULT_STARTING_CASH from .env).")
    st.add_argument("--fast", type=int, default=20, help="Fast SMA window (default 20).")
    st.add_argument("--slow", type=int, default=50, help="Slow SMA window (default 50).")
    st.add_argument("--stop-loss-pct", type=float, default=0.0,
                    help="Hard stop-loss %% below entry (default 0 = off).")
    st.add_argument("--trailing-stop-pct", type=float, default=0.0,
                    help="Trailing stop %% below the peak since entry (default 0 = off).")
    st.add_argument("--take-profit", type=float, default=0.0,
                    help="Take-profit %% above entry (default 0 = off).")
    st.add_argument("--trend-filter", type=int, default=0,
                    help="Only go long when price > SMA(N) (default 0 = off).")
    st.add_argument("--risk-pct", type=float, default=0.0,
                    help="Risk %% of equity per trade; sizes off the tightest stop "
                         "(default 0 = all-in).")
    st.add_argument("--max-drawdown-pct", type=float, default=0.0,
                    help="Liquidate and halt if equity falls this %% below its peak "
                         "(default 0 = off).")

    out = p.add_argument_group("output")
    out.add_argument("--out", help="Write JSON here. Default: .tmp/simulation_<interval>.json")
    out.add_argument("--stdout", action="store_true", help="Also print the JSON to stdout.")
    out.add_argument("--tv-repo", help="Path to the tradingview-mcp checkout.")
    out.add_argument("--settle", type=float, default=1.5, help="Chart settle seconds.")
    out.add_argument("-v", "--verbose", action="store_true", help="Echo bridge commands.")
    return p


def load_price_files(paths):
    series = []
    for path in paths:
        try:
            payload = C.read_json(path)
        except (OSError, ValueError) as e:
            print(f"! {path}: {e}", file=sys.stderr)
            continue
        bars = payload.get("bars")
        if not bars:
            print(f"! {path}: no bars in file", file=sys.stderr)
            continue
        series.append((payload.get("symbol", str(path)), bars, payload))
    return series


def fetch_series(args):
    resolution = C.resolve_interval(args.interval)
    capped, wanted = C.days_to_bars(args.days, resolution)
    if wanted > C.MAX_BARS:
        print(f"! {args.days}d/{args.interval} ~ {wanted} bars; the bridge caps at "
              f"{C.MAX_BARS}. Using the most recent {capped}.", file=sys.stderr)

    bridge = C.get_bridge(tv_repo=args.tv_repo, settle=args.settle, verbose=args.verbose)
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
            series.append((sym, bridge.load_bars(sym, resolution, capped), None))
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
        print("! no price series to simulate", file=sys.stderr)
        return 1

    capital = (args.starting_capital if args.starting_capital is not None
               else C.env_float("DEFAULT_STARTING_CASH", C.DEFAULT_STARTING_CASH))

    results = []
    for symbol, bars, meta in series:
        if bars is None:
            res = {"error": (meta or {}).get("error", "no bars")}
        else:
            res = simulate_strategy(
                bars, capital, fast=args.fast, slow=args.slow,
                stop_loss_pct=args.stop_loss_pct,
                trailing_stop_pct=args.trailing_stop_pct,
                take_profit_pct=args.take_profit, trend_filter=args.trend_filter,
                risk_pct=args.risk_pct, max_drawdown_pct=args.max_drawdown_pct,
            )
        res["symbol"] = symbol
        if meta and meta.get("interval"):
            res["interval"] = meta["interval"]
        results.append(res)

    payload = {
        "ran_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "starting_capital": round(capital, 2),
        "strategy": _sim_label(args.fast, args.slow, args.stop_loss_pct,
                               args.trailing_stop_pct, args.take_profit,
                               args.trend_filter, args.risk_pct,
                               args.max_drawdown_pct),
        "results": results,
    }
    intervals = {r.get("interval") for r in results if r.get("interval")}
    tag = intervals.pop() if len(intervals) == 1 else args.interval
    out = args.out or f".tmp/simulation_{tag}.json"
    path = C.write_json(out, payload)

    errors = sum(1 for r in results if "error" in r)
    halted = sum(1 for r in results if r.get("halted"))
    print(f"{len(results)} result(s) ({errors} error, {halted} halted) -> {path}",
          file=sys.stderr)

    if args.stdout:
        print(json.dumps(payload, indent=2))
    return 1 if errors and errors == len(results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
