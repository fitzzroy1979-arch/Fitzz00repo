#!/usr/bin/env python3
"""Render a run_backtest.py payload as a report. Computes nothing.

Reads the JSON `run_backtest.py` wrote and emits either the monolith's terminal
table or a Markdown deliverable. Every number comes from the input file — this
script never touches bars, a bridge, or a strategy.

    python execution/run_backtest.py --prices .tmp/xrp.json --out .tmp/bt.json
    python execution/render_backtest_report.py --results .tmp/bt.json
    python execution/render_backtest_report.py --results .tmp/bt.json --format text

Markdown goes to `output/` (a deliverable); the text format goes to stdout,
matching what `fitzz trade --backtest` prints today.
"""

import argparse
import datetime as dt
import sys

import _common as C


# --------------------------------------------------------------------------- #
# Terminal format -- moved verbatim from fitzz/trading.py (L621-648)
# --------------------------------------------------------------------------- #

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


# --------------------------------------------------------------------------- #
# Markdown format
# --------------------------------------------------------------------------- #

def render_markdown(payload):
    """Turn a run_backtest.py payload into a Markdown report."""
    results = payload.get("results", [])
    ok = [r for r in results if "error" not in r]
    failed = [r for r in results if "error" in r]

    lines = ["# Agent 47 — Backtest Report", ""]

    strategy = payload.get("strategy") or (ok[0]["strategy"] if ok else "—")
    lines += [
        f"**Strategy:** `{strategy}`  ",
        f"**Starting capital:** ${payload.get('starting_capital', 0):,.2f}  ",
    ]
    if ok:
        intervals = sorted({r.get("interval") for r in ok if r.get("interval")})
        if intervals:
            lines.append(f"**Interval:** {', '.join(intervals)}  ")
        lines.append(f"**Window:** {ok[0].get('from')} → {ok[0].get('to')}  ")
    lines += [f"**Run at:** {payload.get('ran_at', '—')}", ""]

    if ok:
        lines += [
            "| Symbol | Return | Buy & hold | vs B&H | Trades | Win rate | Max DD | Final equity |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for r in sorted(ok, key=lambda x: x["return_pct"], reverse=True):
            edge = r["return_pct"] - r["buy_hold_pct"]
            lines.append(
                f"| `{r['symbol']}` | {r['return_pct']:+.2f}% | {r['buy_hold_pct']:+.2f}% | "
                f"{edge:+.2f} pp | {r['trades']} | {r['win_rate_pct']:.1f}% | "
                f"{r['max_drawdown_pct']:.2f}% | ${r['final_equity']:,.2f} |"
            )
        lines.append("")

        avg_ret = sum(r["return_pct"] for r in ok) / len(ok)
        avg_bh = sum(r["buy_hold_pct"] for r in ok) / len(ok)
        best = max(ok, key=lambda r: r["return_pct"])
        worst = min(ok, key=lambda r: r["return_pct"])
        beat = [r for r in ok if r["return_pct"] > r["buy_hold_pct"]]

        lines += [
            "## Summary", "",
            f"- **Average return:** {avg_ret:+.2f}% vs buy & hold {avg_bh:+.2f}% "
            f"({avg_ret - avg_bh:+.2f} pp)",
            f"- **Best:** `{best['symbol']}` at {best['return_pct']:+.2f}%",
            f"- **Worst:** `{worst['symbol']}` at {worst['return_pct']:+.2f}%",
            f"- **Beat buy & hold:** {len(beat)}/{len(ok)} symbol(s)",
            f"- **Symbols with results:** {len(ok)}/{len(results)}",
            "",
        ]

    if failed:
        lines += ["## Errors", ""]
        for r in failed:
            lines.append(f"- `{r.get('symbol', '?')}` — {r['error']}")
        lines.append("")

    if not ok:
        lines += ["No symbols produced results.", ""]

    lines += [
        "---", "",
        "*Backtested on historical bars from TradingView. Past performance of a "
        "rule on past data is not a prediction. No orders were placed and no "
        "funds were touched.*",
    ]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def build_parser():
    p = argparse.ArgumentParser(
        description="Render a run_backtest.py payload as Markdown or a terminal table.")
    p.add_argument("--results", required=True, metavar="FILE",
                   help="JSON payload written by run_backtest.py.")
    p.add_argument("--format", choices=["md", "text"], default="md",
                   help="md writes a deliverable to output/; text prints the "
                        "monolith's table to stdout (default: md).")
    p.add_argument("--out", help="Where to write the Markdown. Default: "
                                 "output/backtest_<interval>_<date>.md")
    p.add_argument("--stdout", action="store_true",
                   help="Also print the Markdown to stdout.")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)

    try:
        payload = C.read_json(args.results)
    except (OSError, ValueError) as e:
        print(f"! {args.results}: {e}", file=sys.stderr)
        return 1

    results = payload.get("results")
    if results is None:
        print(f"! {args.results}: no 'results' key — is this a run_backtest.py payload?",
              file=sys.stderr)
        return 1

    if args.format == "text":
        for m in results:
            print_result_row(m)
        print_backtest_summary(results)
        return 0

    md = render_markdown(payload)

    ok = [r for r in results if "error" not in r]
    intervals = {r.get("interval") for r in ok if r.get("interval")}
    tag = intervals.pop() if len(intervals) == 1 else "backtest"
    stamp = dt.date.today().isoformat()
    out = args.out or f"output/backtest_{tag}_{stamp}.md"

    path = C.write_text(out, md)
    print(f"report -> {path}", file=sys.stderr)
    if args.stdout:
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
