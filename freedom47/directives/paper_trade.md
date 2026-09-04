# Directive: Paper trade (local simulator)

## Goal
Let the user place simulated crypto trades against real prices with realistic costs, with mandatory approval. No exchange connection, no real funds. Crypto only (matches the watchlist). Local simulator was chosen because HBAR/ZAMA aren't reliably supported on broker paper APIs or Binance Testnet.

## Inputs
- `action` (buy/sell), `symbol`, `quantity` or `notional`
- `fee_rate` (default 0.001 = 0.10% on notional), `slippage_bps` (default 5 = 0.05%, always against the trader)

## Steps
1. `execution/propose_trade.py --action buy --symbol XRP-USD --qty 100 --out .tmp/proposal.json` — fetches the live price, applies slippage and fee, checks cash/holdings, prints the full proposal
2. **Show the proposal to the user and get explicit approval.** Proceed only on `y`, or if the user passed `--yes` on this exact invocation.
3. `execution/execute_paper_trade.py --proposal .tmp/proposal.json` — writes to `state/portfolio.json`
4. `execution/show_portfolio.py` — positions, cash, realized/unrealized P&L, P&L% vs `DEFAULT_STARTING_CASH` ($3,000)

Reset: `execution/reset_portfolio.py` (asks for confirmation; starts fresh at $3,000).

## Hard rules
- Approval is never stored, never defaulted, never granted by a webhook or scheduler.
- Reject trades exceeding available cash or holdings — script exits non-zero with the reason.
- Fees and slippage hit the portfolio immediately on execution, before any price movement.

## Future (not built)
A real/live exchange connection is a separate future step requiring a fresh directive and explicit user sign-off.
