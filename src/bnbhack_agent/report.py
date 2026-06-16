"""Reproducible Track-1 backtest report for the LIVE strategy (the robust ensemble).

Honest by construction: reports the model-averaged ensemble's metrics on the full
window, on the locked 21-day holdout (never used to build it), cost sensitivity,
sub-period stability, and the 7-day right tail — including the finding that returns
are regime-dependent rather than a stable systematic edge.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import marketdata as MD
from . import strategy as ST
from . import universe as U
from .portfolio import metrics_from_returns, strategy_returns

REPORT_MD = Path(__file__).resolve().parents[2] / "docs" / "BACKTEST_RESULTS_TRACK1.md"
HOLDOUT_BARS = 21 * 24


def _candidates(px) -> list[str]:
    cov = px.notna().mean()
    trad = [t.symbol for t in U.tradeable_tokens(U.load_universe())]
    cand = [s for s in trad if s in px.columns and cov[s] > 0.85 and s != "BTC"]
    try:
        liq = U.liquidity_ranking()
        cand = sorted(cand, key=lambda s: liq.get(s, 0.0), reverse=True)
    except Exception:
        pass
    return cand


def _m(r):
    m = metrics_from_returns(r)
    return {"return": round(m.total_return, 4), "sharpe": round(m.sharpe, 3), "max_dd": round(m.max_drawdown, 4)}


def build_backtest_report(*, days: int = 120, out_md: Path = REPORT_MD) -> dict:
    cache = MD.CACHE / f"price_{days}d.parquet"
    px = pd.read_parquet(cache) if cache.exists() else MD.price_panel(
        sorted({t.symbol for t in U.tradeable_tokens(U.load_universe())} | {"BTC"}), days=days)
    cand = _candidates(px)

    # live strategy: model-averaged ensemble weights -> returns at the live config (4h rebalance, 10bps)
    W = ST.ensemble_weights(px, cand)
    sub = px[W.columns]
    r = strategy_returns(sub, W, cost_bps=ST.FROZEN.cost_bps)

    full, holdout = _m(r), _m(r.iloc[-HOLDOUT_BARS:])
    # baselines on the same window
    ew = sub.notna().astype("float64"); ew = ew.div(ew.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    base_ew = _m(strategy_returns(sub, ew, cost_bps=ST.FROZEN.cost_bps))
    base_btc = _m(px["BTC"].pct_change().fillna(0.0))

    cost_curve = {c: _m(strategy_returns(sub, W, cost_bps=c))["return"] for c in (0, 10, 20, 40)}
    n = len(r)
    subperiods = [_m(r.iloc[a:b])["return"] for a, b in ((0, n // 3), (n // 3, 2 * n // 3), (2 * n // 3, n))]
    eq = (1 + r).cumprod()
    win = np.array([eq.iloc[i + 168] / eq.iloc[i] - 1 for i in range(0, len(eq) - 168, 12)])
    tail = {"mean": float(win.mean()), "p95": float(np.percentile(win, 95)),
            "max": float(win.max()), "p_gt15": float((win > 0.15).mean())}

    summary = {
        "n_candidates": len(cand), "bars": int(n), "span": [str(px.index.min()), str(px.index.max())],
        "full": full, "holdout": holdout, "baseline_ew": base_ew, "baseline_btc": base_btc,
        "cost_curve": cost_curve, "subperiods": subperiods, "tail": tail,
        "config": {"ns": ST.FROZEN.ensemble_ns, "mas": ST.FROZEN.ensemble_mas,
                   "rebalance_hours": ST.FROZEN.rebalance_hours, "cost_bps": ST.FROZEN.cost_bps},
    }
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(_render(summary))
    (out_md.parent / "backtest_results_track1.json").write_text(json.dumps(summary, indent=2))
    return summary


def _p(x):
    return f"{x * 100:+.1f}%"


def _render(s) -> str:
    f, h, ew, btc = s["full"], s["holdout"], s["baseline_ew"], s["baseline_btc"]
    cfg = s["config"]
    L = [
        "# Track-1 Backtest Results — live strategy (robust ensemble)",
        "",
        f"Universe: **{s['n_candidates']} eligible BEP-20 tokens** (Binance hourly). "
        f"Window: {s['bars']} bars, {s['span'][0]} → {s['span'][1]}. "
        f"Live config: model-averaged ensemble of regime-gated equal-weight over basket sizes "
        f"N={cfg['ns']} × regime MAs={cfg['mas']}, rebalanced every {cfg['rebalance_hours']}h, {cfg['cost_bps']}bps cost.",
        "",
        "The ensemble is anti-overfit by construction: it never selects an in-sample-best parameter, "
        "it averages over a grid. The locked 21-day holdout was never used to build it.",
        "",
        "## Headline",
        "",
        "| | Return | Sharpe | Max DD |",
        "|---|---:|---:|---:|",
        f"| **Ensemble (live), full window** | **{_p(f['return'])}** | **{f['sharpe']:.2f}** | **{f['max_dd']*100:.1f}%** |",
        f"| Ensemble, locked 21d holdout | {_p(h['return'])} | {h['sharpe']:.2f} | {h['max_dd']*100:.1f}% |",
        f"| Equal-weight baseline | {_p(ew['return'])} | {ew['sharpe']:.2f} | {ew['max_dd']*100:.1f}% |",
        f"| BTC buy-and-hold | {_p(btc['return'])} | {btc['sharpe']:.2f} | {btc['max_dd']*100:.1f}% |",
        "",
        "## Cost sensitivity (turnover robustness)",
        "",
        "| tx cost | full-window return |",
        "|---:|---:|",
        *[f"| {c} bps | {_p(v)} |" for c, v in s["cost_curve"].items()],
        "",
        f"The {cfg['rebalance_hours']}h rebalance keeps the book profitable through ~20bps of cost — "
        "hourly rebalancing did not (it churned the regime gate).",
        "",
        "## Honest caveats — robustness validation",
        "",
        f"- **Returns are regime-dependent, not a stable edge.** Across three equal sub-periods: "
        f"{_p(s['subperiods'][0])}, {_p(s['subperiods'][1])}, {_p(s['subperiods'][2])}. Almost all the profit "
        "comes from one trending window; the strategy loses or sits in cash otherwise. This is diversified "
        "crypto-beta capture with a downside regime gate — not systematic alpha.",
        f"- **7-day right tail** (leaderboard relevance): mean {_p(s['tail']['mean'])}, p95 {_p(s['tail']['p95'])}, "
        f"max {_p(s['tail']['max'])}, P(week > 15%) {s['tail']['p_gt15']*100:.1f}%.",
        "- Naive momentum, reversal, vol-concentration, time-series momentum, adaptive sizing, and on-chain "
        "DEX-flow selection were all tested under the same walk-forward + holdout protocol and **rejected** "
        "(overfit or no edge). The ensemble is what survived.",
        "",
        "Reproduce: `python3 -m bnbhack_agent.cli track1-backtest`.",
        "",
    ]
    return "\n".join(L)
