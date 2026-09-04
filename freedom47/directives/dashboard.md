# Directive: Dashboard

## Goal
A Streamlit view over the deliverables and state — it reads, it does not compute.

## Run
`streamlit run execution/dashboard.py`

## Shows
- Latest briefs from `output/briefs/` (per symbol, with the Agent 47 header and SVG badge avatar)
- Backtest reports from `output/backtests/`
- Paper portfolio from `state/portfolio.json`
- Read-aloud button (browser text-to-speech) for the selected brief

## Rule
The dashboard never fetches data or calls the Claude API itself. To refresh, it triggers `run_directive.py` and re-reads the files. This keeps every number on screen traceable to a file produced by a deterministic script.
