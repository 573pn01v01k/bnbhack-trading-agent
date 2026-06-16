"""Eligible-token universe for the BNB Hack Track-1 contest.

The contest scores a portfolio held in a fixed list of ~149 BEP-20 tokens on
CMC, valued hourly in USD. We build a *tradeable* universe = eligible symbols
that (a) have a reliable hourly price series (a Binance <SYM>USDT spot pair, our
backtest price source) and (b) resolve to a BSC contract (for the Monolit
on-chain flow signal). Stablecoins are the risk-off leg.

Resolution against Monolit's verified_tokens is chunked: the MCP gateway
silently returns empty for very long IN-lists, so we batch symbols.
"""
from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .monolit import MonolitClient

_DATA = Path(__file__).parent / "data"
ELIGIBLE_FILE = _DATA / "eligible_tokens.txt"

# Listed stablecoins in the eligible set = the risk-off leg.
STABLES = {"USDT", "USDC", "DAI", "USD1", "USDE", "USDD", "TUSD", "FDUSD", "FRAX",
           "FRXUSD", "USDF", "DUSD", "LISUSD", "XUSD", "EURI"}


@dataclass(frozen=True)
class Token:
    symbol: str
    binance_pair: str | None = None     # e.g. "BNBUSDT" if CEX-listed
    bsc_contract: str | None = None     # BEP-20 contract for on-chain flow
    decimals: int | None = None
    name: str | None = None
    is_stable: bool = False

    @property
    def tradeable(self) -> bool:
        """Has a price series we can backtest/value against."""
        return self.binance_pair is not None


def load_eligible_symbols(path: Path | str = ELIGIBLE_FILE) -> list[str]:
    raw = Path(path).read_text().split()
    seen, out = set(), []
    for s in raw:
        u = s.upper()
        if s.isascii() and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def binance_usdt_pairs(timeout: int = 30) -> set[str]:
    """Base assets that have a TRADING <BASE>USDT spot pair on Binance."""
    url = "https://api.binance.com/api/v3/exchangeInfo"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        info = json.loads(r.read().decode())
    bases = set()
    for s in info.get("symbols", []):
        if s.get("quoteAsset") == "USDT" and s.get("status") == "TRADING":
            bases.add(s["baseAsset"].upper())
    return bases


def resolve_bsc_contracts(client: "MonolitClient", symbols: list[str], *, chunk: int = 20) -> dict[str, dict]:
    """symbol -> {contract, decimals, name} via Monolit verified_tokens, chunked."""
    from .monolit import _rows

    out: dict[str, dict] = {}
    for i in range(0, len(symbols), chunk):
        batch = symbols[i : i + chunk]
        inlist = ",".join("'%s'" % s.replace("'", "") for s in batch)
        sql = (
            "SELECT upper(symbol) AS sym, any(contract_address) AS addr, "
            "any(decimals) AS decs, any(name) AS nm "
            "FROM mirror_wal.verified_tokens FINAL "
            f"WHERE chain='bsc' AND upper(symbol) IN ({inlist}) GROUP BY sym"
        )
        for r in _rows(client.call_tool("query_verified_tokens", {"query": sql})):
            out[r["sym"]] = {"contract": r["addr"], "decimals": r.get("decs"), "name": r.get("nm")}
    return out


def build_universe(client: "MonolitClient", *, save: bool = True) -> list[Token]:
    symbols = load_eligible_symbols()
    binance = binance_usdt_pairs()
    contracts = resolve_bsc_contracts(client, symbols)
    tokens: list[Token] = []
    for sym in symbols:
        c = contracts.get(sym, {})
        tokens.append(
            Token(
                symbol=sym,
                binance_pair=f"{sym}USDT" if sym in binance else None,
                bsc_contract=c.get("contract"),
                decimals=c.get("decimals"),
                name=c.get("name"),
                is_stable=sym in STABLES,
            )
        )
    if save:
        payload = [t.__dict__ for t in tokens]
        (_DATA / "universe_bsc.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    return tokens


def load_universe(path: Path | str = _DATA / "universe_bsc.json") -> list[Token]:
    data = json.loads(Path(path).read_text())
    return [Token(**d) for d in data]


def tradeable_tokens(tokens: list[Token]) -> list[Token]:
    """Non-stable tokens with a price series — the rotation candidates."""
    return [t for t in tokens if t.tradeable and not t.is_stable]


def liquidity_ranking(*, timeout: int = 30, use_cache: bool = True) -> dict[str, float]:
    """Eligible symbol -> Binance 24h quote volume (USD). Cached to data/."""
    cache = _DATA / "liquidity.json"
    if use_cache and cache.exists():
        return json.loads(cache.read_text())
    url = "https://api.binance.com/api/v3/ticker/24hr"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode())
    vol = {d["symbol"]: float(d.get("quoteVolume", 0)) for d in data}
    out = {}
    for sym in load_eligible_symbols():
        out[sym] = vol.get(f"{sym}USDT", 0.0)
    if use_cache:
        cache.write_text(json.dumps(out, indent=1))
    return out


def liquid_candidates(present: list[str], n: int, *, use_cache: bool = True) -> list[str]:
    """Top-`n` most-liquid eligible symbols that are present in `present`.

    Concentration is the leaderboard lever: a smaller basket fattens the right
    tail of weekly returns (validated) while the regime gate caps the downside.
    """
    rank = liquidity_ranking(use_cache=use_cache)
    ranked = sorted([s for s in present if s in rank], key=lambda s: rank.get(s, 0.0), reverse=True)
    return ranked[:n]
