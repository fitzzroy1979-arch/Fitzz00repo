#!/usr/bin/env python3
"""Provider calls for the two scripts that use an LLM. Import-only by default.

Wraps the four providers the monolith supports, copied verbatim:

    claude      Anthropic API via the official SDK   ANTHROPIC_API_KEY
    hermes      Together's OpenAI-compatible endpoint TOGETHER_API_KEY
    gemini      Google AI Studio (free tier)          GEMINI_API_KEY
    perplexity  Sonar, live web search + citations    PERPLEXITY_API_KEY

Used by research_brief.py (Perplexity) and tune_parameters.py (any of the
four). Nothing here is called during a backtest, simulation or render.

**Every function in this module spends tokens when it succeeds.** Importing it
does not; only calling `call_*` does. The `--check` CLI below reports which
providers are configured *without* making a request:

    python execution/llm_client.py --check

Model defaults come from .env (`ANTHROPIC_MODEL`), so swapping models is a
one-line config change rather than a code edit.
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

import _common as C


# --------------------------------------------------------------------------- #
# Endpoints + defaults -- moved verbatim from fitzz/trading.py (L95-107)
# --------------------------------------------------------------------------- #

TOGETHER_URL = "https://api.together.xyz/v1/chat/completions"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
PERPLEXITY_URL = "https://api.perplexity.ai/chat/completions"

DEFAULT_LEARN_MODELS = {
    "hermes": "NousResearch/Hermes-3-Llama-3.1-70B",
    "claude": "claude-opus-5",
    "perplexity": "sonar",
    "gemini": "gemini-2.5-flash",
}
DEFAULT_RESEARCH_MODEL = "sonar-pro"

# Which env var each provider authenticates with, for --check and for error
# messages. _call_claude also accepts ANTHROPIC_AUTH_TOKEN.
PROVIDER_KEYS = {
    "claude": "ANTHROPIC_API_KEY",
    "hermes": "TOGETHER_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "perplexity": "PERPLEXITY_API_KEY",
}


class LearnError(RuntimeError):
    """Raised when the tuning LLM can't be reached or returns junk."""


def default_model(provider):
    """Model for `provider`, letting .env override the built-in default.

    ANTHROPIC_MODEL in .env drives the claude provider, per CLAUDE.md's
    'a model swap is a one-line change'.
    """
    if provider == "claude":
        return C.env("ANTHROPIC_MODEL") or DEFAULT_LEARN_MODELS["claude"]
    return DEFAULT_LEARN_MODELS[provider]


# --------------------------------------------------------------------------- #
# Provider calls -- moved verbatim from fitzz/trading.py (L741-894)
# --------------------------------------------------------------------------- #

def _extract_json(text):
    """Pull the first JSON object out of a model response."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    raise LearnError(f"Model did not return JSON. Got: {text[:200]!r}")


def _call_claude(model, system, user):
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        raise LearnError("ANTHROPIC_API_KEY is not set (get one at console.anthropic.com).")
    try:
        import anthropic
    except ImportError:
        raise LearnError("The 'anthropic' package is not installed. Run: pip install -r requirements.txt")
    try:
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=model,
            # Claude Opus 5 (the default) runs adaptive thinking on by default, and
            # those thinking tokens share this budget with the answer. Keep it roomy
            # so a longer chain of thought can't truncate the small JSON that follows.
            max_tokens=8000,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
    except Exception as e:  # SDK/network/auth errors -> a clean message
        raise LearnError(f"Anthropic API call failed: {e}")
    if getattr(resp, "stop_reason", None) == "max_tokens":
        raise LearnError(
            "Anthropic response hit the max_tokens cap before finishing (thinking "
            "likely consumed the budget). Retry, or raise max_tokens in _call_claude."
        )
    return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")


def _call_hermes(model, system, user):
    api_key = os.environ.get("TOGETHER_API_KEY")
    if not api_key:
        raise LearnError("TOGETHER_API_KEY is not set (get one at together.ai), or use "
                        "--learn-provider claude.")
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": 1024,
        "temperature": 0.3,
        "response_format": {"type": "json_object"},
    }).encode()
    req = urllib.request.Request(
        TOGETHER_URL, data=body, method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:200]
        raise LearnError(f"Together API HTTP {e.code}: {detail}")
    except urllib.error.URLError as e:
        raise LearnError(f"Together API unreachable: {e.reason}")
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        raise LearnError(f"Unexpected Together response: {json.dumps(data)[:200]}")


def _call_gemini(model, system, user):
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise LearnError("GEMINI_API_KEY is not set (free at aistudio.google.com), "
                         "or use a different --learn-provider.")
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": 1024,
        "temperature": 0.3,
        "response_format": {"type": "json_object"},
    }).encode()
    req = urllib.request.Request(
        GEMINI_URL, data=body, method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:200]
        raise LearnError(f"Gemini API HTTP {e.code}: {detail}")
    except urllib.error.URLError as e:
        raise LearnError(f"Gemini API unreachable: {e.reason}")
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        raise LearnError(f"Unexpected Gemini response: {json.dumps(data)[:200]}")


def _call_perplexity(model, system, user, json_mode=False, temperature=0.2):
    """Call Perplexity's OpenAI-compatible Sonar endpoint.

    Returns (content, citations). Sonar models search the live web, so
    `citations` is a list of source URLs backing the answer (may be empty).
    """
    api_key = os.environ.get("PERPLEXITY_API_KEY")
    if not api_key:
        raise LearnError("PERPLEXITY_API_KEY is not set (get one at "
                         "perplexity.ai/settings/api).")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    req = urllib.request.Request(
        PERPLEXITY_URL, data=json.dumps(payload).encode(), method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        raise LearnError(f"Perplexity API HTTP {e.code}: {detail}")
    except urllib.error.URLError as e:
        raise LearnError(f"Perplexity API unreachable: {e.reason}")
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        raise LearnError(f"Unexpected Perplexity response: {json.dumps(data)[:200]}")
    # Perplexity returns sources either as top-level `citations` or, on newer
    # responses, as `search_results` objects with a `url` field.
    citations = data.get("citations") or []
    if not citations:
        citations = [s.get("url") for s in data.get("search_results", []) if s.get("url")]
    return content, citations


# --------------------------------------------------------------------------- #
# Dispatch
# --------------------------------------------------------------------------- #

def call(provider, system, user, model=None, json_mode=False, temperature=0.2):
    """Call `provider`. Returns (text, citations) -- citations only from Sonar.

    Spends tokens. Callers must have the user's go-ahead for the run.
    """
    if provider not in DEFAULT_LEARN_MODELS:
        raise LearnError(f"Unknown provider {provider!r}. "
                         f"One of: {', '.join(sorted(DEFAULT_LEARN_MODELS))}")
    C.env("ANTHROPIC_MODEL")  # force .env to load before reading os.environ keys
    model = model or default_model(provider)
    if provider == "claude":
        return _call_claude(model, system, user), []
    if provider == "hermes":
        return _call_hermes(model, system, user), []
    if provider == "gemini":
        return _call_gemini(model, system, user), []
    return _call_perplexity(model, system, user, json_mode=json_mode,
                            temperature=temperature)


def configured(provider):
    """True if `provider` has a key set. Makes no request."""
    C.env("ANTHROPIC_MODEL")  # ensure .env is loaded
    if provider == "claude":
        return bool(os.environ.get("ANTHROPIC_API_KEY")
                    or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
    if provider == "gemini":
        return bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    return bool(os.environ.get(PROVIDER_KEYS[provider]))


# --------------------------------------------------------------------------- #
# CLI -- reports configuration only; never makes a request
# --------------------------------------------------------------------------- #

def build_parser():
    p = argparse.ArgumentParser(
        description="Report which LLM providers are configured. Makes no API call.")
    p.add_argument("--check", action="store_true",
                   help="List each provider, its key variable, and its model.")
    p.add_argument("--json", action="store_true", help="Emit JSON.")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if not args.check:
        build_parser().print_help()
        return 2

    rows = []
    for provider in sorted(DEFAULT_LEARN_MODELS):
        ok = configured(provider)
        rows.append({
            "provider": provider,
            "key_var": PROVIDER_KEYS[provider],
            "configured": ok,
            "model": default_model(provider),
        })

    try:
        import anthropic  # noqa: F401
        sdk = True
    except ImportError:
        sdk = False

    if args.json:
        print(json.dumps({"providers": rows, "anthropic_sdk_installed": sdk}, indent=2))
        return 0

    print("Provider configuration (no requests made):\n")
    for r in rows:
        mark = "ok " if r["configured"] else "-- "
        print(f"  {mark} {r['provider']:<11} {r['key_var']:<20} model {r['model']}")
    print(f"\n  anthropic SDK installed: {'yes' if sdk else 'no'}")
    ready = [r["provider"] for r in rows if r["configured"]]
    print(f"  usable now: {', '.join(ready) if ready else 'none — no API keys set'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
