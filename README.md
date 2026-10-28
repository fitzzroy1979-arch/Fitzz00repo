# fitzz

A combined toolkit for TradingView-data-backed quant work. Four tools, one CLI.

| Tool | Module | What it does |
|------|--------|--------------|
| **trade** | `fitzz.trading` | The 00fitzz trading CLI — backtest, LLM parameter learning, Perplexity research, walk-forward paper simulation, and paper trade/futures stubs. Reads OHLCV/watchlist data from a running TradingView Desktop via the local `tradingview-mcp` bridge. |
| **sweep** | `fitzz.sweep` | Sweep-significance analysis — prices the selection bias of a parameter sweep's best config with White's Reality Check and Hansen's SPA p-values. |
| **feed** | `fitzz.feed` | Live crypto prices from CoinMarketCap's WebSocket. |
| **flows** | `fitzz.flows` | Public money flow — CFTC Commitments of Traders positioning and SEC EDGAR full-text filing search, plus a curated corporate-event study. |

## What this repo concluded

**No tradable edge was found.** `FINDINGS.md` is the write-up: roughly 245
significance sweeps over five strategy families, eleven symbols and three
timeframes, plus both public-data feeds, all corrected for the search that
found them. Read it before running a sweep and reading a low p-value as news.

It is also a log of eight data bugs, every one of the same shape — a read that
was short, stale or another symbol's, passing itself off as complete. That
section is the most reusable thing here.

## Layout

```
.
├── fitzz/                 # the combined package
│   ├── cli.py             # unified dispatcher (trade | sweep | feed | flows)
│   ├── trading.py         # the trading CLI (was 00fitzz.py)
│   ├── sweep.py           # sweep significance (was sweep_significance.py)
│   ├── feed.py            # CoinMarketCap websocket stream
│   ├── flows.py           # CFTC / SEC EDGAR / corporate events
│   ├── journal.py         # per-trade entry readings, in- and out-of-sample
│   ├── fm_family.py       # strategy families, each a --strategy plugin:
│   ├── mr_family.py       #   follow_money, mean_revert, confluence,
│   ├── conf_family.py     #   and the same five crossed with a swept
│   └── gated_family.py    #   volatility-regime entry gate
├── run_sweep_4h.py        # the research driver — every family x symbol, side by side
├── studies/               # one-off analyses backing specific FINDINGS claims
├── FINDINGS.md            # results, methodology, and the bug log
├── 00fitzz.py             # back-compat shim → fitzz.trading
├── sweep_significance.py  # back-compat shim → fitzz.sweep
├── freedom47/             # earlier directive-driven agent project
└── tradingview-mcp/       # the data bridge (separate git repo; not committed here)
```

## Usage

Unified CLI (no install needed — run from the repo root):

```bash
python3 -m fitzz trade --simulate --watchlist --days 7 --interval 1h
python3 -m fitzz sweep --csv prices.csv --family ma_cross --objective return
python3 -m fitzz flows --cot BITCOIN --since 2024-01-01
python3 -m fitzz feed --symbols BTC,ETH
```

Or install the `fitzz` console script:

```bash
pip install -e .
fitzz trade --backtest --symbol BTCUSD --period 1y --interval 1d
fitzz sweep --csv prices.csv --family ma_cross
```

The original entry points still work unchanged:

```bash
python3 00fitzz.py --simulate --watchlist --days 7 --interval 1h
python3 sweep_significance.py --csv prices.csv --family ma_cross
```

Each tool keeps its own flags — run `python3 -m fitzz <tool> --help` for the
full option list.

## Running the research sweep

`sweep` scores one grid at a time. `run_sweep_4h.py` is the driver that runs
every family against every symbol and prints the corrected p-values side by
side:

```bash
python3 run_sweep_4h.py                     # the focus symbols, 4h
python3 run_sweep_4h.py --interval 1h --shorts
python3 run_sweep_4h.py --vol-gate          # families crossed with the swept gate
python3 run_sweep_4h.py --journal           # per-trade entry readings
```

`sweep` itself ships two built-in families (`ma_cross`, `breakout`); the rest
are `--strategy FILE.py:FUNC` plugins, which is how the family modules above
are loaded.

Bars are cached between runs, so repeat runs do not re-hit the bridge. A
series that comes back shorter than requested is re-read once rather than
cached, because a short read and a young asset look identical from the
outside — see the bug log.

## Data sources

The `trade` tool and the research driver need **TradingView Desktop** running
with the Chrome DevTools port enabled, plus the sibling `tradingview-mcp`
checkout:

```bash
/Applications/TradingView.app/Contents/MacOS/TradingView --remote-debugging-port=9222
```

Give the app a few seconds to warm up before the first data read.

`flows` needs no bridge — CFTC Socrata and SEC EDGAR are public HTTP. EDGAR
requires a User-Agent and returns 100 hits per response, so `flows` pages
through the full result set and reports whether it saw everything.

## Dedicated agents

Per-domain Claude Code subagents live in `.claude/agents/` — a trading agent, a
sweep/stats agent, and a TradingView-bridge agent — so work can be routed to a
specialist scoped to just that part of the codebase.
