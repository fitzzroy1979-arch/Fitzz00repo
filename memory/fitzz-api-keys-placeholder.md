---
name: fitzz-api-keys-placeholder
description: The LLM API keys in ~/.zshrc are PASTE_YOUR_..._HERE placeholders, and .zshrc isn't sourced non-interactively
metadata:
  type: project
---

Two gaps block the fitzz `--learn` / `--research` bots (confirmed 2026-08-28):

1. `~/.zshrc` exports `GEMINI_API_KEY` and `PERPLEXITY_API_KEY`, but both are
   literal `PASTE_YOUR_..._HERE` placeholders — Gemini returns HTTP 400
   "Please pass a valid API key", Perplexity returns HTTP 401. `ANTHROPIC_API_KEY`
   and `TOGETHER_API_KEY` are not set at all.
2. Keys live in `.zshrc`, which non-interactive shells do NOT source. So even
   once real keys are pasted in, scripted/scheduled runs won't see them —
   those belong in `~/.zprofile` or a `.env` the tool loads.

`--backtest` and `--simulate` are unaffected; they're TradingView-data-only.

**Why:** The bots fail with an API error that looks like a code bug but is purely
a credentials-config issue.
**How to apply:** Before debugging a `--learn`/`--research` failure, check the key
shape first. Only the user can supply real keys. See [[tradingview-mcp-install]].
