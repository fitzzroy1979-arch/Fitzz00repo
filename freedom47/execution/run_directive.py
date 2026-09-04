#!/usr/bin/env python3
"""Orchestration entry point: run a directive's script chain by name.

Usage:
    python execution/run_directive.py research_brief --symbols watchlist
    python execution/run_directive.py backtest --symbol XRP-USD --interval 4h

This file holds the *chains* only — the order in which execution scripts run for each
directive, mirroring the Steps section of directives/<name>.md. It contains no market
logic. If a directive's steps change, update the directive first, then this map.
"""
import argparse, os, subprocess, sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXE = ROOT / "execution"
TMP = ROOT / ".tmp"
OUT = ROOT / "output"


def _load_env():
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.strip() and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def run(script, *args):
    cmd = [sys.executable, str(EXE / script), *map(str, args)]
    print("→", " ".join(cmd[1:]), flush=True)
    r = subprocess.run(cmd)
    if r.returncode != 0:
        sys.exit(f"{script} failed (exit {r.returncode}) — see stack trace above")


def symbols_from(arg):
    if arg == "watchlist":
        return [s.strip() for s in os.environ.get("WATCHLIST", "").split(",") if s.strip()]
    return [arg]


def research_brief(a):
    today = date.today().isoformat()
    (OUT / "briefs").mkdir(parents=True, exist_ok=True)
    for s in symbols_from(a.symbols):
        run("fetch_prices.py", "--symbol", s, "--interval", a.interval, "--period", "6mo", "--out", TMP / f"prices_{s}.json")
        run("fetch_analyst_views.py", "--symbol", s, "--out", TMP / f"views_{s}.json")
        run("fetch_youtube_metadata.py", "--symbol", s, "--channels", "@AlexanderELorenzo,@24hrsCrypto", "--out", TMP / f"yt_{s}.json")
        run("fact_check_claims.py", "--in", TMP / f"views_{s}.json", "--out", TMP / f"checked_{s}.json")
        run("synthesize_brief.py", "--prices", TMP / f"prices_{s}.json", "--views", TMP / f"checked_{s}.json",
            "--yt", TMP / f"yt_{s}.json", "--out", TMP / f"brief_{s}.json")
        run("render_brief.py", "--in", TMP / f"brief_{s}.json", "--out", OUT / "briefs" / f"{today}_{s}.md")


def backtest(a):
    today = date.today().isoformat()
    (OUT / "backtests").mkdir(parents=True, exist_ok=True)
    p = TMP / f"prices_{a.symbol}_{a.interval}.json"
    args = ["--symbol", a.symbol, "--interval", a.interval, "--out", p]
    if a.period:
        args += ["--period", a.period]
    run("fetch_prices.py", *args)
    run("run_backtest.py", "--in", p, "--out", TMP / f"backtest_{a.symbol}_{a.interval}.json")
    run("render_backtest_report.py", "--in", TMP / f"backtest_{a.symbol}_{a.interval}.json",
        "--out", OUT / "backtests" / f"{today}_{a.symbol}_{a.interval}.md")


def discover(a):
    today = date.today().isoformat()
    (OUT / "discover").mkdir(parents=True, exist_ok=True)
    run("scan_launch_platforms.py", "--out", TMP / "discover_raw.json")
    run("score_project_credibility.py", "--in", TMP / "discover_raw.json", "--out", OUT / "discover" / f"{today}.md")


def simulate(a):
    today = date.today().isoformat()
    (OUT / "simulations").mkdir(parents=True, exist_ok=True)
    for s in symbols_from(a.symbols):
        run("fetch_prices.py", "--symbol", s, "--interval", "1d", "--period", f"{a.days}d", "--out", TMP / f"sim_prices_{s}.json")
    run("run_simulation.py", "--prices", TMP, "--days", a.days, "--starting-cash", a.starting_cash,
        "--out", OUT / "simulations" / f"{today}.md")


# NOTE: paper_trade is intentionally absent. It needs an interactive approval prompt,
# so it is run directly: propose_trade.py → (user says y) → execute_paper_trade.py

CHAINS = {"research_brief": research_brief, "backtest": backtest, "discover": discover, "simulate": simulate}

if __name__ == "__main__":
    _load_env()
    TMP.mkdir(exist_ok=True)
    ap = argparse.ArgumentParser()
    ap.add_argument("directive", choices=CHAINS)
    ap.add_argument("--symbols", default="watchlist")
    ap.add_argument("--symbol", default="XRP-USD")
    ap.add_argument("--interval", default="1d")
    ap.add_argument("--period")
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--starting-cash", type=float, default=float(os.environ.get("DEFAULT_STARTING_CASH", 3000)))
    a = ap.parse_args()
    CHAINS[a.directive](a)
