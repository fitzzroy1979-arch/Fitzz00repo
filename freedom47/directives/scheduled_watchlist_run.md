# Directive: Scheduled watchlist run

## Goal
Run `research_brief.md` for the whole watchlist on a schedule and deliver the result somewhere the user reads it.

## Trigger options
- Local: cron / Task Scheduler calling `python execution/run_directive.py research_brief --symbols watchlist`
- Cloud: a webhook (see `add_webhook.md`) hit by a scheduler

## Steps
1. `execution/run_directive.py research_brief --symbols watchlist`
2. `execution/notify.py --file output/briefs/<date>_index.md --email $NOTIFY_EMAIL` (and/or `--sheet`)

## Rules
- Scheduled runs are read-only research. They must never call `execute_paper_trade.py`.
- Step 1 spends API tokens per symbol; if a run fails midway, report which symbols completed rather than re-running everything automatically.
