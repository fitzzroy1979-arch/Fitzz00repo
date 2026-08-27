#!/usr/bin/env python3
"""
00fitzz.py — a small trading CLI that runs on top of the local `tradingview-mcp`
bridge. It reads OHLCV / watchlist data from your running TradingView Desktop app
(via the `tv` CLI) and can:

  * --backtest   run a strategy over historical bars and report performance
  * --learn      let an LLM tune the strategy parameters in a backtest loop:
                 backtest → feed metrics to the model → it proposes new
                 parameters (fast/slow SMA windows + optional stop-loss,
                 take-profit, trend filter) → re-backtest, iterated a few
                 rounds. Works on one --symbol or across the whole --watchlist.
                 Default provider is `hermes` on Together (TOGETHER_API_KEY);
                 `--learn-provider claude` uses the Anthropic API,
                 `--learn-provider perplexity` uses Sonar (PERPLEXITY_API_KEY),
                 and `--learn-provider gemini` uses Google AI Studio's free tier
                 (GEMINI_API_KEY, no credit card).
  * --research   research a --symbol or --watchlist with Perplexity's Sonar
                 "online" models — live web search with citations — and print a
                 structured strategy brief (catalysts, sentiment, technical read,
                 directional bias + key levels). Needs PERPLEXITY_API_KEY. Enriched
                 with live price context from TradingView when it's reachable, but
                 works without it. Research only; never places an order.
  * --simulate   walk-forward paper simulation with portfolio risk management —
                 hard stop (--stop-loss-pct), trailing stop (--trailing-stop-pct),
                 risk-based sizing (--risk-pct), and a max-drawdown circuit
                 breaker (--max-drawdown-pct). One --simulate SYMBOL or the whole
                 --watchlist, over the last --days days. Paper only; no orders.
  * --trade      (STUB) print/log an *intended* order — it never places a real
                 order, because this build is TradingView-data-only.
  * --futures-*  (PAPER) a make-believe leveraged-futures tracker persisted to a
                 local JSON file: --futures-trade opens a simulated position
                 (--direction, --leverage, --margin), --futures-portfolio shows
                 margin/PnL/liquidation, --futures-close realizes it. No exchange
                 is ever contacted and no real leveraged order is placed.

Data source: the sibling `tradingview-mcp` project's `tv` CLI, which talks to
TradingView Desktop over Chrome DevTools Protocol. TradingView Desktop must be
running with the debug port enabled (see that project's SETUP_GUIDE.md).

Examples:
  python3 00fitzz.py --backtest --watchlist --period 1y --interval 1d --starting-capital 1000
  python3 00fitzz.py --backtest --symbol BTCUSD --period 6mo --interval 1d
  python3 00fitzz.py --research BTCUSD --interval 1d
  python3 00fitzz.py --research --watchlist --json
  python3 00fitzz.py --trade XRP-USD --action buy --amount 50
  python3 00fitzz.py --trade XRP-USD --action buy --amount 100 --ignore-trade-window

Trade window: live-trade commands are allowed 24/7 by default. Pass a narrower
window to gate them to certain hours (local time):
  --trade-window-start H --trade-window-end H   e.g. --trade-window-start 7 --trade-window-end 19
  --ignore-trade-window                         bypass any window for one command
"""

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #

# This module lives in the `fitzz` package; the tradingview-mcp checkout and the
# .00fitzz state dir sit at the project root, one level up from the package.
SCRIPT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_TV_REPO = SCRIPT_DIR / "tradingview-mcp"
ORDER_LOG = SCRIPT_DIR / ".00fitzz" / "orders.log"
FUTURES_STATE = SCRIPT_DIR / ".00fitzz" / "futures.json"
FUTURES_CLOSED_LOG = SCRIPT_DIR / ".00fitzz" / "futures_closed.log"

MAX_BARS = 500  # hard cap enforced by the tv bridge (see core/data.js)

# --learn provider defaults. hermes -> Together's OpenAI-compatible endpoint;
# claude -> the Anthropic API via the official SDK; perplexity -> Sonar over
# Perplexity's OpenAI-compatible endpoint (PERPLEXITY_API_KEY); gemini -> Google
# AI Studio's OpenAI-compatible endpoint (GEMINI_API_KEY, free tier, no card).
DEFAULT_LEARN_MODELS = {
    "hermes": "NousResearch/Hermes-3-Llama-3.1-70B",
    "claude": "claude-opus-5",
    "perplexity": "sonar",
    "gemini": "gemini-2.5-flash",
}
TOGETHER_URL = "https://api.together.xyz/v1/chat/completions"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"

# --research uses Perplexity's Sonar "online" models, which search the live web
# and return citations. sonar-pro is the deeper research model.
PERPLEXITY_URL = "https://api.perplexity.ai/chat/completions"
DEFAULT_RESEARCH_MODEL = "sonar-pro"

# Safe bounds the LLM's proposed parameters are clamped to.
FAST_MIN, FAST_MAX = 3, 80
SLOW_MIN, SLOW_MAX = 5, 200
SL_MAX = 50.0          # stop-loss %
TP_MAX = 100.0         # take-profit %
TREND_MIN, TREND_MAX = 20, 200

# Map friendly --interval values to TradingView resolutions.
INTERVAL_TO_TV = {
    "1m": "1", "1min": "1",
    "5m": "5", "15m": "15", "30m": "30",
    "1h": "60", "2h": "120", "4h": "240",
    "1d": "1D", "1day": "1D",
    "1w": "1W", "1week": "1W",
    "1mo": "1M",
}

# Approx minutes per bar, used to turn --period into a bar count.
INTERVAL_MINUTES = {
    "1": 1, "5": 5, "15": 15, "30": 30,
    "60": 60, "120": 120, "240": 240,
    "1D": 1440, "1W": 1440 * 7, "1M": 1440 * 30,
}


class BridgeError(RuntimeError):
    """Raised when the tv bridge can't be reached or returns an error."""


# --------------------------------------------------------------------------- #
# TradingView bridge (thin wrapper over the `tv` CLI)
# --------------------------------------------------------------------------- #

class TradingViewBridge:
    def __init__(self, repo=DEFAULT_TV_REPO, node=None, settle=1.5, verbose=False):
        self.repo = Path(repo)
        self.cli = self.repo / "src" / "cli" / "index.js"
        self.node = node or os.environ.get("FITZZ_NODE") or shutil.which("node") or "node"
        self.settle = settle          # seconds to let a symbol/timeframe load
        self.verbose = verbose

    def _run(self, args):
        if not self.cli.exists():
            raise BridgeError(
                f"tv CLI not found at {self.cli}. Point --tv-repo at the "
                f"tradingview-mcp checkout."
            )
        cmd = [self.node, str(self.cli), *args]
        if self.verbose:
            print(f"  $ {' '.join(cmd)}", file=sys.stderr)
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except FileNotFoundError:
            raise BridgeError(
                f"Could not launch node ('{self.node}'). Set FITZZ_NODE to your "
                f"node binary (nvm users: `which node` after sourcing nvm)."
            )
        except subprocess.TimeoutExpired:
            raise BridgeError(f"tv {' '.join(args)} timed out after 60s.")

        # exit code 2 == connection failure in the tv CLI
        if proc.returncode == 2:
            raise BridgeError(
                "Can't reach TradingView Desktop. Launch it with the debug port "
                "enabled (see tradingview-mcp/SETUP_GUIDE.md), then retry."
            )
        out = proc.stdout.strip()
        if not out:
            err = proc.stderr.strip() or f"exit {proc.returncode}"
            raise BridgeError(f"tv {' '.join(args)} produced no output: {err}")
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            raise BridgeError(f"tv {' '.join(args)} returned non-JSON:\n{out[:400]}")

    # -- data ------------------------------------------------------------- #

    def get_watchlist(self):
        data = self._run(["watchlist", "get"])
        syms = [s.get("symbol") for s in data.get("symbols", []) if s.get("symbol")]
        if not syms:
            raise BridgeError("Watchlist is empty (or the panel wasn't open).")
        return syms

    def set_symbol(self, symbol):
        # `symbol` / `timeframe` are top-level tv commands, not under `chart`.
        self._run(["symbol", symbol])

    def set_timeframe(self, tv_resolution):
        self._run(["timeframe", tv_resolution])

    def get_ohlcv(self, count):
        count = min(count, MAX_BARS)
        # The chart may still be loading right after a symbol/timeframe change.
        last_err = None
        for attempt in range(4):
            try:
                data = self._run(["ohlcv", "-n", str(count)])
                bars = data.get("bars", [])
                if bars:
                    return bars
                last_err = "no bars returned"
            except BridgeError as e:
                last_err = str(e)
            time.sleep(self.settle)
        raise BridgeError(f"Could not read OHLCV: {last_err}")

    def load_bars(self, symbol, tv_resolution, count):
        """Set symbol + timeframe, wait for the chart to settle, read bars."""
        self.set_symbol(symbol)
        time.sleep(self.settle)
        self.set_timeframe(tv_resolution)
        time.sleep(self.settle)
        return self.get_ohlcv(count)

    def get_quote(self, symbol):
        try:
            return self._run(["quote", symbol])
        except BridgeError:
            return None


# --------------------------------------------------------------------------- #
# Period / interval helpers
# --------------------------------------------------------------------------- #

def resolve_interval(interval):
    key = interval.strip().lower()
    if key in INTERVAL_TO_TV:
        return INTERVAL_TO_TV[key]
    # Allow raw TradingView resolutions to pass through (e.g. "1D", "60").
    if interval in INTERVAL_MINUTES:
        return interval
    raise ValueError(f"Unknown --interval '{interval}'. Try one of: "
                     f"{', '.join(sorted(INTERVAL_TO_TV))}")


def period_to_bars(period, tv_resolution):
    """Turn '1y' / '6mo' / '90d' into an approximate bar count for the interval."""
    p = period.strip().lower()
    units = {"y": 525600, "mo": 43200, "w": 10080, "d": 1440, "h": 60}
    # Split leading digits from the trailing unit (e.g. "6mo" -> "6", "mo").
    i = 0
    while i < len(p) and p[i].isdigit():
        i += 1
    num, unit = p[:i], p[i:]
    if not num or unit not in units:
        raise ValueError(f"Unknown --period '{period}'. Try 1y, 6mo, 90d, 30d, 48h.")
    total_minutes = int(num) * units[unit]
    per_bar = INTERVAL_MINUTES.get(tv_resolution, 1440)
    bars = max(2, total_minutes // per_bar)
    return min(bars, MAX_BARS), bars


def days_to_bars(days, tv_resolution):
    """Turn a day count into an approximate bar count for the interval."""
    per_bar = INTERVAL_MINUTES.get(tv_resolution, 1440)
    bars = max(2, int(days * 1440 / per_bar))
    return min(bars, MAX_BARS), bars


# --------------------------------------------------------------------------- #
# Strategy + backtest
# --------------------------------------------------------------------------- #

def sma(values, window):
    """Simple moving average; None until enough data is present."""
    out = [None] * len(values)
    if window <= 0:
        return out
    run = 0.0
    for i, v in enumerate(values):
        run += v
        if i >= window:
            run -= values[i - window]
        if i >= window - 1:
            out[i] = run / window
    return out


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


def fmt_time(t):
    if t is None:
        return None
    try:
        t = float(t)
        if t > 1e12:      # milliseconds
            t /= 1000.0
        return dt.datetime.fromtimestamp(t).strftime("%Y-%m-%d")
    except (ValueError, OSError, OverflowError):
        return str(t)


# --------------------------------------------------------------------------- #
# Trade window gate
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
# Commands
# --------------------------------------------------------------------------- #

def cmd_backtest(args, bridge):
    tv_res = resolve_interval(args.interval)
    capped, wanted = period_to_bars(args.period, tv_res)
    if wanted > MAX_BARS:
        print(f"! {args.period}/{args.interval} ≈ {wanted} bars; the TradingView "
              f"bridge caps at {MAX_BARS}. Using the most recent {capped}.",
              file=sys.stderr)

    if args.watchlist:
        symbols = bridge.get_watchlist()
        print(f"Backtesting {len(symbols)} watchlist symbol(s): "
              f"{', '.join(symbols)}\n", file=sys.stderr)
    elif args.symbol:
        symbols = [args.symbol]
    else:
        raise SystemExit("Backtest needs --watchlist or --symbol SYMBOL.")

    results = []
    for sym in symbols:
        try:
            bars = bridge.load_bars(sym, tv_res, capped)
            metrics = backtest_sma_cross(
                bars, args.starting_capital, fast=args.fast, slow=args.slow,
                stop_loss_pct=args.stop_loss, take_profit_pct=args.take_profit,
                trend_filter=args.trend_filter,
            )
        except BridgeError as e:
            metrics = {"error": str(e)}
        metrics["symbol"] = sym
        results.append(metrics)
        if not args.json and not args.proven_only:
            print_result_row(metrics)

    display = results
    if args.proven_only:
        display = [r for r in results if _is_proven(r, args.proven_min_trades)]
        if not args.json:
            print(f"proven-only: {len(display)}/{len(results)} symbol(s) passed "
                  f"(return>0, trades>={args.proven_min_trades}).\n", file=sys.stderr)
            for m in display:
                print_result_row(m)

    if args.json:
        print(json.dumps(display, indent=2))
    else:
        print_backtest_summary(display)
    return display


def _is_proven(m, min_trades):
    """A symbol 'proves out' if its backtest made money over enough trades."""
    return ("error" not in m
            and m.get("return_pct", 0) > 0
            and m.get("trades", 0) >= min_trades)


def print_result_row(m):
    if "error" in m:
        print(f"  {m['symbol']:<14} — error: {m['error']}")
        return
    print(f"  {m['symbol']:<14} "
          f"ret {m['return_pct']:>7.2f}%  "
          f"b&h {m['buy_hold_pct']:>7.2f}%  "
          f"trades {m['trades']:>3}  "
          f"win {m['win_rate_pct']:>5.1f}%  "
          f"maxDD {m['max_drawdown_pct']:>7.2f}%")


def print_backtest_summary(results):
    ok = [r for r in results if "error" not in r]
    if not ok:
        print("\nNo symbols produced results.")
        return
    avg_ret = sum(r["return_pct"] for r in ok) / len(ok)
    avg_bh = sum(r["buy_hold_pct"] for r in ok) / len(ok)
    best = max(ok, key=lambda r: r["return_pct"])
    print("\n" + "─" * 60)
    print(f"  strategy {ok[0]['strategy']}   window {ok[0]['from']} → {ok[0]['to']}")
    print(f"  avg return {avg_ret:+.2f}%   avg buy&hold {avg_bh:+.2f}%   "
          f"symbols {len(ok)}/{len(results)}")
    print(f"  best: {best['symbol']} ({best['return_pct']:+.2f}%)")
    print("─" * 60)


def cmd_trade(args, bridge):
    """
    STUB. This build is TradingView-data-only, so it NEVER places a real order.
    It gates on the trade window, fetches a reference price, and logs the intent.
    """
    ok, reason = check_trade_window(
        args.trade_window_start, args.trade_window_end, args.ignore_trade_window
    )
    print(f"[trade-window] {reason}", file=sys.stderr)
    if not ok:
        raise SystemExit(1)

    quote = bridge.get_quote(args.trade)
    price = None
    if isinstance(quote, dict):
        price = quote.get("price") or quote.get("last") or quote.get("close")

    order = {
        "ts": dt.datetime.now().isoformat(timespec="seconds"),
        "symbol": args.trade,
        "action": args.action,
        "amount": args.amount,
        "ref_price": price,
        "est_units": round(args.amount / price, 8) if price else None,
        "mode": "SIMULATED",
        "note": "No real order placed — TradingView-data-only build.",
    }

    ORDER_LOG.parent.mkdir(parents=True, exist_ok=True)
    with ORDER_LOG.open("a") as fh:
        fh.write(json.dumps(order) + "\n")

    if args.json:
        print(json.dumps(order, indent=2))
    else:
        px = f"${price}" if price else "unavailable"
        units = f"{order['est_units']} units" if order["est_units"] else "n/a"
        print("┌─ SIMULATED ORDER (no real trade placed) "
              "──────────────────────")
        print(f"│  {args.action.upper()} {args.amount} of {args.trade}")
        print(f"│  reference price: {px}   est. size: {units}")
        print(f"│  logged to: {ORDER_LOG}")
        print("└──────────────────────────────────────────────────────────")
    return order


# --------------------------------------------------------------------------- #
# --learn: LLM-in-the-loop parameter tuning
# --------------------------------------------------------------------------- #

class LearnError(RuntimeError):
    """Raised when the tuning LLM can't be reached or returns junk."""


LEARN_SYSTEM = (
    "You tune parameters for a long-only SMA-crossover trading backtest. Base "
    "rule: go fully long when the fast SMA crosses above the slow SMA, exit to "
    "cash when it crosses below. Optional risk controls you may also set: "
    "stop_loss (exit if price falls this percent below entry; 0 disables), "
    "take_profit (exit if price rises this percent above entry; 0 disables), and "
    "trend (only enter long when price is above the SMA of this many bars; 0 "
    "disables). You are given results of prior parameter sets and must propose "
    "the next one to try, improving return_pct while keeping max_drawdown_pct "
    "contained and the trade count sane. Respond with ONLY a JSON object: "
    '{"fast": int, "slow": int, "stop_loss": number, "take_profit": number, '
    '"trend": int, "rationale": "one sentence"}. '
    f"Constraints: {FAST_MIN}<=fast<={FAST_MAX}, {SLOW_MIN}<=slow<={SLOW_MAX}, "
    f"fast<slow; stop_loss 0 or up to {SL_MAX:g}; take_profit 0 or up to "
    f"{TP_MAX:g}; trend 0 or {TREND_MIN}..{TREND_MAX}."
)


def _learn_user_prompt(symbol, interval, history):
    lines = [
        f"Symbol: {symbol}   Interval: {interval}",
        "Results so far (most recent last):",
    ]
    for h in history:
        params = (f"fast={h['fast']} slow={h['slow']} stop_loss={h.get('stop_loss', 0)} "
                 f"take_profit={h.get('take_profit', 0)} trend={h.get('trend', 0)}")
        if "error" in h:
            lines.append(f"- {params} -> error: {h['error']}")
            continue
        lines.append(
            f"- {params} -> return={h['return_pct']}% buy_hold={h['buy_hold_pct']}% "
            f"trades={h['trades']} win_rate={h['win_rate_pct']}% "
            f"max_drawdown={h['max_drawdown_pct']}%"
        )
    lines.append("Propose the next parameter set to try.")
    return "\n".join(lines)


def _extract_json(text):
    """Pull the first JSON object out of a model response."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    raise LearnError(f"Model did not return JSON. Got: {text[:200]!r}")


def _call_claude(model, system, user):
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        raise LearnError("ANTHROPIC_API_KEY is not set (get one at console.anthropic.com).")
    try:
        import anthropic
    except ImportError:
        raise LearnError("The 'anthropic' package is not installed. Run: pip install -r requirements.txt")
    try:
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=model,
            # Claude Opus 5 (the default) runs adaptive thinking on by default, and
            # those thinking tokens share this budget with the answer. Keep it roomy
            # so a longer chain of thought can't truncate the small JSON that follows.
            max_tokens=8000,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
    except Exception as e:  # SDK/network/auth errors -> a clean message
        raise LearnError(f"Anthropic API call failed: {e}")
    if getattr(resp, "stop_reason", None) == "max_tokens":
        raise LearnError(
            "Anthropic response hit the max_tokens cap before finishing (thinking "
            "likely consumed the budget). Retry, or raise max_tokens in _call_claude."
        )
    return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")


def _call_hermes(model, system, user):
    api_key = os.environ.get("TOGETHER_API_KEY")
    if not api_key:
        raise LearnError("TOGETHER_API_KEY is not set (get one at together.ai), or use "
                        "--learn-provider claude.")
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": 1024,
        "temperature": 0.3,
        "response_format": {"type": "json_object"},
    }).encode()
    req = urllib.request.Request(
        TOGETHER_URL, data=body, method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:200]
        raise LearnError(f"Together API HTTP {e.code}: {detail}")
    except urllib.error.URLError as e:
        raise LearnError(f"Together API unreachable: {e.reason}")
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        raise LearnError(f"Unexpected Together response: {json.dumps(data)[:200]}")


def _call_gemini(model, system, user):
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise LearnError("GEMINI_API_KEY is not set (free at aistudio.google.com), "
                         "or use a different --learn-provider.")
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": 1024,
        "temperature": 0.3,
        "response_format": {"type": "json_object"},
    }).encode()
    req = urllib.request.Request(
        GEMINI_URL, data=body, method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:200]
        raise LearnError(f"Gemini API HTTP {e.code}: {detail}")
    except urllib.error.URLError as e:
        raise LearnError(f"Gemini API unreachable: {e.reason}")
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        raise LearnError(f"Unexpected Gemini response: {json.dumps(data)[:200]}")


def _call_perplexity(model, system, user, json_mode=False, temperature=0.2):
    """Call Perplexity's OpenAI-compatible Sonar endpoint.

    Returns (content, citations). Sonar models search the live web, so
    `citations` is a list of source URLs backing the answer (may be empty).
    """
    api_key = os.environ.get("PERPLEXITY_API_KEY")
    if not api_key:
        raise LearnError("PERPLEXITY_API_KEY is not set (get one at "
                         "perplexity.ai/settings/api).")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    req = urllib.request.Request(
        PERPLEXITY_URL, data=json.dumps(payload).encode(), method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        raise LearnError(f"Perplexity API HTTP {e.code}: {detail}")
    except urllib.error.URLError as e:
        raise LearnError(f"Perplexity API unreachable: {e.reason}")
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        raise LearnError(f"Unexpected Perplexity response: {json.dumps(data)[:200]}")
    # Perplexity returns sources either as top-level `citations` or, on newer
    # responses, as `search_results` objects with a `url` field.
    citations = data.get("citations") or []
    if not citations:
        citations = [s.get("url") for s in data.get("search_results", []) if s.get("url")]
    return content, citations


def _clamp_params(obj):
    """Coerce and clamp a raw proposal dict into safe strategy parameters."""
    def num(key, default):
        try:
            return float(obj.get(key, default))
        except (TypeError, ValueError):
            return default

    fast = int(max(FAST_MIN, min(FAST_MAX, num("fast", 20))))
    slow = int(max(SLOW_MIN, min(SLOW_MAX, num("slow", 50))))
    if fast >= slow:                      # keep the crossover meaningful
        slow = min(SLOW_MAX, fast + 1)
    sl = num("stop_loss", 0)
    sl = 0.0 if sl <= 0 else min(SL_MAX, sl)
    tp = num("take_profit", 0)
    tp = 0.0 if tp <= 0 else min(TP_MAX, tp)
    trend = int(num("trend", 0))
    trend = 0 if trend <= 0 else max(TREND_MIN, min(TREND_MAX, trend))
    return {"fast": fast, "slow": slow, "stop_loss": round(sl, 2),
            "take_profit": round(tp, 2), "trend": trend}


def llm_propose(provider, model, symbol, interval, history):
    """Ask the configured provider for the next parameter set (clamped)."""
    user = _learn_user_prompt(symbol, interval, history)
    if provider == "claude":
        text = _call_claude(model, LEARN_SYSTEM, user)
    elif provider == "perplexity":
        text, _ = _call_perplexity(model, LEARN_SYSTEM, user)
    elif provider == "gemini":
        text = _call_gemini(model, LEARN_SYSTEM, user)
    else:
        text = _call_hermes(model, LEARN_SYSTEM, user)
    obj = _extract_json(text)
    if "fast" not in obj and "slow" not in obj:
        raise LearnError(f"Proposal missing fast/slow: {obj!r}")
    params = _clamp_params(obj)
    params["rationale"] = str(obj.get("rationale", "")).strip()
    return params


def _tune_symbol(args, provider, model, symbol, bars):
    """Run the baseline + N tuning rounds for one symbol's bars."""
    def run(params):
        m = backtest_sma_cross(
            bars, args.starting_capital, fast=params["fast"], slow=params["slow"],
            stop_loss_pct=params["stop_loss"], take_profit_pct=params["take_profit"],
            trend_filter=params["trend"],
        )
        m.update(params)
        return m

    base = {"fast": args.fast, "slow": args.slow, "stop_loss": args.stop_loss,
            "take_profit": args.take_profit, "trend": args.trend_filter, "rationale": ""}
    history = [run(base)]
    _print_learn_row("baseline", history[0])

    for i in range(args.learn_iterations):
        try:
            proposal = llm_propose(provider, model, symbol, args.interval, history)
        except LearnError as e:
            print(f"  ! tuning stopped: {e}", file=sys.stderr)
            break
        m = run(proposal)
        history.append(m)
        _print_learn_row(f"round {i + 1}", m)

    ok = [h for h in history if "error" not in h]
    best = max(ok, key=lambda h: h["return_pct"]) if ok else None
    return {"history": history, "best": best}


def cmd_learn(args, bridge):
    provider = args.learn_provider
    model = args.learn_model or DEFAULT_LEARN_MODELS[provider]

    if args.watchlist:
        symbols = bridge.get_watchlist()
    elif args.symbol:
        symbols = [args.symbol]
    else:
        raise SystemExit("--learn needs --symbol SYMBOL or --watchlist.")

    tv_res = resolve_interval(args.interval)
    capped, _ = period_to_bars(args.period, tv_res)
    print(f"Tuning via {provider} ({model}): {args.learn_iterations} round(s) "
          f"x {len(symbols)} symbol(s)", file=sys.stderr)

    results = {}
    for sym in symbols:
        if len(symbols) > 1:
            print(f"\n### {sym}", file=sys.stderr)
        try:
            bars = bridge.load_bars(sym, tv_res, capped)
        except BridgeError as e:
            print(f"  bridge error: {e}", file=sys.stderr)
            results[sym] = {"history": [], "best": None, "error": str(e)}
            continue
        results[sym] = _tune_symbol(args, provider, model, sym, bars)

    if args.json:
        print(json.dumps({"provider": provider, "model": model, "results": results},
                        indent=2, default=str))
    elif len(symbols) == 1:
        best = results[symbols[0]].get("best")
        if best:
            _print_best(best)
    else:
        print("\n" + "═" * 64)
        print("  best per symbol:")
        for sym in symbols:
            best = results[sym].get("best")
            if best:
                print(f"    {sym:<14} {best['strategy']:<34} {best['return_pct']:+7.2f}%")
            else:
                print(f"    {sym:<14} — {results[sym].get('error', 'no result')}")
        print("═" * 64)
    return results


def _print_best(best):
    print("\n" + "─" * 64)
    print(f"  best: {best['strategy']}  return {best['return_pct']:+.2f}%  "
          f"(buy&hold {best['buy_hold_pct']:+.2f}%, maxDD {best['max_drawdown_pct']:.2f}%)")
    print("─" * 64)


def _print_learn_row(label, m):
    if "error" in m:
        print(f"  {label:<9} f{m['fast']}/s{m['slow']}  error: {m['error']}")
        return
    knobs = f"f{m['fast']}/s{m['slow']}"
    if m.get("trend"):
        knobs += f" tr{m['trend']}"
    if m.get("stop_loss"):
        knobs += f" sl{m['stop_loss']:g}%"
    if m.get("take_profit"):
        knobs += f" tp{m['take_profit']:g}%"
    line = (f"  {label:<9} {knobs:<26} ret {m['return_pct']:>7.2f}%  "
            f"trades {m['trades']:>3}  maxDD {m['max_drawdown_pct']:>7.2f}%")
    if m.get("rationale"):
        line += f"  — {m['rationale']}"
    print(line)


# --------------------------------------------------------------------------- #
# --research: Perplexity Sonar market research + strategy brief
# --------------------------------------------------------------------------- #

RESEARCH_SYSTEM = (
    "You are a markets research analyst. Research the given instrument using "
    "current, reputable web sources and produce a concise, decision-oriented "
    "brief. Be specific and cite figures/dates. Do NOT give personalized "
    "financial advice or tell the user to buy/sell; frame everything as neutral "
    "analysis of the setup. Structure the answer with these markdown sections:\n"
    "## Snapshot — one or two lines on what the instrument is and where it sits.\n"
    "## Catalysts & News — the most relevant developments from roughly the last "
    "two weeks, each with a date.\n"
    "## Sentiment — bullish/bearish/mixed, and why.\n"
    "## Technical Read — trend, momentum, and notable support/resistance levels.\n"
    "## Strategy — a directional bias (long / short / neutral) with a conviction "
    "level, the key price levels that would confirm or invalidate it, the main "
    "risks, and how it maps to a long-only SMA-crossover tool: whether faster or "
    "slower SMA windows suit the current regime, and whether a trend filter or "
    "stops look warranted.\n"
    "Keep the whole brief under ~450 words."
)


def _price_context(bridge, symbol, tv_res):
    """Best-effort live price/technical context from the tv bridge.

    Returns a short human-readable string, or None if TradingView is
    unreachable (research still works without it — the model uses the web)."""
    try:
        bars = bridge.load_bars(symbol, tv_res, 120)
    except BridgeError:
        return None
    closes = [b.get("close") for b in bars if isinstance(b.get("close"), (int, float))]
    if len(closes) < 20:
        return None
    last = closes[-1]
    fast_n, slow_n = 20, 50
    sma_fast = sum(closes[-fast_n:]) / fast_n
    sma_slow = sum(closes[-slow_n:]) / min(slow_n, len(closes)) if len(closes) >= slow_n else None
    window = closes[-60:]
    parts = [f"last={last:g}", f"SMA20={sma_fast:.4g}"]
    if sma_slow is not None:
        trend = "above" if sma_fast >= sma_slow else "below"
        parts.append(f"SMA50={sma_slow:.4g} (SMA20 {trend} SMA50)")
    parts.append(f"60-bar range {min(window):g}..{max(window):g}")
    return ", ".join(parts)


def _research_user_prompt(symbol, interval, price_ctx):
    lines = [f"Instrument: {symbol}", f"Chart interval: {interval}"]
    if price_ctx:
        lines.append(f"Live price context (from the user's TradingView, {interval} bars): "
                     f"{price_ctx}")
    else:
        lines.append("Live price context: unavailable — infer levels from public data.")
    lines.append(f"As of today ({dt.date.today().isoformat()}), research this instrument "
                 "and produce the brief.")
    return "\n".join(lines)


def _research_symbol(bridge, model, symbol, interval, tv_res):
    price_ctx = _price_context(bridge, symbol, tv_res)
    user = _research_user_prompt(symbol, interval, price_ctx)
    brief, citations = _call_perplexity(model, RESEARCH_SYSTEM, user, temperature=0.2)
    return {"symbol": symbol, "price_context": price_ctx,
            "brief": brief.strip(), "citations": citations}


def cmd_research(args, bridge):
    model = args.research_model or DEFAULT_RESEARCH_MODEL
    symbol = args.research or args.symbol
    if args.watchlist:
        symbols = bridge.get_watchlist()
    elif symbol:
        symbols = [symbol]
    else:
        raise SystemExit("--research needs a SYMBOL (e.g. --research BTCUSD) or --watchlist.")

    tv_res = resolve_interval(args.interval)
    print(f"Researching {len(symbols)} symbol(s) via Perplexity ({model})…",
          file=sys.stderr)

    results = {}
    for sym in symbols:
        try:
            results[sym] = _research_symbol(bridge, model, sym, args.interval, tv_res)
        except LearnError as e:
            print(f"  ! {sym}: {e}", file=sys.stderr)
            results[sym] = {"symbol": sym, "error": str(e)}

    if args.json:
        print(json.dumps({"model": model, "results": results}, indent=2, default=str))
    else:
        for sym in symbols:
            _print_research(results[sym])
    return results


def _print_research(res):
    print("\n" + "═" * 64)
    print(f"  RESEARCH — {res['symbol']}")
    print("═" * 64)
    if res.get("error"):
        print(f"  error: {res['error']}")
        return
    if res.get("price_context"):
        print(f"  live: {res['price_context']}\n")
    print(res["brief"])
    citations = res.get("citations") or []
    if citations:
        print("\nSources:")
        for i, url in enumerate(citations, 1):
            print(f"  [{i}] {url}")


# --------------------------------------------------------------------------- #
# --simulate: walk-forward paper simulation with portfolio risk management
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


def cmd_simulate(args, bridge):
    tv_res = resolve_interval(args.interval)
    capped, wanted = days_to_bars(args.days, tv_res)
    if wanted > MAX_BARS:
        print(f"! {args.days}d/{args.interval} ≈ {wanted} bars; the bridge caps at "
              f"{MAX_BARS}. Using the most recent {capped}.", file=sys.stderr)

    if args.simulate:               # a symbol string was given
        symbols = [args.simulate]
    elif args.watchlist:
        symbols = bridge.get_watchlist()
    else:
        raise SystemExit("--simulate needs a SYMBOL or --watchlist.")

    results = []
    for sym in symbols:
        try:
            bars = bridge.load_bars(sym, tv_res, capped)
            res = simulate_strategy(
                bars, args.starting_capital, fast=args.fast, slow=args.slow,
                stop_loss_pct=args.stop_loss_pct, trailing_stop_pct=args.trailing_stop_pct,
                take_profit_pct=args.take_profit, trend_filter=args.trend_filter,
                risk_pct=args.risk_pct, max_drawdown_pct=args.max_drawdown_pct,
            )
        except BridgeError as e:
            res = {"error": str(e)}
        res["symbol"] = sym
        results.append(res)

    if args.json:
        print(json.dumps(results, indent=2, default=str))
        return results
    for res in results:
        _print_sim(res, blotter=(len(symbols) == 1))
    if len(symbols) > 1:
        _print_sim_summary(results)
    return results


def _print_sim(res, blotter=False):
    sym = res["symbol"]
    if "error" in res:
        print(f"\n{sym}: error: {res['error']}")
        return
    halt = "   [HALTED: max-drawdown breached]" if res.get("halted") else ""
    print(f"\n{sym}  {res['strategy']}   {res['from']} → {res['to']}{halt}")
    print(f"  return {res['return_pct']:+.2f}%   buy&hold {res['buy_hold_pct']:+.2f}%   "
          f"trades {res['trades']}   win {res['win_rate_pct']:.1f}%   "
          f"maxDD {res['max_drawdown_pct']:.2f}%")
    if blotter and res.get("blotter"):
        print("  ── trades ──")
        for t in res["blotter"]:
            print(f"    {t['entry_date']} → {t['exit_date']}  size {t['size_pct']:>5.1f}%  "
                  f"{t['pnl_pct']:>+7.2f}%  ({t['reason']})")


def _print_sim_summary(results):
    ok = [r for r in results if "error" not in r]
    if not ok:
        print("\nNo symbols produced results.")
        return
    avg = sum(r["return_pct"] for r in ok) / len(ok)
    halted = sum(1 for r in ok if r.get("halted"))
    print("\n" + "═" * 64)
    print(f"  avg return {avg:+.2f}%   symbols {len(ok)}/{len(results)}   "
          f"halted {halted}")
    print("═" * 64)


# --------------------------------------------------------------------------- #
# Paper futures tracker (SIMULATED — no real leveraged orders are ever placed)
# --------------------------------------------------------------------------- #
#
# This build is TradingView-data-only: it tracks make-believe leveraged
# positions in a local JSON file so you can watch margin / PnL / liquidation
# behave, but it never connects to an exchange and never opens a real position.

def _load_futures():
    if FUTURES_STATE.exists():
        try:
            return json.loads(FUTURES_STATE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"positions": []}


def _save_futures(state):
    FUTURES_STATE.parent.mkdir(parents=True, exist_ok=True)
    FUTURES_STATE.write_text(json.dumps(state, indent=2))


def _mark_price(bridge, symbol):
    """Best-effort current price from the tv bridge; None if unavailable."""
    try:
        q = bridge.get_quote(symbol)
    except BridgeError:
        return None
    if isinstance(q, dict):
        for k in ("price", "last", "close", "lp"):
            v = q.get(k)
            if v:
                try:
                    return float(v)
                except (TypeError, ValueError):
                    pass
    return None


def cmd_futures_trade(args, bridge):
    symbol = args.futures_trade
    if not args.direction:
        raise SystemExit("--futures-trade requires --direction long|short.")
    if args.leverage is None or args.margin is None:
        raise SystemExit("--futures-trade requires --leverage and --margin.")
    lev = float(args.leverage)
    margin = float(args.margin)
    if lev < 1:
        raise SystemExit("--leverage must be >= 1.")
    if margin <= 0:
        raise SystemExit("--margin must be positive.")

    entry = args.entry_price if args.entry_price is not None else _mark_price(bridge, symbol)
    if not entry:
        raise SystemExit(f"No mark price for {symbol} (TradingView unreachable). "
                        f"Pass --entry-price P to open a paper position offline.")

    sign = 1 if args.direction == "long" else -1
    notional = margin * lev
    quantity = notional / entry
    # Approximate isolated-margin liquidation: a 1/leverage adverse move wipes
    # the margin. Ignores fees and maintenance margin.
    liq = entry * (1 - sign * (1 / lev))

    now = dt.datetime.now()
    pos = {
        "id": "F" + now.strftime("%m%d%H%M%S") + f"{now.microsecond // 1000:03d}",
        "symbol": symbol,
        "direction": args.direction,
        "leverage": lev,
        "margin": round(margin, 2),
        "notional": round(notional, 2),
        "quantity": quantity,
        "entry_price": entry,
        "liq_price": round(liq, 6),
        "opened_at": now.isoformat(timespec="seconds"),
        "mode": "SIMULATED",
    }
    state = _load_futures()
    state["positions"].append(pos)
    _save_futures(state)

    if args.json:
        print(json.dumps(pos, indent=2))
    else:
        print("┌─ SIMULATED FUTURES POSITION (paper — no real order placed) ──")
        print(f"│  {args.direction.upper()} {symbol}  {lev:g}x  margin ${margin:g}")
        print(f"│  entry ${entry:g}   notional ${notional:g}   qty {quantity:.6g}")
        print(f"│  est. liquidation ${liq:.6g}  (approx; no fees/maintenance margin)")
        print(f"│  id {pos['id']}   state: {FUTURES_STATE}")
        print("└──────────────────────────────────────────────────────────────")
    return pos


def cmd_futures_portfolio(args, bridge):
    positions = _load_futures()["positions"]
    if not positions:
        print("No open (paper) futures positions.")
        return []

    rows, total_margin, total_pnl, pnl_complete = [], 0.0, 0.0, True
    for p in positions:
        mark = _mark_price(bridge, p["symbol"])
        sign = 1 if p["direction"] == "long" else -1
        if mark:
            upnl = sign * (mark - p["entry_price"]) * p["quantity"]
            total_pnl += upnl
        else:
            upnl = None
            pnl_complete = False
        total_margin += p["margin"]
        rows.append((p, mark, upnl))

    if args.json:
        out = [{**p, "mark": mk, "unrealized_pnl": round(u, 2) if u is not None else None}
               for (p, mk, u) in rows]
        print(json.dumps({"positions": out,
                          "total_margin": round(total_margin, 2),
                          "total_unrealized_pnl": round(total_pnl, 2) if pnl_complete else None},
                        indent=2))
        return rows

    print("Open paper futures positions:")
    for p, mark, upnl in rows:
        head = f"  {p['id']}  {p['direction'].upper():<5} {p['symbol']:<10} {p['leverage']:g}x  margin ${p['margin']:g}"
        if mark is None:
            print(head + f"  entry ${p['entry_price']:g}  liq ${p['liq_price']:g}  (mark n/a)")
            continue
        pnl_pct = upnl / p["margin"] * 100 if p["margin"] else 0.0
        warn = "  ⚠ PAST LIQ" if ((p["direction"] == "long" and mark <= p["liq_price"]) or
                                  (p["direction"] == "short" and mark >= p["liq_price"])) else ""
        print(head + f"  mark ${mark:g}  uPnL ${upnl:+.2f} ({pnl_pct:+.1f}% on margin)  "
                     f"liq ${p['liq_price']:g}{warn}")
    tail = f"${total_pnl:+.2f}" if pnl_complete else "n/a (some marks unavailable)"
    print(f"  ── total margin ${total_margin:.2f}   total uPnL {tail}")
    return rows


def cmd_futures_close(args, bridge):
    state = _load_futures()
    positions = state["positions"]
    target = args.futures_close
    if target in ("", "__ALL__"):
        to_close = list(positions)
    else:
        to_close = [p for p in positions if target in (p["symbol"], p["id"])]
    if not to_close:
        print(f"Nothing to close (no open position matching {target!r})."
              if target not in ("", "__ALL__") else "No open positions to close.")
        return []

    realized = []
    for p in to_close:
        mark = _mark_price(bridge, p["symbol"]) or p["entry_price"]
        sign = 1 if p["direction"] == "long" else -1
        pnl = sign * (mark - p["entry_price"]) * p["quantity"]
        rec = {**p, "close_price": mark, "realized_pnl": round(pnl, 2),
               "closed_at": dt.datetime.now().isoformat(timespec="seconds")}
        realized.append(rec)

    state["positions"] = [p for p in positions if p not in to_close]
    _save_futures(state)
    FUTURES_CLOSED_LOG.parent.mkdir(parents=True, exist_ok=True)
    with FUTURES_CLOSED_LOG.open("a") as fh:
        for rec in realized:
            fh.write(json.dumps(rec) + "\n")

    if args.json:
        print(json.dumps(realized, indent=2))
        return realized
    total = sum(r["realized_pnl"] for r in realized)
    print("Closed (paper) futures positions:")
    for r in realized:
        print(f"  {r['id']}  {r['direction'].upper():<5} {r['symbol']:<10}  "
              f"entry ${r['entry_price']:g} → close ${r['close_price']:g}  "
              f"realized ${r['realized_pnl']:+.2f}")
    print(f"  ── total realized ${total:+.2f}   (logged to {FUTURES_CLOSED_LOG})")
    return realized


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def build_parser():
    p = argparse.ArgumentParser(
        prog="00fitzz.py",
        description="Backtest and (stub) trade on top of the tradingview-mcp bridge.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    mode = p.add_argument_group("mode")
    mode.add_argument("--backtest", action="store_true",
                      help="Run a backtest over historical bars.")
    mode.add_argument("--learn", action="store_true",
                      help="Tune strategy parameters with an LLM in a backtest loop (needs --symbol or --watchlist).")
    mode.add_argument("--simulate", nargs="?", const="", default=None, metavar="SYMBOL",
                      help="Walk-forward paper simulation with portfolio risk management. "
                           "Give a SYMBOL, or use with --watchlist.")
    mode.add_argument("--research", nargs="?", const="", default=None, metavar="SYMBOL",
                      help="Research a SYMBOL (or --watchlist) with Perplexity Sonar and "
                           "print a cited strategy brief. No orders are placed.")
    mode.add_argument("--trade", metavar="SYMBOL",
                      help="(STUB) Log an intended order for SYMBOL. No real order is placed.")
    mode.add_argument("--futures-trade", metavar="SYMBOL", default=None,
                      help="(PAPER) Open a simulated leveraged position. No real order is placed.")
    mode.add_argument("--futures-portfolio", action="store_true",
                      help="(PAPER) Show open simulated futures positions with margin/PnL/liquidation.")
    mode.add_argument("--futures-close", nargs="?", const="__ALL__", default=None, metavar="SYMBOL",
                      help="(PAPER) Close a simulated position by SYMBOL/id, or all if given bare.")

    bt = p.add_argument_group("backtest options")
    bt.add_argument("--watchlist", action="store_true",
                    help="Backtest every symbol in your TradingView watchlist.")
    bt.add_argument("--symbol", help="Single symbol to backtest (instead of --watchlist).")
    bt.add_argument("--period", default="1y", help="Lookback, e.g. 1y, 6mo, 90d (default 1y).")
    bt.add_argument("--interval", default="1d", help="Bar interval, e.g. 1d, 4h, 1h (default 1d).")
    bt.add_argument("--starting-capital", type=float, default=1000.0,
                    help="Starting capital for the backtest (default 1000).")
    bt.add_argument("--fast", type=int, default=20, help="Fast SMA window (default 20).")
    bt.add_argument("--slow", type=int, default=50, help="Slow SMA window (default 50).")
    bt.add_argument("--stop-loss", type=float, default=0.0,
                    help="Stop-loss %% below entry, e.g. 5 (default 0 = off).")
    bt.add_argument("--take-profit", type=float, default=0.0,
                    help="Take-profit %% above entry, e.g. 15 (default 0 = off).")
    bt.add_argument("--trend-filter", type=int, default=0,
                    help="Only go long when price > SMA(N), e.g. 200 (default 0 = off).")
    bt.add_argument("--proven-only", action="store_true",
                    help="Keep only symbols whose backtest return > 0 with at least "
                         "--proven-min-trades trades (useful with --watchlist).")
    bt.add_argument("--proven-min-trades", type=int, default=3,
                    help="Minimum trades for a symbol to count as proven (default 3).")

    sm = p.add_argument_group("simulate options")
    sm.add_argument("--days", type=int, default=90,
                    help="Lookback window in days for --simulate (default 90).")
    sm.add_argument("--stop-loss-pct", type=float, default=0.0,
                    help="Hard stop-loss %% below entry (default 0 = off).")
    sm.add_argument("--trailing-stop-pct", type=float, default=0.0,
                    help="Trailing stop %% below the peak since entry (default 0 = off).")
    sm.add_argument("--risk-pct", type=float, default=0.0,
                    help="Risk %% of equity per trade; sizes off the tightest stop (default 0 = all-in).")
    sm.add_argument("--max-drawdown-pct", type=float, default=0.0,
                    help="Liquidate and halt if equity falls this %% below its peak (default 0 = off).")

    ln = p.add_argument_group("learn options")
    ln.add_argument("--learn-provider",
                    choices=["hermes", "claude", "perplexity", "gemini"],
                    default="hermes",
                    help="Which LLM tunes the parameters (default hermes on Together).")
    ln.add_argument("--learn-model", default=None,
                    help="Override the provider's default model.")
    ln.add_argument("--learn-iterations", type=int, default=3,
                    help="How many tuning rounds to run (default 3).")

    rs = p.add_argument_group("research options")
    rs.add_argument("--research-model", default=None,
                    help=f"Perplexity model for --research (default {DEFAULT_RESEARCH_MODEL}).")

    fu = p.add_argument_group("futures options (paper)")
    fu.add_argument("--direction", choices=["long", "short"], help="Side for --futures-trade.")
    fu.add_argument("--leverage", type=float, help="Leverage multiple for --futures-trade (e.g. 5).")
    fu.add_argument("--margin", type=float, help="Margin (quote currency) for --futures-trade.")
    fu.add_argument("--entry-price", type=float, default=None,
                    help="Override the entry/mark price (use when TradingView is offline).")

    tr = p.add_argument_group("trade options")
    tr.add_argument("--action", choices=["buy", "sell"], help="Order side for --trade.")
    tr.add_argument("--amount", type=float, help="Quote-currency amount for --trade.")
    tr.add_argument("--trade-window-start", type=int, default=0,
                    help="Trade-window start hour, local time (default 0 = 24/7).")
    tr.add_argument("--trade-window-end", type=int, default=24,
                    help="Trade-window end hour, local time (default 24 = 24/7).")
    tr.add_argument("--ignore-trade-window", action="store_true",
                    help="Bypass the trade-window gate for one command.")

    misc = p.add_argument_group("misc")
    misc.add_argument("--tv-repo", default=str(DEFAULT_TV_REPO),
                      help=f"Path to the tradingview-mcp checkout (default {DEFAULT_TV_REPO}).")
    misc.add_argument("--settle", type=float, default=1.5,
                      help="Seconds to wait for the chart to load after a symbol/timeframe change.")
    misc.add_argument("--json", action="store_true", help="Emit JSON instead of a table.")
    misc.add_argument("-v", "--verbose", action="store_true", help="Echo tv commands to stderr.")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)

    modes = [args.backtest, args.trade, args.learn, args.simulate is not None,
             args.research is not None,
             args.futures_trade is not None, args.futures_portfolio,
             args.futures_close is not None]
    if not any(modes):
        build_parser().print_help()
        return 2

    bridge = TradingViewBridge(repo=args.tv_repo, settle=args.settle, verbose=args.verbose)

    try:
        if args.trade:
            if not args.action or args.amount is None:
                raise SystemExit("--trade requires --action buy|sell and --amount.")
            cmd_trade(args, bridge)
        if args.backtest:
            cmd_backtest(args, bridge)
        if args.learn:
            cmd_learn(args, bridge)
        if args.simulate is not None:
            cmd_simulate(args, bridge)
        if args.research is not None:
            cmd_research(args, bridge)
        if args.futures_trade is not None:
            cmd_futures_trade(args, bridge)
        if args.futures_portfolio:
            cmd_futures_portfolio(args, bridge)
        if args.futures_close is not None:
            cmd_futures_close(args, bridge)
    except BridgeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
