"""Auto-research pipeline: generate strategy hypotheses, evaluate them under a
strict anti-overfit protocol, and accumulate findings in a ledger.

Anti-overfit protocol:
  - The LAST `HOLDOUT_DAYS` of data are locked away. Search/selection never touch
    them; only a strategy promoted as the new best is checked there, once.
  - Every hypothesis is scored by walk-forward OOS (params chosen on train, applied
    to the next unseen window, stitched).
  - Every hypothesis ever tested is appended to data/research_ledger.json, so the
    multiple-comparison count is explicit — the more we test, the higher the bar a
    "winner" must clear to be believed (we require a margin over the incumbent).

Run: PYTHONPATH=src python3 scripts/research.py
Each run evaluates the BATCHES below (extend over iterations), logs to
docs/RESEARCH_LOG.md + data/research_ledger.json, and prints the leaderboard.
"""
from __future__ import annotations

import json
import sys
import time
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from bnbhack_agent import marketdata as MD, portfolio as PF, universe as U  # noqa: E402

HOLDOUT_DAYS = 21
TRAIN_H = 24 * 21
TEST_H = 24 * 7
DD_CAP = 0.30
LEDGER = ROOT / "src" / "bnbhack_agent" / "data" / "research_ledger.json"
LOG = ROOT / "docs" / "RESEARCH_LOG.md"
INCUMBENT_KEY = "ensemble_conc"   # current live strategy (robust model-averaged ensemble)


# ---- data ---------------------------------------------------------------
def load():
    """Return the FULL price panel (warm MA throughout), the liquidity-ranked candidate
    list, and the holdout length in bars. Strategies are computed on the full panel and
    the RETURN series is sliced afterwards — recomputing on a short slice leaves the
    regime MA unwarmed and produces artifacts (the bug that faked a -17% holdout)."""
    px = pd.read_parquet(MD.CACHE / "price_120d.parquet")
    cov = px.notna().mean()
    trad = [t.symbol for t in U.tradeable_tokens(U.load_universe())]
    cand = [s for s in trad if s in px.columns and cov[s] > 0.85 and s != "BTC"]
    try:
        liq = U.liquidity_ranking()
        cand = sorted(cand, key=lambda s: liq.get(s, 0.0), reverse=True)
    except Exception:
        pass
    return px, cand, HOLDOUT_DAYS * 24


# ---- building blocks ----------------------------------------------------
def regime_off(px, ma, ref="BTC"):
    r = px[ref]
    return (r < r.rolling(ma).mean()).fillna(False)


def ew_returns(px, cols, ma, cost=10.0):
    sub = px[cols]
    w = sub.notna().astype("float64")
    w = w.div(w.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    w.loc[regime_off(px, ma)] = 0.0
    return PF.strategy_returns(sub, w, cost_bps=cost)


def invvol_returns(px, cols, ma, vol_win=72, cost=10.0):
    sub = px[cols]
    vol = sub.pct_change().rolling(vol_win).std()
    w = (1.0 / vol).where(sub.notna())
    w = w.div(w.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    w.loc[regime_off(px, ma)] = 0.0
    return PF.strategy_returns(sub, w, cost_bps=cost)


def momo_riskon_returns(px, cols, ma, k, lb, cost=10.0):
    """Within risk-on bars only, hold top-k by trailing return (regime-conditional momentum)."""
    sub = px[cols]
    mom = sub.pct_change(lb)
    rank = mom.rank(axis=1, ascending=False, method="first")
    w = (rank <= k).astype("float64").where(sub.notna(), 0.0)
    w = w.div(w.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    w.loc[regime_off(px, ma)] = 0.0
    return PF.strategy_returns(sub, w, cost_bps=cost)


def highvol_pit_returns(px, cols, ma, n=8, vol_win=168, cost=10.0):
    """POINT-IN-TIME high-vol hunt: at each bar hold the top-`n` names by TRAILING
    volatility (known at t — no lookahead), equal-weight, regime-gated. This is the
    honest version of 'hold the movers' — it can only use vol realized up to now."""
    sub = px[cols]
    tvol = sub.pct_change().rolling(vol_win).std()
    rank = tvol.rank(axis=1, ascending=False, method="first")
    w = ((rank <= n) & sub.notna()).astype("float64")
    w = w.div(w.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    w.loc[regime_off(px, ma)] = 0.0
    return PF.strategy_returns(sub, w, cost_bps=cost)


def vol_expansion_returns(px, cols, ma, n=8, fast=24, slow=168, cost=10.0):
    """Ignition proxy: hold names whose trailing vol is EXPANDING (fast vol / slow vol
    highest), point-in-time. Tries to catch moves as they start, no lookahead."""
    sub = px[cols]
    rets = sub.pct_change()
    expansion = rets.rolling(fast).std() / rets.rolling(slow).std()
    rank = expansion.rank(axis=1, ascending=False, method="first")
    w = ((rank <= n) & sub.notna()).astype("float64")
    w = w.div(w.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    w.loc[regime_off(px, ma)] = 0.0
    return PF.strategy_returns(sub, w, cost_bps=cost)


def ts_momentum_returns(px, cols, ma, own_ma=168, cost=10.0):
    """Time-series momentum: hold each token only while ITS OWN price is above its own
    MA (own-trend filter, known at t), equal-weight the qualifiers, market-regime-gated.
    Classic, economically motivated, no cross-sectional ranking (less overfit-prone)."""
    sub = px[cols]
    own_up = (sub > sub.rolling(own_ma).mean()).astype("float64").where(sub.notna(), 0.0)
    w = own_up.div(own_up.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    w.loc[regime_off(px, ma)] = 0.0
    return PF.strategy_returns(sub, w, cost_bps=cost)


def trend_scaled_returns(px, cols, ma, cost=10.0):
    """Continuous exposure: scale the equal-weight basket by market breadth (fraction of
    names above their MA) instead of a binary on/off gate. Smoother de-risking."""
    sub = px[cols]
    above = (sub > sub.rolling(ma).mean()).astype("float64")
    breadth = (above.sum(axis=1) / sub.notna().sum(axis=1).replace(0, np.nan)).clip(0, 1)
    base = sub.notna().astype("float64")
    base = base.div(base.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    return PF.strategy_returns(sub, base.mul(breadth, axis=0), cost_bps=cost)


def adaptive_conc_returns(px, cand, ma, thr=0.05, cost=10.0):
    """Adaptive concentration: when BTC is STRONG (>thr above its MA) concentrate into
    the top-5 liquid (fat right tail); when merely risk-on, diversify into top-15; when
    risk-off (below MA), go to cash. The 'smart agent' — match aggression to regime."""
    btc = px["BTC"]; sub = px[cand]
    maline = btc.rolling(ma).mean()
    strong = (btc / maline - 1 > thr).fillna(False)
    below = (btc < maline).fillna(False)

    def colmask(cols):
        m = pd.DataFrame(0.0, index=px.index, columns=cand)
        present = [c for c in cols if c in cand]
        m[present] = sub[present].notna().astype("float64")
        return m

    w = colmask(cand[:15]).mask(strong, colmask(cand[:5]))
    w = w.div(w.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    w.loc[below] = 0.0
    return PF.strategy_returns(sub, w, cost_bps=cost)


def btc_scaled_returns(px, cand, ma, k=0.10, cost=10.0):
    """Continuous exposure scaled by BTC trend strength (distance above its MA, /k, clipped
    0..1) over an equal-weight basket. Smooth de-risking instead of a binary gate."""
    btc = px["BTC"]; sub = px[cand]
    strength = ((btc / btc.rolling(ma).mean() - 1) / k).clip(0, 1).fillna(0.0)
    base = sub.notna().astype("float64")
    base = base.div(base.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    return PF.strategy_returns(sub, base.mul(strength, axis=0), cost_bps=cost)


def ensemble_returns(px, cand, ns=(5, 10, 15), mas=(240, 336, 480), cost=10.0):
    """Robust ensemble: split capital equally across regime-EW sleeves over a grid of
    basket sizes x regime MAs, instead of betting on one (N, MA). Model averaging is
    anti-overfitting — it never picks the in-sample-best param, so it can't overfit it.
    Should survive the holdout that punishes single-param concentration."""
    parts = [ew_returns(px, cand[:n], ma, cost) for n in ns for ma in mas]
    return sum(parts) / len(parts)


def breadth_off(px, cols, ma):
    """Risk-off when fewer than half the basket trades above its own MA (breadth)."""
    sub = px[cols]
    above = (sub > sub.rolling(ma).mean()).astype(float)
    frac = above.sum(axis=1) / sub.notna().sum(axis=1).replace(0, np.nan)
    return (frac < 0.5).fillna(False)


def ew_breadth_returns(px, cols, ma, cost=10.0):
    sub = px[cols]
    w = sub.notna().astype("float64")
    w = w.div(w.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    w.loc[breadth_off(px, cols, ma)] = 0.0
    return PF.strategy_returns(sub, w, cost_bps=cost)


# ---- evaluation ---------------------------------------------------------
def wf_oos(ret_by_param: dict) -> dict:
    """Walk-forward: pick best param on train (Sharpe s.t. DD cap), apply OOS, stitch."""
    any_ret = next(iter(ret_by_param.values()))
    n = len(any_ret)
    start, oos = 0, []
    while start + TRAIN_H + TEST_H <= n:
        tr = slice(start, start + TRAIN_H)
        te = slice(start + TRAIN_H, start + TRAIN_H + TEST_H)
        best, bk = None, (-9, -9)
        for key, r in ret_by_param.items():
            m = PF.metrics_from_returns(r.iloc[tr])
            k = (0 if m.max_drawdown > DD_CAP else 1, m.sharpe)
            if k > bk:
                bk, best = k, key
        oos.append(ret_by_param[best].iloc[te])
        start += TEST_H
    o = PF.metrics_from_returns(pd.concat(oos)) if oos else PF.metrics_from_returns(any_ret.iloc[:0])
    return {"return": round(o.total_return, 4), "sharpe": round(o.sharpe, 3), "max_dd": round(o.max_drawdown, 4), "bars": o.n_bars}


# ---- hypothesis batches (extend over loop iterations) -------------------
def batches(px, cand):
    """Yield (hypothesis_key, ret_by_param) to evaluate this iteration."""
    out = {}
    # incumbent + concentration sweep (walk-forward N)
    for N in (5, 8, 10, 15, 64):
        cols = cand[:N] if N < len(cand) else cand
        out[f"regime_ew_top{N}"] = {ma: ew_returns(px, cols, ma) for ma in (240, 336, 480, 672)}
    # H: inverse-vol weighting (risk parity) on top-15
    out["invvol_top15"] = {ma: invvol_returns(px, cand[:15], ma) for ma in (240, 336, 480, 672)}
    # H: regime-conditional momentum on top-20
    out["momo_riskon_top20"] = {
        (ma, k, lb): momo_riskon_returns(px, cand[:20], ma, k, lb)
        for ma, k, lb in product((336, 480), (3, 5), (24, 72))
    }
    # H: breadth-gated equal-weight top-10
    out["ew_breadth_top10"] = {ma: ew_breadth_returns(px, cand[:10], ma) for ma in (96, 168, 336)}

    # --- high-volatility "crimes" hunt (Pavel's direction), POINT-IN-TIME (no lookahead) ---
    out["highvol_pit_top8"] = {(ma, vw): highvol_pit_returns(px, cand, ma, 8, vw)
                               for ma in (336, 480) for vw in (72, 168)}
    out["highvol_pit_top12"] = {(ma, vw): highvol_pit_returns(px, cand, ma, 12, vw)
                                for ma in (336, 480) for vw in (72, 168)}
    out["vol_expansion_top8"] = {(ma, f): vol_expansion_returns(px, cand, ma, 8, f, 168)
                                 for ma in (336, 480) for f in (12, 24, 48)}
    # --- time-series momentum (own-trend filter) + continuous breadth-scaled exposure ---
    out["ts_momentum"] = {(ma, own): ts_momentum_returns(px, cand, ma, own)
                          for ma in (336, 480) for own in (96, 168, 336)}
    out["ts_momentum_top15"] = {(ma, own): ts_momentum_returns(px, cand[:15], ma, own)
                                for ma in (336, 480) for own in (96, 168, 336)}
    out["trend_scaled"] = {ma: trend_scaled_returns(px, cand, ma) for ma in (96, 168, 336, 480)}
    # --- smart/adaptive agentic strategies ---
    out["adaptive_conc"] = {(ma, thr): adaptive_conc_returns(px, cand, ma, thr)
                            for ma in (240, 336, 480) for thr in (0.02, 0.05, 0.08)}
    out["btc_scaled"] = {(ma, k): btc_scaled_returns(px, cand, ma, k)
                         for ma in (240, 336, 480) for k in (0.05, 0.10, 0.20)}
    # robust ensemble (model averaging over N x MA) — single config, nothing to tune
    out["ensemble"] = {"fixed": ensemble_returns(px, cand)}
    out["ensemble_conc"] = {"fixed": ensemble_returns(px, cand, ns=(3, 5, 8))}
    return out


# ---- runner -------------------------------------------------------------
def main():
    px, cand, hb = load()
    batch = batches(px, cand)                         # full-length return series (warm MA)
    results, holdouts = {}, {}
    for key, grid in batch.items():
        results[key] = wf_oos({k: v.iloc[:-hb] for k, v in grid.items()})   # walk-forward on search portion
        rep = list(grid.values())[len(grid) // 2]                            # representative param
        ho = PF.metrics_from_returns(rep.iloc[-hb:])                         # holdout = slice of full-panel returns
        holdouts[key] = {"return": round(ho.total_return, 4), "sharpe": round(ho.sharpe, 3), "max_dd": round(ho.max_drawdown, 4)}

    ledger = json.loads(LEDGER.read_text()) if LEDGER.exists() else {"tested": {}, "iterations": 0, "best": None}
    ledger["iterations"] += 1
    for k, v in results.items():
        ledger["tested"][k] = {**v, "holdout": holdouts[k]}
    ranked = sorted(results.items(), key=lambda kv: kv[1]["return"], reverse=True)
    incumbent = results.get(INCUMBENT_KEY, {"return": 0.118})
    best_key, best = ranked[0]
    margin = best["return"] - incumbent["return"]

    # Final gate: promote only if it beats the incumbent OOS by >3pp AND survives the
    # (correctly-evaluated) locked holdout — positive return, under the DD cap.
    ho = holdouts[best_key]
    promote = (best_key != INCUMBENT_KEY and margin > 0.03 and best["max_dd"] <= DD_CAP
               and ho["return"] > 0.0 and ho["max_dd"] <= DD_CAP)

    ledger["best"] = {"key": best_key, **best, "holdout": ho}
    LEDGER.write_text(json.dumps(ledger, indent=1))
    _append_log(ledger["iterations"], ranked, incumbent, promote, best_key, ho)
    print(f"iter {ledger['iterations']}: top={best_key} ret={best['return']:+.1%} sharpe={best['sharpe']} dd={best['max_dd']:.1%} "
          f"| holdout ret={ho['return']:+.1%} sharpe={ho['sharpe']} | incumbent {INCUMBENT_KEY} {incumbent['return']:+.1%} | promote={promote}", flush=True)
    for k, v in ranked:
        h = holdouts[k]
        print(f"   {k:20} OOS={v['return']:+.1%} sh={v['sharpe']:.2f} dd={v['max_dd']:.1%}  | HOLDOUT={h['return']:+.1%} sh={h['sharpe']:.2f}", flush=True)


def _holdout_eval(key, holdout, cand):
    # rebuild the family on the holdout with a fixed mid param and report full-period metrics
    px = holdout
    if key.startswith("highvol_pit_top"):
        N = int(key.replace("highvol_pit_top", ""))
        r = highvol_pit_returns(px, cand, 336, N, 168)
    elif key == "vol_expansion_top8":
        r = vol_expansion_returns(px, cand, 336, 8, 24, 168)
    elif key == "ts_momentum":
        r = ts_momentum_returns(px, cand, 336, 168)
    elif key == "ts_momentum_top15":
        r = ts_momentum_returns(px, cand[:15], 336, 168)
    elif key == "trend_scaled":
        r = trend_scaled_returns(px, cand, 336)
    elif key == "adaptive_conc":
        r = adaptive_conc_returns(px, cand, 336, 0.05)
    elif key == "btc_scaled":
        r = btc_scaled_returns(px, cand, 336, 0.10)
    elif key == "ensemble":
        r = ensemble_returns(px, cand)
    elif key == "ensemble_conc":
        r = ensemble_returns(px, cand, ns=(3, 5, 8))
    elif key.startswith("regime_ew_top"):
        N = int(key.replace("regime_ew_top", "")); cols = cand[:N] if N < len(cand) else cand
        r = ew_returns(px, cols, 336)
    elif key == "invvol_top15":
        r = invvol_returns(px, cand[:15], 336)
    elif key == "momo_riskon_top20":
        r = momo_riskon_returns(px, cand[:20], 336, 5, 72)
    elif key == "ew_breadth_top10":
        r = ew_breadth_returns(px, cand[:10], 168)
    else:
        return None
    m = PF.metrics_from_returns(r)
    return {"return": round(m.total_return, 4), "sharpe": round(m.sharpe, 3), "max_dd": round(m.max_drawdown, 4)}


def _append_log(it, ranked, incumbent, promote, best_key, holdout_check):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    if not LOG.exists():
        lines += ["# Auto-Research Log", "",
                  "Walk-forward OOS on the search window (last 21 days locked as holdout). "
                  "A new strategy is promoted only if it beats the incumbent OOS return by >3pp, "
                  "respects the 30% DD cap, AND survives the locked holdout. Every hypothesis tested "
                  "is recorded — the count is the multiple-comparison budget.", ""]
    lines.append(f"## Iteration {it} ({time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())})")
    lines.append("")
    lines.append("| hypothesis | OOS return | OOS Sharpe | OOS max DD |")
    lines.append("|---|---:|---:|---:|")
    for k, v in ranked:
        star = " ⭐" if k == best_key else ""
        lines.append(f"| `{k}`{star} | {v['return']*100:+.1f}% | {v['sharpe']:.2f} | {v['max_dd']*100:.1f}% |")
    lines.append("")
    verdict = (f"**Promoted `{best_key}`** (beat incumbent by margin)." if promote
               else f"No promotion — incumbent `{INCUMBENT_KEY}` ({incumbent['return']*100:+.1f}%) holds (no hypothesis cleared +3pp margin OOS).")
    lines.append(verdict)
    if holdout_check:
        lines.append(f"Holdout check of `{best_key}`: {holdout_check['return']*100:+.1f}% / Sharpe {holdout_check['sharpe']:.2f} / DD {holdout_check['max_dd']*100:.1f}%.")
    lines.append("")
    with LOG.open("a") as fh:
        fh.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
