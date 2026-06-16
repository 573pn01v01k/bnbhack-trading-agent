"""The frozen Track-1 strategy: regime-gated equal-weight rotation.

Walk-forward validated on 120d of real data (stitched OOS, MA chosen on train
each fold, applied out-of-sample):

    regime-EW, top-10 liquid  :  +16.5% return,  Sharpe 1.72,  max DD 16.4%  (LIVE)
    regime-EW, full 64        :  +11.9% return,  Sharpe 1.50,  max DD 14.7%
    equal-weight baseline     :  + 7.0% return,  Sharpe 0.75,  max DD 27.9%

Spot-only, no leverage (perps are out of scope). Naive momentum, reversal, and
vol-concentration were tested under the same protocol and REJECTED (they overfit:
in-sample positive, OOS deeply negative). Concentration to the most-liquid names
is the leaderboard lever: it keeps expected return flat-to-up but fattens the
weekly right tail (max 7-day return +14% at N=64 -> +28% at N=5), while the
regime gate holds the worst drawdown under the contest's 30% disqualification gate.

Thesis: hold a diversified equal-weight basket of the eligible BEP-20 tokens
when the market regime is risk-on (BTC above its ~14-day MA); rotate fully to
the stablecoin leg otherwise. Most profit without blowing up.

The SAME `target_weights` function drives both the backtest and the live agent
(decision parity). Monolit on-chain flow + token security enter live as a
best-effort veto/tilt on the held basket (the data edge competitors lack),
never blocking the core decision if the cluster is slow.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from .monolit import MonolitClient
    from .universe import Token


@dataclass(frozen=True)
class StrategyConfig:
    regime_ref: str = "BTC"      # regime reference asset
    ma_window: int = 336         # ~14d BTC MA gate (walk-forward picks lived in 240–672)
    max_positions: int = 10      # concentration: top-N most-liquid eligible (fat right tail, leaderboard lever)
    max_weight: float = 0.20     # per-name diversification cap
    rebalance_hours: int = 1     # hourly valuation cadence; also guarantees >=1 trade/day
    cost_bps: float = 10.0       # simulated transaction cost
    dd_cap: float = 0.30         # contest disqualification gate
    hard_dd_stop: float = 0.22   # our internal circuit-breaker, inside the gate
    min_coverage: float = 0.85   # min price-history coverage to include a name


FROZEN = StrategyConfig()


def regime_off(price: pd.DataFrame, cfg: StrategyConfig = FROZEN) -> pd.Series:
    """Risk-off mask: reference asset below its MA -> rotate to cash/stables."""
    if cfg.regime_ref not in price.columns:
        return pd.Series(False, index=price.index)
    ref = price[cfg.regime_ref]
    return (ref < ref.rolling(cfg.ma_window).mean()).fillna(False)


def target_weights(
    price: pd.DataFrame,
    candidates: list[str],
    cfg: StrategyConfig = FROZEN,
    *,
    vetoes: set[str] | None = None,
) -> pd.DataFrame:
    """Regime-gated equal-weight target weights over the candidate columns.

    Identical logic for backtest (full panel) and live (latest bar). Vetoed
    symbols (e.g. honeypot / strongly-negative on-chain flow) get zero weight.
    """
    cols = [c for c in candidates if c in price.columns and c != cfg.regime_ref]
    sub = price[cols]
    w = sub.notna().astype("float64")
    if vetoes:
        for v in vetoes:
            if v in w.columns:
                w[v] = 0.0
    w = w.div(w.sum(axis=1).replace(0, np.nan), axis=0).clip(upper=cfg.max_weight).fillna(0.0)
    w.loc[regime_off(price, cfg)] = 0.0
    return w


def live_allocation(
    price: pd.DataFrame,
    candidates: list[str],
    cfg: StrategyConfig = FROZEN,
    *,
    vetoes: set[str] | None = None,
) -> dict:
    """Target allocation for the most recent bar.

    Returns {"risk_off": bool, "weights": {symbol: weight}, "as_of": ts}.
    """
    w = target_weights(price, candidates, cfg, vetoes=vetoes)
    last = w.iloc[-1]
    held = {s: float(v) for s, v in last.items() if v > 1e-9}
    return {
        "risk_off": bool(regime_off(price, cfg).iloc[-1]),
        "weights": held,
        "as_of": price.index[-1].isoformat(),
    }


# ---- Monolit live edge (best-effort; never blocks the core decision) -----
def security_vetoes(client: "MonolitClient", tokens: list["Token"], *, max_checks: int = 25) -> set[str]:
    """Drop tokens Monolit flags as honeypot / very high tax. Best-effort."""
    bad: set[str] = set()
    for t in tokens[:max_checks]:
        if not t.bsc_contract:
            continue
        try:
            res = client.call_tool("get_token_security", {"address": t.bsc_contract, "chain": "bsc"})
        except Exception:
            continue
        text = str(res).lower()
        if '"is_honeypot": true' in text or '"honeypot": true' in text or "honeypot risk" in text:
            bad.add(t.symbol)
    return bad


def flow_tilt(client: "MonolitClient", symbols_to_contracts: dict[str, str], *, hours: int = 48,
              max_checks: int = 20) -> dict[str, float]:
    """Recent on-chain net buy/sell imbalance per symbol in roughly [-1, 1].

    A live, proprietary signal (Monolit swap_events) used to mildly overweight
    accumulation and underweight distribution within the held basket. Best-effort
    and bounded so an hourly decision stays fast.
    """
    out: dict[str, float] = {}
    for sym, addr in list(symbols_to_contracts.items())[:max_checks]:
        try:
            rows = client.onchain_netflow_bsc(addr, hours=hours)
        except Exception:
            continue
        if not rows:
            continue
        buy = sum(float(r.get("buy_vol", 0) or 0) for r in rows)
        sell = sum(float(r.get("sell_vol", 0) or 0) for r in rows)
        if buy + sell > 0:
            out[sym] = (buy - sell) / (buy + sell)
    return out
