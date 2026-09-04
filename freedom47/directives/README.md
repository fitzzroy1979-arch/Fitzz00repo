# Directives index

| Directive | Replaces (00fitzz.py mode) | Primary scripts |
|---|---|---|
| research_brief.md | single-symbol / `--watchlist` brief | fetch_prices, fetch_analyst_views, fetch_youtube_metadata, fact_check_claims, synthesize_brief, render_brief |
| source_credibility.md | (shared rules, no mode) | used by fetch_analyst_views + fact_check_claims |
| backtest.md | `--backtest --interval --period` | fetch_prices, run_backtest, render_backtest_report |
| paper_trade.md | `--trade`, `--portfolio`, `--reset-portfolio` | propose_trade, execute_paper_trade, show_portfolio |
| historical_simulation.md | `--simulate --days --starting-cash` | fetch_prices, run_simulation |
| discover_projects.md | `--discover` | scan_launch_platforms, score_project_credibility |
| scheduled_watchlist_run.md | scheduler mode | run_directive (chains research_brief) + notify |
| dashboard.md | `streamlit run 00fitzz.py` | dashboard.py (reads output/ + state/, no logic of its own) |
| add_webhook.md | (new) | webhooks.json, webhook_server.py |
