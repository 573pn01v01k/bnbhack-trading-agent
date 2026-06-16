from __future__ import annotations

import csv
import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from .models import Candle

CMC_IDS = {"BTC": 1, "ETH": 1027, "BNB": 1839, "SOL": 5426, "USDC": 3408}


class DataSource(Protocol):
    def load(self, symbol: str) -> list[Candle]: ...


def parse_timestamp(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@dataclass(frozen=True)
class FixtureDataSource:
    path: Path

    def load(self, symbol: str = "BNB") -> list[Candle]:
        with self.path.open(newline="") as fh:
            rows = csv.DictReader(fh)
            candles = [
                Candle(
                    timestamp=parse_timestamp(row["timestamp"]),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                )
                for row in rows
            ]
        if not candles:
            raise ValueError(f"no candles loaded from {self.path}")
        return candles


@dataclass(frozen=True)
class CMCDataSource:
    api_key: str | None = None
    count: int = 180
    convert: str = "USD"
    base_url: str = "https://pro-api.coinmarketcap.com"

    def load(self, symbol: str = "BNB") -> list[Candle]:
        api_key = self.api_key or os.environ.get("CMC_PRO_API_KEY") or os.environ.get("CMC_API_KEY")
        if not api_key:
            raise RuntimeError("CMC_PRO_API_KEY or CMC_API_KEY is required for CMCDataSource")
        cmc_id = CMC_IDS.get(symbol.upper())
        if not cmc_id:
            raise ValueError(f"unknown CMC id for symbol {symbol!r}; add it to CMC_IDS")
        params = urllib.parse.urlencode({"id": cmc_id, "time_period": "daily", "count": self.count, "convert": self.convert})
        url = f"{self.base_url}/v2/cryptocurrency/ohlcv/historical?{params}"
        request = urllib.request.Request(url, headers={"Accept": "application/json", "X-CMC_PRO_API_KEY": api_key})
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return parse_cmc_ohlcv_response(payload, convert=self.convert)


def parse_cmc_ohlcv_response(payload: dict[str, Any], *, convert: str = "USD") -> list[Candle]:
    data = payload.get("data", {})
    quotes = data.get("quotes", []) if isinstance(data, dict) else []
    candles: list[Candle] = []
    for item in quotes:
        quote = item.get("quote", {}).get(convert) or item.get("quote", {}).get(convert.upper())
        if not quote:
            continue
        timestamp = item.get("time_close") or item.get("timestamp") or quote.get("timestamp")
        candles.append(
            Candle(
                timestamp=parse_timestamp(timestamp),
                open=float(quote["open"]),
                high=float(quote["high"]),
                low=float(quote["low"]),
                close=float(quote["close"]),
                volume=float(quote.get("volume", 0.0)),
            )
        )
    return sorted(candles, key=lambda item: item.timestamp)


@dataclass(frozen=True)
class BinanceKlinesSource:
    """Credential-free fallback for local backtests when CMC credentials are absent."""

    interval: str = "1d"
    limit: int = 180

    def load(self, symbol: str = "BNB") -> list[Candle]:
        market = f"{symbol.upper()}USDT"
        params = urllib.parse.urlencode({"symbol": market, "interval": self.interval, "limit": self.limit})
        url = f"https://api.binance.com/api/v3/klines?{params}"
        with urllib.request.urlopen(url, timeout=30) as response:
            rows = json.loads(response.read().decode("utf-8"))
        return [
            Candle(
                timestamp=datetime.fromtimestamp(row[0] / 1000, tz=timezone.utc),
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[5]),
            )
            for row in rows
        ]


@dataclass(frozen=True)
class MonolitMCPEnrichmentSource:
    """Optional Monolit MCP enrichment adapter; failures return empty features."""

    endpoint: str | None = None

    def load_features(self, symbol: str, candles: list[Candle]) -> dict[str, list[float]]:
        endpoint = self.endpoint or os.environ.get("MONOLIT_MCP_URL")
        if not endpoint:
            return {}
        payload = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": "bnbhack-alpha-enrichment",
                "method": "tools/call",
                "params": {
                    "name": "wallet_flow_anomaly",
                    "arguments": {"symbol": symbol, "start": candles[0].timestamp.isoformat(), "end": candles[-1].timestamp.isoformat()},
                },
            }
        ).encode("utf-8")
        try:
            request = urllib.request.Request(endpoint, data=payload, headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(request, timeout=15) as response:
                data = json.loads(response.read().decode("utf-8"))
        except Exception:
            return {}
        result = data.get("result", {}) if isinstance(data, dict) else {}
        features = result.get("features", result)
        if not isinstance(features, dict):
            return {}
        normalized: dict[str, list[float]] = {}
        for key, values in features.items():
            if isinstance(values, list) and len(values) == len(candles):
                normalized[str(key)] = [float(x) for x in values]
        return normalized
