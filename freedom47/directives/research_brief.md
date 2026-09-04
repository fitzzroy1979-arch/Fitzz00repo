# Directive: Research brief

## Goal
Produce a cited market-research brief for one symbol or the full watchlist, for the user's own manual trading decisions. Output is research, never a recommendation to execute.

## Inputs
- `symbols`: one ticker, or `watchlist` (reads `WATCHLIST` from .env — default XRP, XLM, HBAR, ZAMA)
- `interval` (optional, default `1d`) for the technical snapshot

## Steps
1. `execution/fetch_prices.py --symbol X --interval 1d --period 6mo --out .tmp/prices_X.json`
2. `execution/fetch_analyst_views.py --symbol X --out .tmp/views_X.json` — applies `source_credibility.md`; writes each view with source, URL, date, reasoning excerpt, and a credibility pass/fail with reason
3. `execution/fetch_youtube_metadata.py --symbol X --channels @AlexanderELorenzo,@24hrsCrypto --out .tmp/yt_X.json` — metadata only
4. `execution/fact_check_claims.py --in .tmp/views_X.json --out .tmp/checked_X.json` — tags each claim confirmed/uncertain/contradicted with the checking source
5. `execution/synthesize_brief.py --prices .tmp/prices_X.json --views .tmp/checked_X.json --yt .tmp/yt_X.json --out .tmp/brief_X.json` — the only Claude API call; uses `ANTHROPIC_MODEL`; fixed system prompt, JSON schema output
6. `execution/render_brief.py --in .tmp/brief_X.json --out output/briefs/YYYY-MM-DD_X.md` — header reads "Agent 47"
7. For `watchlist`, loop 1–6 per symbol, then render a combined index.

## Output
`output/briefs/<date>_<symbol>.md` containing: price/technical snapshot, analyst views table (source, view, credibility, fact-check flag), YouTube items (title/date/link), halving context for crypto, Investopedia background where a term needs it, and a sources list.

## Edge cases / learnings
- Step 5 costs API tokens: if it fails, do not retry blindly — ask the user before re-running.
- If fewer than 2 credible analyst views are found, still produce the brief and say so plainly in the header.
- Yahoo tickers for crypto need the `-USD` suffix.
- (Append constraints discovered here.)
