"""Negative-news veto: a bounded, logged risk control for HELD tokens.

At each rebalance, for the tokens the strategy actually holds, pull fresh
social/news (Monolit ``search_twitter``) and score it with MiniMax M3 (0G router).
If a held token has a FRESH SEVERE negative event (hack / exploit / depeg /
delisting / regulatory action / rug), drop that name to cash for the cycle by
adding it to the strategy ``vetoes`` set.

Design contract (mirrors the existing security/flow overlay in ``strategy.py``):
  - BEST-EFFORT: any failure (network, LLM, parse) returns no veto. It must
    NEVER block or delay the core ensemble decision.
  - BOUNDED: only HELD names are scored (<= a handful per cycle), cached with a
    short TTL so we don't re-pay the LLM/search cost every hour.
  - LOGGED: returns structured reasons so every veto is auditable in the
    decision record.
  - ASYMMETRIC: opportunity cost of a false veto ~= one cycle in cash for one
    name (~0.08% of book + ~30bps round trip); avoided loss when it fires on a
    staged catastrophe (delisting / slow exploit) is up to ~-60% of a held
    position. Rare-fire (held-universe base rate ~0.18 severe crashes / 7d), big
    payoff-when-fired.

Validated mechanism (see docs/hypotheses/negative-news-veto.md): the STG
Coinbase-delisting crash (-64% peak-to-trough over ~18h) is correctly flagged by
this exact pipeline (search_twitter -> CoinDesk delisting post -> M3
{delisting, severity 8}); a 4h-cadence veto avoids ~the back -59% of the slide.
Gap-down crashes (ZEC, SAHARA) are only partly dodged, but the veto never makes
things worse and still avoids the back half.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_ROUTER = "https://router-api.0g.ai/v1/chat/completions"
_MODEL = "minimax-m3"

# Severity at/above this drops the held name to cash for the cycle.
SEVERITY_DROP = 6

_SYS = (
    "You are a risk screen for a spot crypto trading agent. Given recent "
    "social/news for a token the agent currently HOLDS, decide if there is a "
    "FRESH SEVERE NEGATIVE event: hack, exploit, depeg, delisting, regulatory "
    "action/enforcement, or rug. Ignore ordinary price chatter, bullish posts, "
    "trader opinions, and stale (>72h old) events. Respond ONLY with compact "
    'JSON: {"negative_event": bool, "category": str, "severity": int 0-10, '
    '"reason": str}. severity>=6 means the agent should drop the token to cash.'
)


@dataclass
class VetoConfig:
    severity_drop: int = SEVERITY_DROP
    ttl_h: float = 4.0                       # re-screen a held name at most this often
    max_checks: int = 8                      # only the concentrated held sleeve is scored
    request_timeout: int = 90
    min_likes: int = 5                       # filter social junk before the LLM sees it
    cache_path: Path = field(
        default_factory=lambda: Path(__file__).parent / "data" / "runtime" / "news_veto.json"
    )


def _strip_think(text: str) -> str:
    if "</think>" in text:
        text = text.split("</think>", 1)[1]
    return text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()


def _score_event(token: str, social_text: str, cfg: VetoConfig) -> dict[str, Any] | None:
    """Score one token's fresh social/news with MiniMax M3. None on any failure."""
    key = os.environ.get("MINIMAX_M3_API_KEY")
    if not key or not social_text.strip():
        return None
    body = {
        "model": _MODEL,
        "max_tokens": 2000,          # M3 emits a <think> block; needs headroom
        "temperature": 0,
        "messages": [
            {"role": "system", "content": _SYS},
            {"role": "user", "content": f"Token: {token}. Recent posts:\n{social_text[:4000]}"},
        ],
    }
    req = urllib.request.Request(
        _ROUTER,
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=cfg.request_timeout) as r:
            content = json.loads(r.read())["choices"][0]["message"]["content"]
        return json.loads(_strip_think(content))
    except Exception:
        return None


def _fresh_social(client, token: str, cfg: VetoConfig) -> str:
    """Pull fresh tweets for a token via Monolit search_twitter; '' on failure."""
    try:
        res = client.call_tool(
            "search_twitter",
            {"query": f"${token} hack exploit depeg delisting rug regulatory",
             "sort": "Latest", "min_likes": cfg.min_likes},
        )
    except Exception:
        return ""
    # The tool returns a human-readable summary in 'content' plus an artifact; the
    # summary already contains the top tweet texts, which is enough to score on.
    if isinstance(res, dict):
        return str(res.get("summary") or res.get("content") or "")
    return str(res)


def negative_vetoes(client, held_symbols: list[str], cfg: VetoConfig | None = None
                    ) -> tuple[set[str], list[dict]]:
    """Return (vetoed_symbols, audit_records) for the currently-held names.

    Best-effort and bounded: scores at most ``cfg.max_checks`` held names, caches
    per-symbol verdicts for ``cfg.ttl_h`` hours, and swallows every error so the
    core decision is never blocked. ``audit_records`` is for the decision log.
    """
    cfg = cfg or VetoConfig()
    now = time.time()
    cache: dict[str, Any] = {}
    if cfg.cache_path.exists():
        try:
            cache = json.loads(cfg.cache_path.read_text())
        except Exception:
            cache = {}

    vetoed: set[str] = set()
    audit: list[dict] = []
    for sym in held_symbols[: cfg.max_checks]:
        ent = cache.get(sym)
        if ent and now - ent.get("ts", 0) < cfg.ttl_h * 3600:
            verdict = ent.get("verdict")
        else:
            social = _fresh_social(client, sym, cfg)
            verdict = _score_event(sym, social, cfg) if social else None
            cache[sym] = {"ts": now, "verdict": verdict}
        if not verdict:
            continue
        sev = int(verdict.get("severity", 0) or 0)
        if verdict.get("negative_event") and sev >= cfg.severity_drop:
            vetoed.add(sym)
            audit.append({"symbol": sym, "severity": sev,
                          "category": verdict.get("category"), "reason": verdict.get("reason")})

    try:
        cfg.cache_path.parent.mkdir(parents=True, exist_ok=True)
        cfg.cache_path.write_text(json.dumps(cache, indent=1))
    except Exception:
        pass
    return vetoed, audit
