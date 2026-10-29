---
name: tradingview-mcp-install
description: TradingView MCP server install state — installed but pending TradingView Desktop + restart
metadata: 
  node_type: memory
  type: project
  originSessionId: f48fca54-aa36-4352-8327-5932bdc7f573
  modified: 2026-08-09T08:44:50.366Z
---

The `tradesdontlie/tradingview-mcp` server (MCP bridge to TradingView Desktop via Chrome DevTools Protocol) at `~/Desktop/AI/tradingview-mcp`. **Confirmed working end-to-end 2026-08-09.**

To use: TradingView Desktop is installed at `/Applications/TradingView.app`. Launch with the debug port before running anything data-backed:
`/Applications/TradingView.app/Contents/MacOS/TradingView --remote-debugging-port=9222`
Port 9222 comes up fast, but the app needs a few seconds to warm up before charts read reliably.

The sibling CLI `00fitzz.py` (a trading CLI: --backtest/--learn/--research/--simulate/--trade) drives the bridge via `node tradingview-mcp/src/cli/index.js`. Run it with `python3` (plain `python` is not on PATH). Node is under nvm — see [[node-nvm-setup]].

**Cold-start gotcha (fixed 2026-08-28):** `load_bars` used to fire `set_symbol`,
sleep a fixed 1.5s, then read `get_ohlcv` without checking the chart had actually
repainted — so a fast watchlist loop silently returned the *previous* symbol's
bars, and unrelated instruments (e.g. TVC:USOIL and BYBIT:HBARUSDT) reported
identical returns. `fitzz/trading.py` now polls `tv symbol` until the chart
confirms the requested ticker (comparing only the part after the exchange prefix,
since `TSX:NVDA` comes back as `TSX_DLY:NVDA`) and rejects a bar read whose
fingerprint matches the previous symbol's. Raise `--settle` if confirmation times
out on a cold app.

Still true: `get_watchlist` reads visible DOM rows, so it can miss unscrolled
symbols. And `--days` is measured in bars, not calendar days, so a stock's
"7 days" of hourly bars spans ~a month of trading sessions.
