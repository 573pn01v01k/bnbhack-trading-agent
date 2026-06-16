"""Market-data panels for backtesting and live decisions.

Two aligned hourly panels over the tradeable universe:
  - PRICE panel: close price per symbol (Binance <SYM>USDT spot klines — reliable,
    public, matches the contest's USD valuation of the BEP-20 tokens).
  - FLOW panel: on-chain net DEX buy/sell volume per symbol (Monolit swap_events on
    BSC) — the proprietary edge competitors using CMC-only do not have.

Both are pandas DataFrames indexed by hourly UTC timestamps, columns = symbols.
Panels are cached as parquet so re-runs and the live agent are instant.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from .monolit import MonolitClient
    from .universe import Token

CACHE = Path(__file__).parent / "data" / "cache"
CACHE.mkdir(parents=True, exist_ok=True)
_BINANCE = "https://api.binance.com/api/v3/klines"


# ---- Binance hourly price ------------------------------------------------
_BINANCE_HOSTS = (
    "https://api.binance.com",
    "https://data-api.binance.vision",
    "https://api1.binance.com",
)


def _get_klines(host: str, symbol: str, cursor: int, end_ms: int, timeout: int) -> list:
    url = f"{host}/api/v3/klines?symbol={symbol}&interval=1h&limit=1000&startTime={cursor}&endTime={end_ms}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def fetch_binance_hourly(symbol: str, *, days: int = 120, timeout: int = 30,
                         pause: float = 0.06, max_retries: int = 4) -> pd.Series:
    """Hourly close series for <SYM>USDT, paginated (1000 candles/request).

    Retries with backoff on rate limits / transient errors and rotates Binance
    hosts. Returns an empty Series only if the symbol genuinely has no data.
    """
    end_ms = int(time.time() * 1000)
    cursor = end_ms - days * 24 * 3600 * 1000
    closes: dict[int, float] = {}
    host_idx = 0
    while cursor < end_ms:
        rows = None
        for attempt in range(max_retries):
            host = _BINANCE_HOSTS[host_idx % len(_BINANCE_HOSTS)]
            try:
                rows = _get_klines(host, symbol, cursor, end_ms, timeout)
                break
            except urllib.error.HTTPError as e:
                if e.code in (429, 418):  # rate limited / banned -> back off + rotate host
                    host_idx += 1
                    time.sleep(min(10, 1.0 * (2 ** attempt)))
                    continue
                if e.code == 400:  # bad symbol / no such pair
                    return pd.Series(dtype="float64")
                host_idx += 1
                time.sleep(0.5 * (attempt + 1))
            except Exception:
                host_idx += 1
                time.sleep(0.5 * (attempt + 1))
        if not rows:
            break
        for k in rows:
            closes[int(k[0])] = float(k[4])
        last_open = int(rows[-1][0])
        if len(rows) < 1000:
            break
        cursor = last_open + 3600 * 1000
        time.sleep(pause)
    if not closes:
        return pd.Series(dtype="float64")
    s = pd.Series(closes, dtype="float64")
    s.index = pd.to_datetime(s.index, unit="ms", utc=True)
    return s.sort_index()


def price_panel(symbols: list[str], *, days: int = 120, use_cache: bool = True) -> pd.DataFrame:
    cache = CACHE / f"price_{days}d.parquet"
    if use_cache and cache.exists():
        df = pd.read_parquet(cache)
        if set(symbols).issubset(df.columns):
            return df[symbols]
    series = {}
    for sym in symbols:
        pair = sym if sym.upper().endswith("USDT") else f"{sym.upper()}USDT"
        s = fetch_binance_hourly(pair, days=days)
        if not s.empty:
            series[sym] = s
    if not series:
        raise RuntimeError("no price series fetched (network/rate-limit?) — check connectivity to Binance")
    df = pd.DataFrame(series).sort_index()
    # align to a regular hourly grid, forward-fill small gaps (<= 6h)
    full = pd.date_range(df.index.min(), df.index.max(), freq="1h", tz="UTC")
    df = df.reindex(full).ffill(limit=6)
    if use_cache:
        df.to_parquet(cache)
    return df


# ---- Monolit on-chain flow (BSC) ----------------------------------------
def fetch_token_flow(client: "MonolitClient", token: "Token", *, hours: int) -> pd.DataFrame:
    """Hourly net DEX flow for one token; empty frame if no contract/data."""
    if not token.bsc_contract:
        return pd.DataFrame()
    rows = client.onchain_netflow_bsc(token.bsc_contract, hours=hours)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["hour"] = pd.to_datetime(df["hour"], utc=True)
    return df.set_index("hour").sort_index()


def flow_panel(client: "MonolitClient", tokens: list["Token"], *, days: int = 120,
               field: str = "net_vol", use_cache: bool = True) -> pd.DataFrame:
    """Per-symbol hourly on-chain flow `field` (default net_vol)."""
    cache = CACHE / f"flow_{field}_{days}d.parquet"
    if use_cache and cache.exists():
        return pd.read_parquet(cache)
    hours = days * 24
    cols = {}
    for t in tokens:
        df = fetch_token_flow(client, t, hours=hours)
        if not df.empty and field in df.columns:
            cols[t.symbol] = df[field].astype("float64")
    panel = pd.DataFrame(cols).sort_index()
    if not panel.empty:
        full = pd.date_range(panel.index.min(), panel.index.max(), freq="1h", tz="UTC")
        panel = panel.reindex(full)
    if use_cache:
        panel.to_parquet(cache)
    return panel
