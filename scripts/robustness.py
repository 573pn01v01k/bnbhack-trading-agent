"""Robustness / sensitivity validation of the live ENSEMBLE strategy, and a fix
for the turnover/cost fragility it surfaced: rebalance less often.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "scripts")
import research as R  # noqa: E402
from bnbhack_agent import strategy as ST, portfolio as PF  # noqa: E402

px = pd.read_parquet(R.MD.CACHE / "price_120d.parquet")
cov = px.notna().mean()
trad = [t.symbol for t in R.U.tradeable_tokens(R.U.load_universe())]
cand = [s for s in trad if s in px.columns and cov[s] > 0.85 and s != "BTC"]
try:
    liq = R.U.liquidity_ranking(); cand = sorted(cand, key=lambda s: liq.get(s, 0.0), reverse=True)
except Exception:
    pass


def stats(r):
    r = np.asarray(r, dtype=float)
    eq = np.cumprod(1 + r); peak = np.maximum.accumulate(eq)
    dd = float(((peak - eq) / peak).max()) if len(eq) else 0.0
    sh = float(r.mean() / r.std() * np.sqrt(24 * 365)) if r.std() > 0 else 0.0
    return float(eq[-1] - 1), sh, dd


def downsample(w, rebal_h):
    """Hold weights constant, only re-set them every `rebal_h` bars (cuts turnover)."""
    keep = (np.arange(len(w)) % rebal_h) == 0
    return w.where(pd.Series(keep, index=w.index), np.nan).ffill().fillna(0.0)


# Build the live ensemble WEIGHT panel once (so we can re-cost / re-balance it).
W = ST.ensemble_weights(px, cand)

print("=== (1) REBALANCE FREQ x COST (the turnover fix) ===", flush=True)
print(f"  {'rebalance':>10} | {'turnover':>8} | {'10bps':>14} | {'20bps':>14} | {'40bps':>14}", flush=True)
for rebal in (1, 4, 12, 24, 48):
    wd = downsample(W, rebal)
    turn = float((wd - wd.shift(1).fillna(0.0)).abs().sum(axis=1).mean())
    cells = []
    for c in (10, 20, 40):
        ret, sh, dd = stats(PF.strategy_returns(px[wd.columns], wd, cost_bps=c))
        cells.append(f"{ret:+.1%}/dd{dd:.0%}")
    print(f"  {rebal:>8}h  | {turn:>8.3f} | {cells[0]:>14} | {cells[1]:>14} | {cells[2]:>14}", flush=True)

print("=== (2) SUB-PERIOD stability (ensemble, daily rebal, 10bps, 3 windows) ===", flush=True)
wd = downsample(W, 24)
r = PF.strategy_returns(px[wd.columns], wd, cost_bps=10)
n = len(r)
for i, seg in enumerate([r.iloc[:n // 3], r.iloc[n // 3:2 * n // 3], r.iloc[2 * n // 3:]], 1):
    ret, sh, dd = stats(seg)
    print(f"  window {i}: ret={ret:+.1%} sharpe={sh:.2f} dd={dd:.1%}", flush=True)

print("=== (3) 7-day right tail (daily-rebal ensemble, 10bps) ===", flush=True)
WIN = 168
eq = (1 + r).cumprod()
a = np.array([eq.iloc[i + WIN] / eq.iloc[i] - 1 for i in range(0, len(eq) - WIN, 12)])
print(f"  mean={a.mean():+.1%} p95={np.percentile(a,95):+.1%} max={a.max():+.1%} P(>15%)={(a>0.15).mean():.1%}", flush=True)
print("DONE", flush=True)
