"""Red-team Attack #3: concentration fragility (N=2/3).

Reproduce the shipped book PnL, then perturb the candidate set:
 - drop each top name in turn
 - random name-subsets
 - rolling non-overlapping 7d windows (contest unit)
to measure single-name dependence and dispersion. Then test a robustification:
a "pumped-name exclusion" + minimum-names floor that keeps the convex tail but
caps single-name blowup.
"""
from __future__ import annotations
import sys
import numpy as np
import pandas as pd

from bnbhack_agent.strategy import combined_weights, ensemble_weights, StrategyConfig, FROZEN
from bnbhack_agent.portfolio import strategy_returns, metrics_from_returns
from bnbhack_agent.universe import load_universe, tradeable_tokens, liquid_candidates

PRICE = "src/bnbhack_agent/data/cache/price_120d.parquet"
COST = 30.0  # backtest assumed flat 30bps per the brief (cost_bps in cfg is 10; we stress at 30)


def load_price():
    p = pd.read_parquet(PRICE)
    return p


def ranked_pool(price, n=12, min_cov=0.85):
    cov = price.notna().mean()
    present = [c for c in price.columns if cov.get(c, 0) >= min_cov]
    toks = load_universe()
    trad = {t.symbol for t in tradeable_tokens(toks)}
    present_trad = [c for c in present if c in trad]
    return liquid_candidates(present_trad, n)


def book_returns(price, ranked, cfg=FROZEN, cost_bps=COST):
    w = combined_weights(price, ranked, cfg)
    return strategy_returns(price, w, cost_bps=cost_bps / 1e4 * 1e4)  # cost in bps


def book_returns_bps(price, ranked, cfg=FROZEN, cost_bps=COST):
    w = combined_weights(price, ranked, cfg)
    return strategy_returns(price, w, cost_bps=cost_bps)


def metr(ret):
    m = metrics_from_returns(ret)
    return m.total_return, m.max_drawdown, m.sharpe


def nonoverlap_7d(ret):
    """Non-overlapping 7d (168h) window returns from a per-bar return series."""
    rr = (1 + ret.fillna(0.0))
    out = []
    h = 168
    for i in range(0, len(rr) - h + 1, h):
        out.append(rr.iloc[i:i + h].prod() - 1)
    return np.array(out)


def main():
    price = load_price()
    ranked = ranked_pool(price)
    print("RANKED POOL (top-12 liquid):", ranked)
    print(f"ensemble_ns={FROZEN.ensemble_ns}  max_weight={FROZEN.max_weight}  cost={COST}bps\n")

    # baseline book
    base = book_returns_bps(price, ranked)
    tr, dd, sh = metr(base)
    w7 = nonoverlap_7d(base)
    print(f"=== BASELINE BOOK (full window) ===")
    print(f"total {tr:+.1%}  maxDD {dd:.1%}  Sharpe {sh:.2f}")
    print(f"non-overlap 7d windows: n={len(w7)} mean {w7.mean():+.2%} median {np.median(w7):+.2%} "
          f"min {w7.min():+.2%} max {w7.max():+.2%} std {w7.std():.2%}")
    print(f"7d windows < -10%: {(w7<-0.10).sum()}   > +10%: {(w7>0.10).sum()}\n")

    # --- drop-one perturbation: exclude each of the top names that actually carries weight ---
    top_active = ranked[:max(FROZEN.ensemble_ns)]  # names that ever enter the ensemble sleeves
    print(f"=== DROP-ONE (exclude each of {top_active}) ===")
    for drop in top_active:
        sub = [c for c in ranked if c != drop]
        r = book_returns_bps(price, sub)
        t, d, s = metr(r)
        ww = nonoverlap_7d(r)
        print(f"  drop {drop:5s}: total {t:+.1%} (Δ{t-tr:+.1%})  maxDD {d:.1%}  7d max {ww.max():+.2%} min {ww.min():+.2%}")
    print()

    # --- random subset perturbation: random 8 of top-12, recompute ranked order preserved ---
    print("=== RANDOM SUBSETS (drop 4 of top-12 at random, 200 draws) ===")
    rng = np.random.default_rng(7)
    tots, dds, w7maxes = [], [], []
    for _ in range(200):
        keep = sorted(rng.choice(len(ranked), size=8, replace=False))
        sub = [ranked[i] for i in keep]
        r = book_returns_bps(price, sub)
        t, d, _ = metr(r)
        tots.append(t); dds.append(d); w7maxes.append(nonoverlap_7d(r).max())
    tots = np.array(tots)
    print(f"  total return: mean {tots.mean():+.1%} median {np.median(tots):+.1%} "
          f"p10 {np.percentile(tots,10):+.1%} p90 {np.percentile(tots,90):+.1%} std {tots.std():.1%}")
    print(f"  fraction of subsets that INCLUDE ZEC vs not:")
    inc, exc = [], []
    rng2 = np.random.default_rng(7)
    for _ in range(200):
        keep = sorted(rng2.choice(len(ranked), size=8, replace=False))
        sub = [ranked[i] for i in keep]
        t = metr(book_returns_bps(price, sub))[0]
        (inc if 'ZEC' in sub else exc).append(t)
    print(f"    with ZEC (n={len(inc)}): mean {np.mean(inc):+.1%}   without ZEC (n={len(exc)}): mean {np.mean(exc):+.1%}")
    print()


if __name__ == "__main__":
    main()
