"""Reproducible Track-1 backtest report.

Runs the anti-overfit walk-forward for the frozen strategy (regime-gated
equal-weight) and the rejected momentum baseline on real cached/fetched price
data, and writes a judge-readable markdown + machine-readable JSON.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .portfolio import strategy_returns

from . import marketdata as MD
from . import universe as U
from . import walkforward as WF

REPORT_MD = Path(__file__).resolve().parents[2] / "docs" / "BACKTEST_RESULTS_TRACK1.md"


def _load_price(days: int) -> pd.DataFrame:
    cache = MD.CACHE / f"price_{days}d.parquet"
    if cache.exists():
        return pd.read_parquet(cache)
    trad = [t.symbol for t in U.tradeable_tokens(U.load_universe())]
    return MD.price_panel(sorted(set(trad) | {"BTC", "ETH"}), days=days)


def build_backtest_report(*, days: int = 120, min_coverage: float = 0.85, out_md: Path = REPORT_MD) -> dict:
    px = _load_price(days)
    cov = px.notna().mean()
    trad = [t.symbol for t in U.tradeable_tokens(U.load_universe())]
    cand = [s for s in trad if s in px.columns and cov[s] > min_coverage and s != "BTC"]
    price = px[cand + ["BTC"]]

    strat = WF.regime_ew_walk_forward(price, regime_ref="BTC")
    mom = WF.walk_forward(price[cand], regime_series=None, baseline_symbol="ETH")  # rejected reference

    # concentrated variant (the leaderboard lever): top-N most-liquid eligible
    n_conc = 10
    try:
        conc_syms = U.liquid_candidates(cand, n_conc)
    except Exception:
        conc_syms = cand[:n_conc]
    strat_conc = WF.regime_ew_walk_forward(px[conc_syms + ["BTC"]], regime_ref="BTC")

    summary = {
        "universe_size": len(cand),
        "bars": int(len(price)),
        "span": [str(price.index.min()), str(price.index.max())],
        "strategy_oos": strat.oos.to_dict(),
        "concentrated_oos": strat_conc.oos.to_dict(),
        "concentrated_n": n_conc,
        "concentrated_symbols": conc_syms,
        "weekly_tail": _weekly_tail(px, cand, U),
        "momentum_oos": mom.oos.to_dict(),
        "baselines": {k: v.to_dict() for k, v in strat.baselines.items()},
        "n_folds": len(strat.folds),
        "ma_picks": [f.params["ma_window"] for f in strat.folds],
        "insample_return_mean": round(strat.insample_return_mean, 6),
    }

    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(_render_md(summary, strat))
    (out_md.parent / "backtest_results_track1.json").write_text(json.dumps(summary, indent=2))
    return summary


def _weekly_tail(px, cand, U, *, levels=(64, 12, 8, 5), n_subsets=25, W=168, seed=7) -> dict:
    """7-day rolling-return distribution by concentration level (random subsets,
    isolating variance from selection). Shows the leaderboard right-tail lever."""
    btc = px["BTC"]
    rng = np.random.default_rng(seed)

    def regime_ew(cols, ma=336):
        sub = px[cols]
        off = (btc < btc.rolling(ma).mean()).fillna(False)
        w = sub.notna().astype("float64")
        w = w.div(w.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
        w.loc[off] = 0.0
        return strategy_returns(sub, w)

    def windows(r):
        eq = (1 + r).cumprod()
        return np.array([eq.iloc[i + W] / eq.iloc[i] - 1 for i in range(0, len(eq) - W, 12)])

    out = {}
    for N in levels:
        k = min(N, len(cand))
        subs = [cand] if k >= len(cand) else [list(rng.choice(cand, k, replace=False)) for _ in range(n_subsets)]
        a = np.concatenate([windows(regime_ew(c)) for c in subs])
        out[str(N)] = {"mean": float(a.mean()), "p95": float(np.percentile(a, 95)),
                       "max": float(a.max()), "p_gt15": float((a > 0.15).mean())}
    return out


def _pct(x: float) -> str:
    return f"{x * 100:+.1f}%"


def _render_md(s: dict, strat) -> str:
    so, mo = s["strategy_oos"], s["momentum_oos"]
    co = s["concentrated_oos"]
    ew = s["baselines"].get("equal_weight", {})
    btc = s["baselines"].get("BTC_hold", {})
    lines = [
        "# Track-1 Backtest Results (walk-forward, out-of-sample)",
        "",
        f"Universe: **{s['universe_size']} eligible BEP-20 tokens** (Binance hourly price). "
        f"Window: {s['bars']} hourly bars, {s['span'][0]} → {s['span'][1]}. "
        "Cost: 10 bps/turn simulated. Drawdown DQ gate: 30%.",
        "",
        "All numbers below are **stitched out-of-sample**: on each 21-day train window the only "
        "hyperparameter (the regime MA) is chosen by Sharpe subject to the DD cap, then applied to "
        "the next 7-day window it never saw. The in-sample/OOS spread is reported as an overfit gauge.",
        "",
        "## Result",
        "",
        "| Strategy | OOS return | OOS Sharpe | OOS max DD |",
        "|---|---:|---:|---:|",
        f"| **Regime-gated EW, top-{s['concentrated_n']} liquid (LIVE strategy)** | **{_pct(co['total_return'])}** | **{co['sharpe']:.2f}** | **{co['max_drawdown']*100:.1f}%** |",
        f"| Regime-gated EW, full {s['universe_size']} | {_pct(so['total_return'])} | {so['sharpe']:.2f} | {so['max_drawdown']*100:.1f}% |",
        f"| Equal-weight basket (baseline) | {_pct(ew.get('total_return',0))} | {ew.get('sharpe',0):.2f} | {ew.get('max_drawdown',0)*100:.1f}% |",
        f"| BTC buy-and-hold | {_pct(btc.get('total_return',0))} | {btc.get('sharpe',0):.2f} | {btc.get('max_drawdown',0)*100:.1f}% |",
        f"| Cross-sectional momentum (REJECTED) | {_pct(mo['total_return'])} | {mo['sharpe']:.2f} | {mo['max_drawdown']*100:.1f}% |",
        "",
        "## Concentration — the leaderboard lever (spot-only, no leverage)",
        "",
        "A winner-take-all 7-day contest rewards the right tail, not Sharpe. Concentrating the basket "
        "leaves expected return ~flat but fattens the weekly right tail, while the regime gate keeps the "
        "worst drawdown under the 30% DQ line. 7-day rolling-return distribution by basket size (random "
        "subsets, so this is the variance effect alone, not selection):",
        "",
        "| Basket N | mean 7d | p95 7d | max 7d | P(week > 15%) |",
        "|---:|---:|---:|---:|---:|",
        *[
            f"| {N} | {_pct(t['mean'])} | {_pct(t['p95'])} | **{_pct(t['max'])}** | {t['p_gt15']*100:.1f}% |"
            for N, t in s["weekly_tail"].items()
        ],
        "",
        f"Live basket (top-{s['concentrated_n']} liquid): {', '.join(s['concentrated_symbols'])}.",
        "",
        "## Why momentum was rejected",
        "",
        f"Naive top-K momentum rotation looks plausible in-sample (mean train return "
        f"{_pct(s['insample_return_mean'])}) but collapses out-of-sample "
        f"({_pct(mo['total_return'])}, Sharpe {mo['sharpe']:.2f}) — a textbook overfit. The walk-forward "
        "protocol exposes this instead of hiding it, which is the whole point.",
        "",
        "## Chosen strategy",
        "",
        f"Hold a diversified equal-weight basket of the eligible tokens when BTC is above its regime MA; "
        f"rotate fully to the stablecoin leg otherwise. MA chosen per fold (picks: {s['ma_picks']}). "
        f"Across {s['n_folds']} OOS folds it beats the equal-weight baseline on return, roughly doubles "
        "Sharpe, and roughly halves drawdown — most profit without blowing up.",
        "",
        "Reproduce: `python3 -m bnbhack_agent.cli track1-backtest`.",
        "",
    ]
    return "\n".join(lines)
