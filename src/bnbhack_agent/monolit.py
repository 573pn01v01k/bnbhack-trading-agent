"""Real Monolit MCP client (streamable-HTTP JSON-RPC).

Replaces the v1 placebo `MonolitMCPEnrichmentSource`, which called a tool that
does not exist and silently returned nothing. This client speaks the actual MCP
protocol to `https://mcp.monolit.network/mcp` and exposes typed helpers for the
signals that are our edge: on-chain BSC flow, CEX funding/taker, and TA.

Config via env (never hard-code the key):
    MONOLIT_MCP_URL   (default https://mcp.monolit.network/mcp)
    MONOLIT_API_KEY   (required)

Transport notes: the server returns either application/json or an SSE stream
(text/event-stream) of `data: {...}` lines; both are handled. Monolit tool
results arrive as a JSON string inside result.content[0].text, which we parse.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

DEFAULT_URL = "https://mcp.monolit.network/mcp"
PROTOCOL_VERSION = "2025-06-18"


class MonolitError(RuntimeError):
    pass


def _parse_body(raw: bytes, content_type: str) -> dict[str, Any]:
    """Return the JSON-RPC envelope from a plain-JSON or SSE response body."""
    text = raw.decode("utf-8", errors="replace").strip()
    if "text/event-stream" in content_type or text.startswith("event:") or text.startswith("data:"):
        payload: dict[str, Any] = {}
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                chunk = line[5:].strip()
                if not chunk or chunk == "[DONE]":
                    continue
                try:
                    obj = json.loads(chunk)
                except json.JSONDecodeError:
                    continue
                # last JSON-RPC message with a result/error wins
                if isinstance(obj, dict) and ("result" in obj or "error" in obj or "id" in obj):
                    payload = obj
        return payload
    return json.loads(text) if text else {}


@dataclass
class MonolitClient:
    url: str = field(default_factory=lambda: os.environ.get("MONOLIT_MCP_URL", DEFAULT_URL))
    api_key: str | None = field(default_factory=lambda: os.environ.get("MONOLIT_API_KEY"))
    timeout: int = 120
    max_retries: int = 4
    _session_id: str | None = field(default=None, init=False, repr=False)
    _next_id: int = field(default=0, init=False, repr=False)
    _initialized: bool = field(default=False, init=False, repr=False)

    # ---- transport -----------------------------------------------------
    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise MonolitError("MONOLIT_API_KEY is not set")
        h = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "X-Api-Key": self.api_key,
            "User-Agent": os.environ.get(
                "MONOLIT_USER_AGENT",
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            ),
        }
        if self._session_id:
            h["Mcp-Session-Id"] = self._session_id
        return h

    def _post(self, method: str, params: dict[str, Any] | None, *, is_notification: bool = False) -> dict[str, Any]:
        body: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if not is_notification:
            self._next_id += 1
            body["id"] = self._next_id
        if params is not None:
            body["params"] = params
        payload = json.dumps(body).encode("utf-8")
        last_err: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                request = urllib.request.Request(self.url, data=payload, headers=self._headers(), method="POST")
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    sid = response.headers.get("Mcp-Session-Id") or response.headers.get("mcp-session-id")
                    if sid:
                        self._session_id = sid
                    raw = response.read()
                    ctype = response.headers.get("Content-Type", "")
                if is_notification:
                    return {}
                envelope = _parse_body(raw, ctype)
                if envelope.get("error"):
                    raise MonolitError(f"{method} failed: {envelope['error']}")
                return envelope.get("result", {})
            except (urllib.error.URLError, TimeoutError, MonolitError) as err:
                last_err = err
                msg = str(err)
                # Retry transient cluster/network errors; do not retry auth/4xx.
                http_code = getattr(err, "code", None)
                if http_code is not None and 400 <= http_code < 500 and http_code != 429:
                    raise
                transient = (
                    http_code in (429, 500, 502, 503, 504)
                    or isinstance(err, (TimeoutError,))
                    or any(s in msg for s in ("unavailable", "Max retries", "Internal error", "timed out", "unreachable", "ConnectTimeout"))
                )
                if not transient or attempt == self.max_retries - 1:
                    raise
                time.sleep(min(8, 1.5 * (2 ** attempt)))
        raise MonolitError(f"{method} failed after retries: {last_err}")

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        self._post(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "bnbhack-trading-agent", "version": "0.1.0"},
            },
        )
        try:
            self._post("notifications/initialized", None, is_notification=True)
        except Exception:
            pass  # some servers don't require / accept this
        self._initialized = True

    # ---- generic tool call --------------------------------------------
    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        """Call an MCP tool and return its parsed result.

        Monolit tools return a JSON string inside result.content[0].text — we
        parse that into a Python object. Falls back to the raw envelope.
        """
        self._ensure_initialized()
        result = self._post("tools/call", {"name": name, "arguments": arguments or {}})
        content = result.get("content")
        if isinstance(content, list) and content:
            first = content[0]
            text = first.get("text") if isinstance(first, dict) else None
            if isinstance(text, str):
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return text
        if "structuredContent" in result:
            return result["structuredContent"]
        return result

    def query_evm(self, sql: str) -> list[dict[str, Any]]:
        out = self.call_tool("query_evm_onchain", {"query": sql})
        return _rows(out)

    def query_cex_normalized(self, sql: str) -> list[dict[str, Any]]:
        return _rows(self.call_tool("query_cex_normalized", {"query": sql}))

    def query_cex_aggregates(self, sql: str) -> list[dict[str, Any]]:
        return _rows(self.call_tool("query_cex_aggregates", {"query": sql}))

    # ---- typed signal helpers (our edge) ------------------------------
    def onchain_netflow_bsc(self, token_address: str, *, hours: int = 24) -> list[dict[str, Any]]:
        """Hourly on-chain DEX flow for a BEP-20 token from swap_events (BSC).

        swap_events has indexed base_coin/quote_coin address columns (fast),
        unlike the array columns on defi_events. In a swap the trader spends
        base_coin to receive quote_coin, so when our token is the quote_coin it
        was BOUGHT, and when it is the base_coin it was SOLD. Net buy volume
        (in token units) is a proxy for accumulation/distribution pressure.
        Address must be a lowercase 0x... 42-char string.
        """
        addr = token_address.lower()
        sql = f"""
        SELECT toStartOfHour(block_time) AS hour,
               sumIf(toFloat64(quote_coin_amount)/pow(10, quote_coin_decimals), quote_coin = '{addr}') AS buy_vol,
               sumIf(toFloat64(base_coin_amount)/pow(10, base_coin_decimals), base_coin = '{addr}')   AS sell_vol,
               buy_vol - sell_vol AS net_vol,
               countIf(quote_coin = '{addr}') AS buys,
               countIf(base_coin = '{addr}')  AS sells,
               uniqExact(tx_from_address) AS wallets
        FROM evm.swap_events
        WHERE chain = 'bsc'
          AND block_time > now() - INTERVAL {int(hours)} HOUR
          AND (base_coin = '{addr}' OR quote_coin = '{addr}')
        GROUP BY hour ORDER BY hour
        """
        return self.query_evm(sql)

    def cex_funding(self, coin: str, venue: str = "binance", *, hours: int = 168) -> list[dict[str, Any]]:
        sql = f"""
        SELECT ts, funding_rate FROM cex_mcp.funding_normalized
        WHERE venue = '{venue}' AND canonical_base = '{coin.upper()}'
          AND ts > now() - INTERVAL {int(hours)} HOUR
        ORDER BY ts
        """
        return self.query_cex_normalized(sql)

    def cex_taker_skew(self, coin: str, venue: str = "binance", *, hours: int = 168) -> list[dict[str, Any]]:
        sql = f"""
        SELECT * FROM cex_mcp.coin_taker
        WHERE venue = '{venue}' AND canonical_base = '{coin.upper()}'
          AND ts > now() - INTERVAL {int(hours)} HOUR
        ORDER BY ts
        """
        return self.query_cex_aggregates(sql)

    def technical_analysis(self, symbol: str, *, timeframe: str = "4h") -> Any:
        return self.call_tool(
            "get_and_calc_cex_technical_analysis",
            {"symbol": symbol.upper(), "timeframe": timeframe, "mode": "overview"},
        )

    def resolve_token(self, symbol: str, chain: str = "bsc") -> Any:
        return self.call_tool("resolve_token_info", {"symbol": symbol, "chain": chain})


def _rows(result: Any) -> list[dict[str, Any]]:
    """Extract row dicts from a Monolit query tool result.

    Query tools return an envelope like {"status": "success", "content": [ {...}, ... ]}.
    """
    if isinstance(result, list):
        return [r for r in result if isinstance(r, dict)]
    if isinstance(result, dict):
        for key in ("content", "data", "rows", "result"):
            value = result.get(key)
            if isinstance(value, list):
                return [r for r in value if isinstance(r, dict)]
    return []
