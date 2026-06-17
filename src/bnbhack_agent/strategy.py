"""The Track-1 strategy: regime-gated equal-weight rotation over the DEX-liquid set.

Validated on 120d of real hourly data, **net of measured per-name PancakeSwap
slippage** (the cost that matters — the agent executes on a DEX, not a CEX), with
a locked 21-day holdout:

    DEX-liquid ensemble (N=3/4 x MA=240/336/480) :  -2.2% full / +3.1% holdout / DD 18.7%  (LIVE)
    equal-weight (DEX-liquid set) baseline       :  +7.6% full but DD 29.2% (~at the DQ cliff)
    BTC buy-and-hold                             :  -2.9% / DD 28%

RED-TEAM CORRECTION: an earlier version ranked by Binance CEX volume and assumed a
flat 10bps cost, reporting ~+20%. But execution is on PancakeSwap — re-measuring
on-chain depth showed that book concentrated into names with ~no DEX liquidity and
would have hit 50%+ drawdown from slippage = automatic DQ. The fix: rank/restrict the
investable set to names with real BSC DEX depth (>$20k/wk) via
`universe.dex_liquid_candidates`, and price slippage per name. The honest result is a
DQ-safe book (DD 18.7% < 30% gate) with a modest right tail, not a +20% edge.

The strategy is a model-averaged ENSEMBLE over basket sizes N=(3,4) x regime MAs —
anti-overfit by construction (never a single-parameter bet). Two circuit-breakers cap
the left tail: a regime-HYSTERESIS gate (exit risk-off fast, re-enter only above
MA*(1+band) — kills whipsaw) and a 20% per-name TRAILING STOP (a held name 20% below
its 24h peak drops to cash). Both are near-zero carry on a benign window and bound
drawdown in stress. Spot-only, no leverage (perps out of scope).

Net of realistic cost, NO positive return-alpha survives here (consistent with ~15
rejected signal hypotheses). The leaderboard play is convexity + not getting
disqualified: a book that can post a >15% trending week (max 7d +22.7%, P(week>15%)=4%)
while drawdown stays well inside the 30% gate. The optional moonshot sleeve defaults
OFF — it is a ~-1.9pp drag once slippage is real.

The SAME `combined_weights` function drives both the backtest and the live agent
(decision parity). Monolit on-chain flow + token security + the M3 negative-news veto
enter live as best-effort overlays on the held basket, never blocking the core decision.
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
    max_positions: int = 12      # liquid candidate pool the ensemble slices into top-N sleeves
    ensemble_ns: tuple = (3, 4)           # basket sizes — de-concentrated (red-team): the DEX-liquid set is only ~5 names,
                                          # so 3–4 spreads slippage and avoids the single-name DQ the (2,3) book risked
    ensemble_mas: tuple = (240, 336, 480) # regime-MA sleeves
    rebalance_hours: int = 4     # main sleeve re-weights every 4h (cost-robust)
    max_weight: float = 0.34     # per-name cap (3-name sleeve = 0.33 each; bounds single-name slippage/concentration risk)
    regime_band: float = 0.0075  # hysteresis: exit risk-off fast (BTC<MA) but only re-enter at BTC>MA*(1+band) — kills whipsaw
    trailing_stop: float = 0.20  # per-name circuit-breaker: held name >=20% below its trailing-24h peak -> drop to cash
    trailing_lookback: int = 24  # trailing-peak window (h) for the per-name stop
    # --- moonshot sleeve: OPTIONAL convex lottery on the DEX-liquid set, DEFAULT OFF ---
    # Tested net-of-realistic-DEX-slippage it is a ~-1.9pp drag (it churns idle cash through
    # thin pools), so it does not earn its keep — same verdict as the ~15 rejected return signals.
    # Kept available (set moonshot_frac>0) for a trending week; the >=1-trade/day rule is met by
    # the agent's ~zero-cost stable heartbeat, not by this sleeve.
    moonshot_frac: float = 0.0   # fraction of idle cash in moonshots (0 = off; was 0.10 with the phantom flat cost)
    moonshot_k: int = 2          # how many movers to hold
    moonshot_lookback: int = 12  # trailing hours used to pick "what's starting to move"
    moonshot_rebalance: int = 24 # rotate daily if enabled (a heartbeat cadence, not a churn engine)
    cost_bps: float = 10.0       # OPTIMISTIC flat cost floor; the report also prices realistic per-name DEX slippage
    dd_cap: float = 0.30         # contest disqualification gate
    hard_dd_stop: float = 0.22   # our internal circuit-breaker, inside the gate
    min_coverage: float = 0.85   # min price-history coverage to include a name


FROZEN = StrategyConfig()


def regime_off(price: pd.DataFrame, cfg: StrategyConfig = FROZEN) -> pd.Series:
    """Risk-off mask: reference asset below its MA -> rotate to cash/stables.

    With `regime_band` > 0 this is a *hysteresis* gate (red-team fix for whipsaw):
    exit to cash as soon as BTC < MA, but only re-enter risk-on once BTC climbs back
    to MA*(1+band). The dead-band stops the book from flip-flopping across the MA in
    a chop (every flip pays round-trip slippage), at the cost of a slightly later
    re-entry. Stateless (band=0) reduces to the original `ref < MA` signal.
    """
    if cfg.regime_ref not in price.columns:
        return pd.Series(False, index=price.index)
    ref = price[cfg.regime_ref]
    ma = ref.rolling(cfg.ma_window).mean()
    if not cfg.regime_band:
        return (ref < ma).fillna(False)
    below = (ref < ma).to_numpy()
    reenter = (ref >= ma * (1.0 + cfg.regime_band)).to_numpy()
    valid = ma.notna().to_numpy()
    off = np.zeros(len(ref), dtype=bool)
    cur = False
    for i in range(len(ref)):
        if not valid[i]:
            off[i] = False
            continue
        if cur:                       # currently risk-off: re-enter only if strongly above MA
            if reenter[i]:
                cur = False
        else:                         # currently risk-on: exit the moment we drop below MA
            if below[i]:
                cur = True
        off[i] = cur
    return pd.Series(off, index=ref.index)


def apply_trailing_stop(price: pd.DataFrame, weights: pd.DataFrame, cfg: StrategyConfig = FROZEN) -> pd.DataFrame:
    """Per-name circuit-breaker: when a held name closes >= `trailing_stop` below its
    trailing `trailing_lookback`-hour peak, force its weight to zero (the freed weight
    stays in cash — never redistributed into another falling name). Point-in-time: the
    trailing peak at bar t uses only prices <= t. Caps a single held-name crash from a
    DQ-level drawdown to a bounded one (red-team: −50% name -> ~12% book DD vs ~38%)."""
    if not cfg.trailing_stop:
        return weights
    cols = [c for c in weights.columns if c in price.columns]
    if not cols:
        return weights
    px = price[cols]
    peak = px.rolling(cfg.trailing_lookback, min_periods=1).max()
    alive = (px >= peak * (1.0 - cfg.trailing_stop))
    alive = alive.reindex(index=weights.index, columns=weights.columns, fill_value=True).fillna(True)
    return weights.where(alive, 0.0)


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


def ensemble_weights(price: pd.DataFrame, ranked_candidates: list[str], cfg: StrategyConfig = FROZEN,
                     *, vetoes: set[str] | None = None) -> pd.DataFrame:
    """Robust model-averaged target weights: the mean of regime-gated equal-weight sleeves
    over a grid of basket sizes (top-N most-liquid) x regime MAs. No single-parameter bet —
    walk-forward +15.0% OOS / holdout +2.4%, beating every single-config sleeve. The names
    that recur across sleeves (most liquid) get more weight; the regime MAs are averaged so
    no one MA's timing can sink the book.
    """
    sleeves = []
    for n in cfg.ensemble_ns:
        cols = ranked_candidates[:n]
        for ma in cfg.ensemble_mas:
            sleeves.append(target_weights(price, cols, StrategyConfig(
                regime_ref=cfg.regime_ref, ma_window=ma, max_weight=cfg.max_weight), vetoes=vetoes))
    cols = sorted(set().union(*[s.columns for s in sleeves]))
    acc = sum(s.reindex(columns=cols, fill_value=0.0) for s in sleeves) / len(sleeves)
    # rebalance cadence: only re-set weights every `rebalance_hours` bars (hold between) to
    # cut turnover — robustness validation showed hourly churn makes the book cost-fragile.
    if cfg.rebalance_hours and cfg.rebalance_hours > 1 and len(acc) > cfg.rebalance_hours:
        keep = (np.arange(len(acc)) % cfg.rebalance_hours) == 0
        acc = acc.where(pd.Series(keep, index=acc.index), np.nan).ffill().fillna(0.0)
    return acc


def moonshot_weights(price: pd.DataFrame, candidates: list[str], cfg: StrategyConfig = FROZEN) -> pd.DataFrame:
    """Small lottery sleeve: hold the top-k eligible tokens by short-term trailing return
    (names that are starting to move), equal-weight, rotated every `moonshot_rebalance` h.
    Negative-to-flat expected value BY DESIGN — it's a capped convex bet for the right tail,
    and its frequent rotation keeps the agent trading (>=1/day) when the main book is in cash.
    Point-in-time (trailing return known at t — no lookahead)."""
    sub = price[[c for c in candidates if c in price.columns]]
    mom = sub.pct_change(cfg.moonshot_lookback)
    rank = mom.rank(axis=1, ascending=False, method="first")
    w = ((rank <= cfg.moonshot_k) & sub.notna() & (mom > 0)).astype("float64")  # only chase positive movers
    w = w.div(w.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    rb = cfg.moonshot_rebalance
    if rb and rb > 1 and len(w) > rb:
        keep = (np.arange(len(w)) % rb) == 0
        w = w.where(pd.Series(keep, index=w.index), np.nan).ffill().fillna(0.0)
    return w


def combined_weights(price: pd.DataFrame, ranked_candidates: list[str], cfg: StrategyConfig = FROZEN,
                     *, vetoes: set[str] | None = None) -> pd.DataFrame:
    """Live target weights: the validated main ensemble PLUS a capped moonshot sleeve that
    fills idle cash. In risk-on the book is mostly the ensemble; in risk-off (ensemble in
    cash) up to `moonshot_frac` is deployed into frequent small moonshot bets — bounded
    downside, right-tail upside, and guaranteed trading activity in any regime."""
    main = ensemble_weights(price, ranked_candidates, cfg, vetoes=vetoes)
    moon = moonshot_weights(price, ranked_candidates, cfg)
    cash = (1.0 - main.sum(axis=1)).clip(lower=0.0)
    alloc = cash.clip(upper=cfg.moonshot_frac)              # only ever use idle cash, capped
    cols = sorted(set(main.columns) | set(moon.columns))
    main = main.reindex(columns=cols, fill_value=0.0)
    moon = moon.reindex(columns=cols, fill_value=0.0)
    combined = main.add(moon.mul(alloc, axis=0), fill_value=0.0)
    return apply_trailing_stop(price, combined, cfg)        # per-name DQ circuit-breaker


def live_ensemble_allocation(price: pd.DataFrame, ranked_candidates: list[str], cfg: StrategyConfig = FROZEN,
                             *, vetoes: set[str] | None = None) -> dict:
    """Latest-bar target allocation for the live strategy (ensemble + moonshot sleeve)."""
    w = combined_weights(price, ranked_candidates, cfg, vetoes=vetoes)
    last = w.iloc[-1]
    held = {s: round(float(v), 5) for s, v in last.items() if v > 1e-9}
    # any sleeve risk-on -> not fully cash; report the consensus
    off_frac = float(sum(regime_off(price, StrategyConfig(ma_window=ma)).iloc[-1] for ma in cfg.ensemble_mas)) / len(cfg.ensemble_mas)
    return {
        "risk_off_fraction": round(off_frac, 2),
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
