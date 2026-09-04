# Directive: Add a webhook

## Goal
Expose one directive as an HTTP endpoint with scoped tools. Provider-agnostic: the reference is Modal, but Cloud Run, Lambda, Railway, etc. all fit the same contract.

## Contract (`execution/webhooks.json`)
```json
{
  "slug": {
    "directive": "directives/<name>.md",
    "tools": ["run_directive", "send_email"],
    "auth": "WEBHOOK_SECRET"
  }
}
```

## Steps
1. Write or pick the directive in `directives/`
2. Add the slug entry to `execution/webhooks.json` — list only the tools that directive needs
3. Deploy `execution/webhook_server.py` with your provider (deploy command is documented in the file header per provider)
4. Test: `curl -H "X-Webhook-Secret: $WEBHOOK_SECRET" "<base-url>/directive?slug=<slug>"`
5. Confirm the run streamed to Slack (if `SLACK_WEBHOOK_URL` is set)

## Rules
- One webhook → exactly one directive
- Allowed tools: `run_directive`, `send_email`, `read_sheet`, `update_sheet`
- `execute_paper_trade` is never an allowed tool — approval can't happen over a webhook
- Every endpoint requires the shared secret header
