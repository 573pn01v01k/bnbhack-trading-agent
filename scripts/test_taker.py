"""Test whether CEX taker-imbalance (Monolit coin_taker) adds OOS selection alpha
on top of the validated regime-gated equal-weight strategy. Honest walk-forward.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from bnbhack_agent import marketdata as MD, portfolio as PF, universe as U  # noqa: E402
from bnbhack_agent.monolit import MonolitClient  # noqa: E402

LOG = ROOT / "scripts" / "test_taker.log"


def log(m):
    with LOG.open("a") as fh:
        fh.write(f"[{time.strftime('%H:%M:%S')}] {m}\n")
    print(m, flush=True)


def wf_select(price, btc, score, ma_grid, k_grid, cost=10.0):
    """Walk-forward: regime-gated top-K by `score`, select (K, ma) on train."""
    sub = price
    rets = sub.pct_change()

    def ret_for(K, ma):
        valid = sub.notna() & score.notna()
        masked = score.where(valid)
        rank = masked.rank(axis=1, ascending=False, method="first")
        w = (rank <= K).astype(float)
        w = w.div(w.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
        w.loc[(btc < btc.rolling(ma).mean()).fillna(False)] = 0.0
        return PF.strategy_returns(sub, w, cost_bps=cost)

    cache = {(K, ma): ret_for(K, ma) for K in k_grid for ma in ma_grid}
    n = len(sub); th = 24 * 21; te = 24 * 7; st = 0; oos = []
    while st + th + te <= n:
        tr = slice(st, st + th); t2 = slice(st + th, st + th + te)
        best = None; bk = (-9, -9)
        for key, r in cache.items():
            m = PF.metrics_from_returns(r.iloc[tr])
            kk = (0 if m.max_drawdown > 0.30 else 1, m.sharpe)
            if kk > bk: bk, best = kk, key
        oos.append(cache[best].iloc[t2]); st += te
    return PF.metrics_from_returns(pd.concat(oos))


def main():
    cfg = json.load(open(os.path.expanduser("~/.claude.json"))); m = cfg["mcpServers"]["monolit"]
    os.environ.setdefault("MONOLIT_MCP_URL", m["url"]); os.environ.setdefault("MONOLIT_API_KEY", m["headers"]["X-Api-Key"])
    client = MonolitClient(timeout=90, max_retries=4)

    px = pd.read_parquet(MD.CACHE / "price_120d.parquet"); cov = px.notna().mean()
    trad = [t.symbol for t in U.tradeable_tokens(U.load_universe())]
    cand = [s for s in trad if s in px.columns and cov[s] > 0.85 and s != "BTC"]
    btc = px["BTC"]; price = px[cand]

    log(f"fetching taker panel for {len(cand)} coins x 120d ...")
    taker = MD.taker_panel(client, cand, days=120)
    log(f"taker panel: {taker.shape}, coins={list(taker.columns)[:8]}...")

    # signal known at t: smoothed taker imbalance, cross-sectional z-score
    sm = taker.rolling(24, min_periods=6).mean().reindex(price.index).reindex(columns=price.columns)
    z = sm.sub(sm.mean(axis=1), axis=0).div(sm.std(axis=1).replace(0, np.nan), axis=0)

    base = PF.metrics_from_returns(
        __import__("bnbhack_agent.walkforward", fromlist=["regime_ew_walk_forward"])
        .regime_ew_walk_forward(px[cand + ["BTC"]]).oos_equity.pct_change().fillna(0)
    )
    log(f"BASE regime-EW OOS: ret={base.total_return:+.1%} sharpe={base.sharpe:.2f} dd={base.max_drawdown:.1%}")

    sel = wf_select(price, btc, z, ma_grid=[240, 336, 480, 672], k_grid=[5, 10, 15, 20])
    log(f"TAKER top-K selection OOS: ret={sel.total_return:+.1%} sharpe={sel.sharpe:.2f} dd={sel.max_drawdown:.1%}")

    # tilt: EW weighted by (1 + alpha*z), regime-gated, walk-forward alpha+ma
    def tilt_ret(alpha, ma, cost=10.0):
        base_w = price.notna().astype(float)
        tilt = (1 + alpha * z.fillna(0)).clip(lower=0)
        w = (base_w * tilt)
        w = w.div(w.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
        w.loc[(btc < btc.rolling(ma).mean()).fillna(False)] = 0.0
        return PF.strategy_returns(price, w, cost_bps=cost)
    cache = {(a, ma): tilt_ret(a, ma) for a in [0.5, 1.0, 2.0] for ma in [240, 336, 480, 672]}
    n = len(price); th = 24 * 21; te = 24 * 7; st = 0; oos = []
    while st + th + te <= n:
        tr = slice(st, st + th); t2 = slice(st + th, st + th + te); best = None; bk = (-9, -9)
        for key, r in cache.items():
            mm = PF.metrics_from_returns(r.iloc[tr]); kk = (0 if mm.max_drawdown > 0.30 else 1, mm.sharpe)
            if kk > bk: bk, best = kk, key
        oos.append(cache[best].iloc[t2]); st += te
    tilt = PF.metrics_from_returns(pd.concat(oos))
    log(f"TAKER tilt OOS: ret={tilt.total_return:+.1%} sharpe={tilt.sharpe:.2f} dd={tilt.max_drawdown:.1%}")
    log("DONE")


if __name__ == "__main__":
    main()
