#!/usr/bin/env python3
"""Provider-agnostic webhook handler. One slug → one directive → scoped tools.

Deploy on any provider that runs a Python HTTP handler. Examples:
  Modal:      modal deploy execution/webhook_server.py     (wrap `handle` with @app.function + @modal.web_endpoint)
  Cloud Run:  gcloud run deploy --source . (serve `handle` behind Flask/FastAPI)
  Lambda:     export `lambda_handler(event, ctx)` calling `handle(event["queryStringParameters"], event["headers"])`

Endpoints (contract):
  GET /list      → slugs in webhooks.json
  GET /directive?slug=<slug>   header X-Webhook-Secret → runs the chain, posts result to Slack if configured
"""
import json, os, subprocess, sys, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEBHOOKS = json.loads((ROOT / "execution" / "webhooks.json").read_text())
FORBIDDEN_TOOLS = {"execute_paper_trade"}  # approval can't happen over HTTP


def slack(msg):
    url = os.environ.get("SLACK_WEBHOOK_URL")
    if url:
        req = urllib.request.Request(url, json.dumps({"text": msg}).encode(), {"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)


def handle(query: dict, headers: dict):
    slug = (query or {}).get("slug")
    if slug not in WEBHOOKS:
        return 404, {"error": "unknown slug", "known": list(WEBHOOKS)}
    spec = WEBHOOKS[slug]
    if headers.get("X-Webhook-Secret") != os.environ.get(spec["auth"]):
        return 401, {"error": "bad secret"}
    if FORBIDDEN_TOOLS & set(spec["tools"]):
        return 403, {"error": "paper trading is not webhook-executable"}
    directive = Path(spec["directive"]).stem
    slack(f":hourglass: webhook `{slug}` → `{directive}` starting")
    r = subprocess.run([sys.executable, str(ROOT / "execution" / "run_directive.py"), directive],
                       capture_output=True, text=True)
    status = "done" if r.returncode == 0 else f"FAILED ({r.returncode})"
    slack(f":white_check_mark: `{slug}` {status}\n```{(r.stdout + r.stderr)[-1500:]}```")
    return (200 if r.returncode == 0 else 500), {"slug": slug, "status": status, "log": r.stdout[-4000:]}


def list_webhooks():
    return 200, {s: {"directive": v["directive"], "tools": v["tools"]} for s, v in WEBHOOKS.items()}
