"""Signal panels feeding the rotation strategy.

Every signal at row t is computed only from data at or before t (no lookahead).
Signals are combined cross-sectionally: each is z-scored across symbols within a
bar, so heterogeneous inputs (price momentum, on-chain flow) are comparable, then
blended with weights. This is the layer where Monolit's on-chain flow — data the
CMC-only competitors lack — enters as alpha.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def xs_zscore(panel: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional (per-bar, across symbols) z-score."""
    mu = panel.mean(axis=1)
    sd = panel.std(axis=1).replace(0, np.nan)
    return panel.sub(mu, axis=0).div(sd, axis=0)


def momentum(price: pd.DataFrame, *, lookback: int = 48) -> pd.DataFrame:
    """Trailing return over `lookback` bars (known at t)."""
    return price.pct_change(lookback)


def vol_adjusted_momentum(price: pd.DataFrame, *, lookback: int = 48, vol_window: int = 72) -> pd.DataFrame:
    rets = price.pct_change()
    mom = price.pct_change(lookback)
    vol = rets.rolling(vol_window).std()
    return mom.div(vol.replace(0, np.nan))


def flow_signal(flow_imbalance: pd.DataFrame, *, smooth: int = 12) -> pd.DataFrame:
    """Smoothed on-chain net buy/sell imbalance in [-1, 1] (known at t)."""
    return flow_imbalance.rolling(smooth, min_periods=1).mean()


def combine(
    price: pd.DataFrame,
    *,
    mom_lookback: int = 48,
    vol_window: int = 72,
    flow_imbalance: pd.DataFrame | None = None,
    w_momentum: float = 1.0,
    w_flow: float = 0.0,
    flow_smooth: int = 12,
) -> pd.DataFrame:
    """Blended score panel aligned to `price`.

    score = w_momentum * z(vol_adj_momentum) + w_flow * z(flow_signal).
    With w_flow = 0 this is pure price momentum (the baseline); raising w_flow
    mixes in the Monolit on-chain edge.
    """
    mom_z = xs_zscore(vol_adjusted_momentum(price, lookback=mom_lookback, vol_window=vol_window))
    score = w_momentum * mom_z
    if flow_imbalance is not None and w_flow != 0.0:
        flow_z = xs_zscore(flow_signal(flow_imbalance, smooth=flow_smooth)).reindex_like(price)
        score = score.add(w_flow * flow_z, fill_value=0.0)
    return score.reindex_like(price)


def market_regime(price: pd.DataFrame, *, ref: str = "BTC", ma: int = 96) -> pd.Series:
    """Risk-off (True) when the reference asset trades below its `ma`-bar average.

    Used as a cash gate: in risk-off bars the portfolio rotates fully to cash
    (the contest's stablecoin leg), protecting the 30% drawdown limit.
    """
    if ref not in price.columns:
        return pd.Series(False, index=price.index)
    p = price[ref]
    return (p < p.rolling(ma).mean()).fillna(False)
