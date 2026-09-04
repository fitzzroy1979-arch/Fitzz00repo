# Directive: Backtest

## Goal
Compare the tool's quantitative strategies against buy-and-hold on real historical prices for one symbol. This tests technical signals only — it does not and cannot backtest AI-generated analyst commentary (produced fresh each run, no historical archive).

## Inputs
- `symbol`, `interval` (one of 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1wk), `period` (optional — auto-clamped per interval, see table)

## Strategies (7)
buy-and-hold, SMA crossover, RSI mean-reversion, MACD crossover (12/26/9), Bollinger Bands mean-reversion, Donchian channel breakout, Fibonacci retracement (swing-structure pullback into the 50–61.8% zone; exit at swing high or below 78.6%)

## Metrics
total return, Sharpe, Sortino, Calmar, max drawdown, win rate, profit factor — annualized with the correct bars-per-year for the interval

## Steps
1. `execution/fetch_prices.py --symbol X --interval I --period P --out .tmp/prices_X_I.json`
2. `execution/run_backtest.py --in .tmp/prices_X_I.json --out .tmp/backtest_X_I.json`
3. `execution/render_backtest_report.py --in .tmp/backtest_X_I.json --out output/backtests/<date>_X_I.md`

## Known constraints (Yahoo Finance)
| interval | max history | default period |
|---|---|---|
| 1m | ~7d | 7d |
| 5m/15m/30m | ~60d | 60d |
| 1h | ~730d | 730d |
| 4h | none native — built by resampling 1h (OHLC aggregated) | 730d |
| 1d/1wk | effectively unlimited | 5y |

## Framing rule
There is no universally "best" strategy; results depend on regime (trending vs. choppy). The report compares all strategies side by side and never declares a winner in advance.
