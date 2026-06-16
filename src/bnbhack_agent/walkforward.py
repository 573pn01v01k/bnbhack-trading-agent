"""Walk-forward, out-of-sample evaluation — the anti-overfitting core.

Overfitting is the central risk in strategy search: it is trivial to find a
parameter set that looks great on one window. This engine refuses to report any
in-sample number as the result. It:

  1. computes per-bar returns for every candidate parameter set once;
  2. slides non-overlapping (train, test) folds across time;
  3. on each TRAIN window selects the parameter set by a robustness objective
     (Sharpe subject to a max-drawdown cap), never peeking at the test window;
  4. applies that choice to the immediately-following TEST window (true OOS);
  5. stitches the OOS test segments into one continuous out-of-sample curve and
     compares it to baselines (equal-weight basket, BTC buy-and-hold).

The headline metrics are the stitched OOS curve. The in-sample/OOS spread is
reported as an overfit gauge — a strategy that only wins in-sample is rejected.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import product

import numpy as np
import pandas as pd

from . import signals as sig
from .portfolio import (
    PortfolioResult,
    decide_weights,
    equal_weight_baseline,
    metrics_from_returns,
    single_asset_baseline,
    strategy_returns,
)


@dataclass(frozen=True)
class FoldResult:
    fold: int
    params: dict
    train_sharpe: float
    train_return: float
    test_return: float
    test_sharpe: float
    test_max_dd: float


@dataclass
class WalkForwardReport:
    oos_equity: pd.Series
    oos: PortfolioResult
    folds: list[FoldResult]
    baselines: dict[str, PortfolioResult]
    insample_return_mean: float
    param_grid_size: int

    def summary(self) -> dict:
        return {
            "oos": self.oos.to_dict(),
            "baselines": {k: v.to_dict() for k, v in self.baselines.items()},
            "insample_return_mean": round(self.insample_return_mean, 6),
            "oos_minus_insample_return": round(self.oos.total_return / max(1, len(self.folds)) - self.insample_return_mean, 6),
            "n_folds": len(self.folds),
            "param_grid_size": self.param_grid_size,
            "selected_params": [f.params for f in self.folds],
        }


def default_grid() -> list[dict]:
    grid = []
    for lb, vw, k, mw, regime in product(
        [24, 48, 72, 96],      # momentum lookback (h)
        [48, 72],              # vol window (h)
        [3, 5, 8],             # top-K
        [0.34, 0.5],           # max weight per name
        [True, False],         # BTC-MA cash regime gate
    ):
        grid.append({"mom_lookback": lb, "vol_window": vw, "top_k": k, "max_weight": mw, "regime": regime})
    return grid


def _returns_for_params(price, p, *, flow_imbalance=None, cost_bps=10.0, regime_series=None) -> pd.Series:
    score = sig.combine(
        price,
        mom_lookback=p["mom_lookback"],
        vol_window=p["vol_window"],
        flow_imbalance=flow_imbalance,
        w_momentum=p.get("w_momentum", 1.0),
        w_flow=p.get("w_flow", 0.0),
    )
    regime = (regime_series if regime_series is not None else sig.market_regime(price)) if p.get("regime") else None
    weights = decide_weights(score, price, top_k=p["top_k"], max_weight=p["max_weight"], regime=regime)
    return strategy_returns(price, weights, cost_bps=cost_bps)


def regime_ew_walk_forward(
    price: pd.DataFrame,
    *,
    regime_ref: str = "BTC",
    ma_grid: tuple[int, ...] = (168, 240, 336, 480, 672),
    train_h: int = 24 * 21,
    test_h: int = 24 * 7,
    cost_bps: float = 10.0,
    dd_cap: float = 0.30,
) -> WalkForwardReport:
    """Walk-forward the frozen strategy: regime-gated equal-weight.

    The only hyperparameter is the regime MA window, selected on each TRAIN
    window (best Sharpe subject to DD cap) and applied out-of-sample. Candidate
    columns exclude the regime reference. This is the headline, anti-overfit
    evaluation behind the live strategy.
    """
    cands = [c for c in price.columns if c != regime_ref]
    sub = price[cands]
    ref = price[regime_ref] if regime_ref in price.columns else None

    def _ret(ma: int) -> pd.Series:
        w = sub.notna().astype("float64")
        w = w.div(w.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
        if ref is not None:
            w.loc[(ref < ref.rolling(ma).mean()).fillna(False)] = 0.0
        return strategy_returns(sub, w, cost_bps=cost_bps)

    ret_by_ma = {ma: _ret(ma) for ma in ma_grid}
    ew_ret = strategy_returns(
        sub, sub.notna().astype("float64").pipe(lambda w: w.div(w.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)),
        cost_bps=cost_bps,
    )

    n = len(price)
    folds: list[FoldResult] = []
    oos_segments, ins_returns = [], []
    start = fold_no = 0
    while start + train_h + test_h <= n:
        tr = slice(start, start + train_h)
        te = slice(start + train_h, start + train_h + test_h)
        best_ma, best_key = ma_grid[0], (-1e9, -1e9)
        for ma in ma_grid:
            m = metrics_from_returns(ret_by_ma[ma].iloc[tr])
            key = (0 if m.max_drawdown > dd_cap else 1, m.sharpe)
            if key > best_key:
                best_key, best_ma = key, ma
        tr_m = metrics_from_returns(ret_by_ma[best_ma].iloc[tr])
        te_m = metrics_from_returns(ret_by_ma[best_ma].iloc[te])
        folds.append(FoldResult(fold_no, {"ma_window": best_ma}, tr_m.sharpe, tr_m.total_return, te_m.total_return, te_m.sharpe, te_m.max_drawdown))
        oos_segments.append(ret_by_ma[best_ma].iloc[te])
        ins_returns.append(tr_m.total_return)
        start += test_h
        fold_no += 1

    oos_ret = pd.concat(oos_segments) if oos_segments else pd.Series(dtype="float64")
    oos = metrics_from_returns(oos_ret)
    baselines = {}
    if len(oos_ret):
        baselines["equal_weight"] = metrics_from_returns(ew_ret.loc[oos_ret.index])
        if ref is not None:
            baselines[f"{regime_ref}_hold"] = single_asset_baseline(price.loc[oos_ret.index], regime_ref)
    return WalkForwardReport(
        oos_equity=oos.equity, oos=oos, folds=folds, baselines=baselines,
        insample_return_mean=float(np.mean(ins_returns)) if ins_returns else 0.0,
        param_grid_size=len(ma_grid),
    )


def walk_forward(
    price: pd.DataFrame,
    *,
    grid: list[dict] | None = None,
    flow_imbalance: pd.DataFrame | None = None,
    train_h: int = 24 * 21,
    test_h: int = 24 * 7,
    cost_bps: float = 10.0,
    dd_cap: float = 0.30,
    baseline_symbol: str = "BTC",
    regime_series: pd.Series | None = None,
) -> WalkForwardReport:
    grid = grid or default_grid()
    # 1) per-bar returns for every candidate, once.
    ret_by_param: list[pd.Series] = [
        _returns_for_params(price, p, flow_imbalance=flow_imbalance, cost_bps=cost_bps, regime_series=regime_series)
        for p in grid
    ]

    n = len(price)
    idx = price.index
    folds: list[FoldResult] = []
    oos_segments: list[pd.Series] = []
    insample_returns: list[float] = []

    start = 0
    fold_no = 0
    while start + train_h + test_h <= n:
        tr = slice(start, start + train_h)
        te = slice(start + train_h, start + train_h + test_h)

        best_i, best_key = None, (-1e9, -1e9)
        for i, ret in enumerate(ret_by_param):
            m = metrics_from_returns(ret.iloc[tr])
            penalized = m.max_drawdown > dd_cap
            key = (0 if penalized else 1, m.sharpe, m.total_return)  # respect DD cap first, then Sharpe
            if key > best_key:
                best_key, best_i = key, i

        chosen = grid[best_i]
        tr_m = metrics_from_returns(ret_by_param[best_i].iloc[tr])
        te_ret = ret_by_param[best_i].iloc[te]
        te_m = metrics_from_returns(te_ret)
        folds.append(FoldResult(fold_no, chosen, tr_m.sharpe, tr_m.total_return, te_m.total_return, te_m.sharpe, te_m.max_drawdown))
        oos_segments.append(te_ret)
        insample_returns.append(tr_m.total_return)

        start += test_h
        fold_no += 1

    oos_ret = pd.concat(oos_segments) if oos_segments else pd.Series(dtype="float64")
    oos = metrics_from_returns(oos_ret)
    oos_span = price.loc[oos_ret.index] if len(oos_ret) else price.iloc[0:0]

    baselines = {}
    if len(oos_span):
        baselines["equal_weight"] = equal_weight_baseline(oos_span, cost_bps=cost_bps)
        if baseline_symbol in price.columns:
            baselines[f"{baseline_symbol}_hold"] = single_asset_baseline(oos_span, baseline_symbol)

    return WalkForwardReport(
        oos_equity=oos.equity,
        oos=oos,
        folds=folds,
        baselines=baselines,
        insample_return_mean=float(np.mean(insample_returns)) if insample_returns else 0.0,
        param_grid_size=len(grid),
    )
