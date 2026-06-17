"""Multi-asset hourly portfolio backtest for the rotation strategy.

Separates the two concerns so each is testable:
  - `decide_weights`: turn a per-(ts,symbol) score panel into target weights
    (top-K long/flat rotation, caps, risk-off-to-cash regime gate).
  - `simulate`: deterministic accounting of an equity curve from prices + weights,
    with strict no-lookahead and turnover cost.

No-lookahead contract: weights in row t are decided using information available
*at* t (the score panel must itself be computed from data ≤ t). simulate() holds
row-t weights over the t→t+1 step, i.e. it earns next-bar returns — implemented
by shifting weights forward one bar. There is no way for a return to feed back
into the weight that captured it.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

HOURS_PER_YEAR = 24 * 365


@dataclass(frozen=True)
class PortfolioResult:
    equity: pd.Series
    total_return: float
    sharpe: float
    max_drawdown: float
    turnover: float          # average per-bar one-sided turnover
    avg_exposure: float
    n_bars: int

    def to_dict(self) -> dict:
        return {
            "total_return": round(self.total_return, 6),
            "sharpe": round(self.sharpe, 4),
            "max_drawdown": round(self.max_drawdown, 6),
            "turnover": round(self.turnover, 4),
            "avg_exposure": round(self.avg_exposure, 4),
            "n_bars": self.n_bars,
        }


def _max_drawdown(equity: pd.Series) -> float:
    peak = equity.cummax()
    return float(((peak - equity) / peak).max())


def metrics_from_returns(port_ret: pd.Series) -> PortfolioResult:
    port_ret = port_ret.fillna(0.0)
    equity = (1.0 + port_ret).cumprod()
    total = float(equity.iloc[-1] - 1.0) if len(equity) else 0.0
    sigma = float(port_ret.std())
    sharpe = float(port_ret.mean() / sigma * np.sqrt(HOURS_PER_YEAR)) if sigma > 0 else 0.0
    return PortfolioResult(
        equity=equity,
        total_return=total,
        sharpe=sharpe,
        max_drawdown=_max_drawdown(equity) if len(equity) else 0.0,
        turnover=0.0,
        avg_exposure=0.0,
        n_bars=len(port_ret),
    )


def decide_weights(
    score: pd.DataFrame,
    price: pd.DataFrame,
    *,
    top_k: int = 5,
    max_weight: float = 0.34,
    min_score: float = 0.0,
    regime: pd.Series | None = None,
) -> pd.DataFrame:
    """Top-K long/flat target weights from a score panel.

    - Only symbols with a valid price and score > `min_score` are eligible.
    - Pick the top-K by score each bar, equal-weight, capped at `max_weight`
      (leftover stays in cash, i.e. weights may sum to < 1).
    - `regime` (bool Series, True = risk-off) forces all-cash that bar.
    """
    score = score.reindex_like(price)
    valid = price.notna() & score.notna() & (score > min_score)
    masked = score.where(valid)

    # rank within each row; keep the top_k highest scores
    ranks = masked.rank(axis=1, ascending=False, method="first")
    chosen = ranks <= top_k

    weights = chosen.astype("float64")
    counts = weights.sum(axis=1).replace(0, np.nan)
    weights = weights.div(counts, axis=0).clip(upper=max_weight).fillna(0.0)

    if regime is not None:
        off = regime.reindex(weights.index).fillna(False).astype(bool)
        weights.loc[off] = 0.0
    return weights


def strategy_returns(price: pd.DataFrame, weights: pd.DataFrame, *, cost_bps: float = 10.0,
                     cost_bps_by_name: dict[str, float] | None = None) -> pd.Series:
    """Per-bar net portfolio returns (no-lookahead, turnover-costed).

    Exposed so the walk-forward engine can compute it once per parameter set and
    slice it into train/test windows without recomputation.

    `cost_bps_by_name` (symbol -> bps) charges *per-name* turnover at that name's cost
    — the honest DEX model (measured PancakeSwap slippage + LP fee), since a flat bps
    badly understates cost on thin pools. Names absent from the map fall back to
    `cost_bps`. Pass None to use the flat `cost_bps` everywhere.
    """
    weights = weights.reindex_like(price).fillna(0.0)
    rets = price.pct_change().fillna(0.0)
    held = weights.shift(1).fillna(0.0)
    gross = (held * rets).sum(axis=1)
    dturn = (weights - weights.shift(1).fillna(0.0)).abs()
    if cost_bps_by_name:
        bps = pd.Series({c: cost_bps_by_name.get(c, cost_bps) for c in weights.columns})
        cost = (dturn * (bps / 1e4)).sum(axis=1)
    else:
        cost = dturn.sum(axis=1) * (cost_bps / 1e4)
    return gross - cost


def simulate(price: pd.DataFrame, weights: pd.DataFrame, *, cost_bps: float = 10.0) -> PortfolioResult:
    """Equity curve from prices + target weights with turnover cost.

    Row-t weights are held over t→t+1 (shifted forward one bar) — strict
    no-lookahead. `cost_bps` is charged on one-sided turnover each bar.
    """
    weights = weights.reindex_like(price).fillna(0.0)
    rets = price.pct_change().fillna(0.0)

    held = weights.shift(1).fillna(0.0)               # what we actually hold into bar t
    gross = (held * rets).sum(axis=1)

    turnover = (weights - weights.shift(1).fillna(0.0)).abs().sum(axis=1)
    cost = turnover * (cost_bps / 1e4)
    port_ret = gross - cost

    res = metrics_from_returns(port_ret)
    return PortfolioResult(
        equity=res.equity,
        total_return=res.total_return,
        sharpe=res.sharpe,
        max_drawdown=res.max_drawdown,
        turnover=float(turnover.mean()),
        avg_exposure=float(weights.sum(axis=1).mean()),
        n_bars=res.n_bars,
    )


# ---- baselines -----------------------------------------------------------
def equal_weight_baseline(price: pd.DataFrame, *, cost_bps: float = 10.0) -> PortfolioResult:
    """Buy-and-hold an equal-weight basket of all symbols (rebalanced hourly)."""
    valid = price.notna()
    w = valid.astype("float64")
    w = w.div(w.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    return simulate(price, w, cost_bps=cost_bps)


def single_asset_baseline(price: pd.DataFrame, symbol: str) -> PortfolioResult:
    s = price[[symbol]].dropna()
    rets = s[symbol].pct_change().fillna(0.0)
    return metrics_from_returns(rets)
