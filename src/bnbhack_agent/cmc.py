"""CoinMarketCap Agent Hub — live market signals.

Adds partner (CMC) signals to the agent: Fear & Greed, global derivatives, and BTC
dominance. These are *current-snapshot* market-regime reads (not historically
backtestable via the free tier), so they enter as a **bounded, logged** live overlay
that confirms/tempers the validated price-regime decision — it can trim exposure in
euphoric conditions but cannot override the core strategy or tank returns.

Access: CMC Pro API key in env `CMC_PRO_API_KEY` (REST host pro-api.coinmarketcap.com).
The same data is exposed via the CMC Agent Hub MCP (`mcp.coinmarketcap.com/mcp`) and
keyless x402 — REST is used here for reliability. Degrades gracefully with no key.
"""
from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass

HOST = "https://pro-api.coinmarketcap.com"


@dataclass
class CMCClient:
    api_key: str | None = None
    timeout: int = 15

    def __post_init__(self):
        self.api_key = self.api_key or os.environ.get("CMC_PRO_API_KEY") or os.environ.get("CMC_API_KEY")

    def available(self) -> bool:
        return bool(self.api_key)

    def _get(self, path: str) -> dict:
        req = urllib.request.Request(
            HOST + path,
            headers={"X-CMC_PRO_API_KEY": self.api_key or "", "Accept": "application/json",
                     "User-Agent": "bnbhack-trading-agent/0.1"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read().decode())

    def fear_greed(self) -> int | None:
        """Current CMC Fear & Greed index (0-100), or None if unavailable."""
        try:
            d = self._get("/v3/fear-and-greed/latest")
            return int(d["data"]["value"])
        except Exception:
            return None

    def global_metrics(self) -> dict:
        """BTC dominance + total market cap snapshot, or {} if unavailable."""
        try:
            d = self._get("/v1/global-metrics/quotes/latest")["data"]
            return {"btc_dominance": d.get("btc_dominance"),
                    "total_mcap": d.get("quote", {}).get("USD", {}).get("total_market_cap")}
        except Exception:
            return {}

    def derivatives(self) -> dict:
        """Global derivatives snapshot (OI, volume) when the plan exposes it, else {}."""
        try:
            d = self._get("/v1/global-metrics/quotes/latest")["data"]
            return {"derivatives_volume_24h": d.get("derivatives_volume_24h"),
                    "derivatives_24h_percentage_change": d.get("derivatives_24h_percentage_change")}
        except Exception:
            return {}


def regime_signal(client: CMCClient | None) -> dict:
    """A bounded live-regime overlay from CMC. Returns fear&greed, dominance, and a
    `caution_factor` in [0.80, 1.0] that trims exposure as the market gets euphoric
    (Fear & Greed is mean-reverting at extremes). Neutral (1.0) when no key/data."""
    if client is None or not client.available():
        return {"fng": None, "caution_factor": 1.0, "source": "unavailable"}
    fng = client.fear_greed()
    gm = client.global_metrics()
    factor = 1.0
    note = "neutral"
    if fng is not None:
        if fng >= 80:        # extreme greed -> tops cluster here; trim
            factor, note = 0.80, "extreme_greed_trim"
        elif fng >= 70:
            factor, note = 0.90, "greed_trim"
        # extreme fear: do NOT add risk here (regime gate handles risk-off); stay neutral
    return {"fng": fng, "btc_dominance": gm.get("btc_dominance"), "caution_factor": factor, "source": note}
