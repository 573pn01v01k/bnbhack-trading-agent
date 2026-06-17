"""R3 NOVEL #2 — BTC-breakout alt-catchup.

Hypothesis: when BTC confirms an upside breakout (new N-h high, or crosses above
its MA with positive momentum), high-beta eligible alts CATCH UP with a lag, so a
regime-ENTRY trigger that tilts INTO the basket on a fresh BTC up-break captures
asymmetric continuation.

This is index/regime-level momentum (entry timing), NOT cross-sectional momentum
(which was rejected). Everything is point-in-time and net of cost.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from bnbhack_agent.report import _candidates
from bnbhack_agent import strategy as ST
from bnbhack_agent.portfolio import metrics_from_returns, strategy_returns

CACHE = "src/bnbhack_agent/data/cache/price_120d.parquet"
HOLDOUT_BARS = 21 * 24


def load():
    px = pd.read_parquet(CACHE)
    cand = _candidates(px)
    return px, cand


def basket_returns(px, cand, cost_bps=10.0):
    """Equal-weight alt basket (no regime gate) per-bar net returns, for event study."""
    sub = px[cand]
    w = sub.notna().astype("float64")
    w = w.div(w.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    return strategy_returns(sub, w, cost_bps=cost_bps), w, sub


# ---------------------------------------------------------------------------
# 1) Point-in-time BTC breakout definitions (all known at bar t, no lookahead).
# ---------------------------------------------------------------------------
def btc_breakout_flags(px, lookbacks=(48, 72, 96)):
    btc = px["BTC"]
    out = {}
    for lb in lookbacks:
        # new lb-hour high: today's close >= max of the PRIOR lb closes (shifted, strict no-lookahead)
        prior_high = btc.shift(1).rolling(lb).max()
        out[f"newhigh_{lb}"] = (btc >= prior_high) & prior_high.notna()
    # MA cross-up with positive momentum (regime ENTRY, not just state)
    for ma in (168, 240, 336):
        above = btc > btc.rolling(ma).mean()
        cross_up = above & (~above.shift(1).fillna(False))
        out[f"crossup_{ma}"] = cross_up.fillna(False)
    return pd.DataFrame(out, index=px.index)


# ---------------------------------------------------------------------------
# 2) Event study: alt-basket forward returns conditioned on a fresh BTC breakout.
# ---------------------------------------------------------------------------
def event_study(px, cand, horizons=(6, 12, 24, 48, 96)):
    btc = px["BTC"]
    sub = px[cand]
    altew = sub.div(sub.iloc[0]).mean(axis=1)  # equal-weight alt index level (gross, for fwd ret)
    flags = btc_breakout_flags(px)
    res = {}
    # "fresh" event = flag True now but was False the previous bar (rising edge)
    for name in flags.columns:
        f = flags[name]
        fresh = f & (~f.shift(1).fillna(False))
        ev_idx = np.where(fresh.values)[0]
        row = {"n_events": int(len(ev_idx))}
        for h in horizons:
            fwd_alt, fwd_btc = [], []
            for i in ev_idx:
                if i + h < len(altew):
                    fwd_alt.append(altew.iloc[i + h] / altew.iloc[i] - 1)
                    fwd_btc.append(btc.iloc[i + h] / btc.iloc[i] - 1)
            if fwd_alt:
                fa = np.array(fwd_alt); fb = np.array(fwd_btc)
                row[f"alt_h{h}_mean"] = float(fa.mean())
                row[f"alt_h{h}_hit"] = float((fa > 0).mean())
                row[f"altMinusBtc_h{h}"] = float((fa - fb).mean())  # catch-up: alt beating BTC after?
        res[name] = row
    # baseline: unconditional forward returns over all bars (same horizons)
    base = {"n_events": len(altew)}
    for h in horizons:
        fa = (altew.shift(-h) / altew - 1).dropna().values
        fb = (btc.shift(-h) / btc - 1).dropna().values
        base[f"alt_h{h}_mean"] = float(fa.mean())
        base[f"alt_h{h}_hit"] = float((fa > 0).mean())
        m = min(len(fa), len(fb))
        base[f"altMinusBtc_h{h}"] = float((fa[:m] - fb[:m]).mean())
    res["__UNCONDITIONAL__"] = base
    return pd.DataFrame(res).T


# ---------------------------------------------------------------------------
# 3) Strategy variant: deploy basket on BTC breakout, hold H bars, cash otherwise.
#    Compare vs incumbent ensemble and vs always-on EW basket. WF + holdout, net cost.
# ---------------------------------------------------------------------------
def breakout_deploy_returns(px, cand, *, lookback=72, hold=96, cost_bps=10.0,
                            use_ensemble_book=True):
    """On a fresh BTC newhigh_lookback event, turn the book ON for `hold` bars.
    Book = either the validated ensemble weights, or plain EW basket. Cash when off."""
    flags = btc_breakout_flags(px, lookbacks=(lookback,))
    f = flags[f"newhigh_{lookback}"]
    fresh = (f & (~f.shift(1).fillna(False))).values
    # build an ON mask: 1 for `hold` bars after each fresh event (point-in-time forward fill of trigger)
    on = np.zeros(len(px), dtype=bool)
    last_on_until = -1
    for i in range(len(px)):
        if fresh[i]:
            last_on_until = i + hold
        if i <= last_on_until:
            on[i] = True
    on = pd.Series(on, index=px.index)

    if use_ensemble_book:
        base_w = ST.ensemble_weights(px, cand)  # already regime-gated + rebalanced
    else:
        sub = px[cand]
        base_w = sub.notna().astype("float64")
        base_w = base_w.div(base_w.sum(axis=1).replace(0, np.nan), axis=0).clip(upper=0.34).fillna(0.0)
    base_w = base_w.copy()
    base_w.loc[~on] = 0.0
    sub = px[base_w.columns]
    return strategy_returns(sub, base_w, cost_bps=cost_bps), on


def walk_forward_breakout(px, cand, *, cost_bps=10.0, train_h=24*21, test_h=24*7,
                          dd_cap=0.30):
    """WF over the (lookback, hold) grid: pick best Sharpe (DD-capped) on train,
    apply OOS on test. Compare stitched OOS vs incumbent ensemble on same OOS bars."""
    grid = [(lb, h) for lb in (48, 72, 96) for h in (48, 72, 96, 168)]
    ret_by = {g: breakout_deploy_returns(px, cand, lookback=g[0], hold=g[1], cost_bps=cost_bps)[0]
              for g in grid}
    ens = ST.ensemble_weights(px, cand)
    ens_ret = strategy_returns(px[ens.columns], ens, cost_bps=cost_bps)

    n = len(px); start = 0; oos_seg = []; ins = []; folds = []
    while start + train_h + test_h <= n:
        tr = slice(start, start + train_h); te = slice(start + train_h, start + train_h + test_h)
        best_g, best_key = grid[0], (-1e9, -1e9)
        for g in grid:
            m = metrics_from_returns(ret_by[g].iloc[tr])
            key = (0 if m.max_drawdown > dd_cap else 1, m.sharpe)
            if key > best_key:
                best_key, best_g = key, g
        oos_seg.append(ret_by[best_g].iloc[te])
        ins.append(metrics_from_returns(ret_by[best_g].iloc[tr]).total_return)
        folds.append(best_g)
        start += test_h
    oos = pd.concat(oos_seg)
    return oos, ens_ret.loc[oos.index], folds, ret_by


def m(r):
    x = metrics_from_returns(r)
    return {"return": round(x.total_return, 4), "sharpe": round(x.sharpe, 3),
            "max_dd": round(x.max_drawdown, 4)}


def main():
    px, cand = load()
    print("=== window", px.index[0], "->", px.index[-1], "bars", len(px), "cand", len(cand))

    print("\n=== 1) EVENT STUDY: alt-basket fwd returns after fresh BTC breakout ===")
    es = event_study(px, cand)
    pd.set_option("display.width", 200, "display.max_columns", 40)
    print(es.round(4).to_string())

    print("\n=== 2) STRATEGY VARIANT (full window) ===")
    sub = px[cand]
    ew = sub.notna().astype("float64"); ew = ew.div(ew.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    ew_ret = strategy_returns(sub, ew, cost_bps=10.0)
    ens = ST.ensemble_weights(px, cand); ens_ret = strategy_returns(px[ens.columns], ens, cost_bps=10.0)
    print("incumbent ensemble     ", m(ens_ret))
    print("always-on EW basket    ", m(ew_ret))
    print("BTC hold               ", m(px["BTC"].pct_change().fillna(0.0)))
    for lb in (48, 72, 96):
        for h in (72, 96, 168):
            r, on = breakout_deploy_returns(px, cand, lookback=lb, hold=h, use_ensemble_book=True)
            r0, _ = breakout_deploy_returns(px, cand, lookback=lb, hold=h, use_ensemble_book=False)
            print(f"breakout(lb={lb},hold={h}) ENS {m(r)}  exposure {on.mean():.2f}  | EWbook {m(r0)}")

    print("\n=== 3) WALK-FORWARD (OOS stitched) breakout-gate vs incumbent ===")
    oos, ens_oos, folds, _ = walk_forward_breakout(px, cand)
    print("breakout-gate OOS   ", m(oos), "n_bars", len(oos))
    print("incumbent OOS (same bars)", m(ens_oos))
    print("selected (lb,hold) per fold:", folds)

    print("\n=== holdout (last 21d) ===")
    for lb, h in ((72, 96), (48, 96), (96, 168)):
        r, _ = breakout_deploy_returns(px, cand, lookback=lb, hold=h, use_ensemble_book=True)
        print(f"breakout(lb={lb},hold={h}) holdout", m(r.iloc[-HOLDOUT_BARS:]))
    print("incumbent ensemble holdout", m(ens_ret.iloc[-HOLDOUT_BARS:]))

    print("\n=== cost sensitivity on best full-window breakout variant ===")
    for c in (0, 10, 20, 40):
        r, _ = breakout_deploy_returns(px, cand, lookback=72, hold=96, cost_bps=c)
        print(f"  {c}bps -> {m(r)['return']}")


if __name__ == "__main__":
    main()
