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

# Manual BSC-contract overrides where the auto-resolver picks the wrong/illiquid token.
# ETH: the resolver returns WETH (0x4db5a..) which has ~no PancakeSwap depth; the deep,
# routable BSC asset is Binance-Peg Ethereum Token. (ETH is excluded from the tradeable
# DEX set anyway — see dex_liquidity.json — but keep the contract correct for the flow signal.)
CONTRACT_OVERRIDES = {
    "ETH": "0x2170ed0880ac9a755fd29b2688956bd959f933f8",
}


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
                bsc_contract=CONTRACT_OVERRIDES.get(sym, c.get("contract")),
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

    NOTE: ranks by *Binance CEX* 24h volume. The agent does NOT execute on Binance —
    it swaps spot on PancakeSwap via TWAK, where CEX volume is irrelevant. Using this
    to pick what to *hold* was the root cause of the red-team's auto-DQ finding
    (concentrating into names that have ~no on-chain depth → 50%+ drawdown from
    slippage). Use `dex_liquid_candidates` for any allocation decision; this is kept
    only for reference/diagnostics.
    """
    rank = liquidity_ranking(use_cache=use_cache)
    ranked = sorted([s for s in present if s in rank], key=lambda s: rank.get(s, 0.0), reverse=True)
    return ranked[:n]


# ---- BSC DEX liquidity (the EXECUTABLE universe) -------------------------
DEX_LIQUIDITY_FILE = _DATA / "dex_liquidity.json"
DEX_MIN_WEEKLY_USD = 20_000   # red-team threshold: below this, ~$200 trades move the pool


def dex_liquidity_ranking(*, path: Path | str = DEX_LIQUIDITY_FILE) -> dict[str, float]:
    """Eligible symbol -> measured trailing weekly USD volume on BSC PancakeSwap.

    Measured on-chain via Monolit `evm.swap_events` (chain='bsc'); cached here.
    This is what actually constrains execution — the agent trades on the DEX, not
    the CEX, so depth here (not Binance volume) decides what is safely tradable.
    """
    data = json.loads(Path(path).read_text())
    return {k: float(v["weekly_usd"]) for k, v in data.items() if not k.startswith("_")}


def dex_cost_bps(*, path: Path | str = DEX_LIQUIDITY_FILE, lp_fee_bps: float = 25.0) -> dict[str, float]:
    """Per-name realistic round-trip-leg cost (bps) for the backtest cost model:
    measured ~$200 price impact + the PancakeSwap LP fee (0.25%). Honest slippage,
    not the optimistic 10bps flat assumption that produced the phantom edge."""
    data = json.loads(Path(path).read_text())
    return {k: float(v["impact_bps_200"]) + lp_fee_bps for k, v in data.items() if not k.startswith("_")}


def dex_liquid_candidates(present: list[str], n: int | None = None, *,
                          min_weekly_usd: float = DEX_MIN_WEEKLY_USD,
                          path: Path | str = DEX_LIQUIDITY_FILE) -> list[str]:
    """The investable set: eligible names present in `present` that are genuinely
    EXECUTABLE on PancakeSwap — verdict `tradable*` in the cache (>= `min_weekly_usd`
    weekly DEX volume AND enough swap count that ~$200 trades are not the whole book),
    ranked by DEX volume descending. Filtering on verdict (not volume alone) excludes
    lumpy names that clear the dollar bar on a handful of large swaps (e.g. TWT/FF/XPL).

    This replaces CEX-volume ranking for every allocation decision. The red-team
    validated that ranking/restricting by *measured BSC DEX volume* converts the book
    from auto-DQ (−40% / 51% DD on CEX-rank) to DQ-safe (DD < 20%)."""
    data = json.loads(Path(path).read_text())
    rank = dex_liquidity_ranking(path=path)
    liquid = [s for s in present
              if rank.get(s, 0.0) >= min_weekly_usd
              and str(data.get(s, {}).get("verdict", "")).startswith("tradable")]
    liquid.sort(key=lambda s: rank.get(s, 0.0), reverse=True)
    return liquid[:n] if n else liquid


def refresh_dex_liquidity(client: "MonolitClient", *, days: int = 14,
                          path: Path | str = DEX_LIQUIDITY_FILE) -> dict[str, dict]:
    """Re-measure BSC DEX liquidity point-in-time before the contest and overwrite
    the cache. Per-token swap_events scan (bounded); slow (~minutes) — run as a job.
    Keeps the universe data-driven rather than a static snapshot."""
    from .monolit import _rows

    USDT = "0x55d398326f99059ff775485246999027b3197955"
    toks = [t for t in tradeable_tokens(load_universe()) if t.bsc_contract]
    out: dict[str, dict] = {"_note": "refreshed via universe.refresh_dex_liquidity",
                            "_threshold_weekly_usd": DEX_MIN_WEEKLY_USD}
    for t in toks:
        a = t.bsc_contract.lower()
        sql = (
            f"SELECT count() n, "
            f"sumIf(toFloat64(quote_coin_amount)/pow(10,quote_coin_decimals), quote_coin='{USDT}') "
            f"+ sumIf(toFloat64(base_coin_amount)/pow(10,base_coin_decimals), base_coin='{USDT}') AS usd "
            f"FROM evm.swap_events WHERE chain='bsc' AND block_time>now()-INTERVAL {days} DAY "
            f"AND (base_coin='{a}' OR quote_coin='{a}')"
        )
        try:
            r = _rows(client.query_evm(sql))
        except Exception:
            continue
        if r and int(r[0].get("n", 0) or 0) > 0:
            weekly = float(r[0].get("usd", 0) or 0) * 7.0 / days
            out[t.symbol] = {"weekly_usd": round(weekly), "swaps_period": int(r[0]["n"]),
                             "impact_bps_200": 999, "verdict": "measured"}
    Path(path).write_text(json.dumps(out, indent=1))
    return out
