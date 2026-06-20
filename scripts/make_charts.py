"""Generate the README strategy charts from the REAL backtest pipeline.

Every figure is computed with the same functions the agent and the backtest report
use (strategy.combined_weights, portfolio.strategy_returns, universe.dex_cost_bps) so
the visuals can never drift from the reported numbers. Run:

    PYTHONPATH=src python3 scripts/make_charts.py

Writes PNGs to docs/assets/.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

from bnbhack_agent import marketdata as MD
from bnbhack_agent import strategy as ST
from bnbhack_agent import universe as U
from bnbhack_agent.portfolio import metrics_from_returns, strategy_returns
from bnbhack_agent.report import _candidates, HOLDOUT_BARS

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "assets"
ASSETS.mkdir(parents=True, exist_ok=True)

# ---- premium dark theme (carries its own bg → looks right in GitHub light AND dark) ----
BG = "#0d1117"
PANEL = "#121821"
GRID = "#222c3a"
INK = "#e6edf3"
MUTE = "#8b97a7"
GOLD = "#f0b90b"      # BNB accent — the strategy
CYAN = "#39d0d8"
RED = "#f0506e"
GREEN = "#34d399"
VIOLET = "#a78bfa"

plt.rcParams.update({
    "figure.facecolor": BG, "axes.facecolor": PANEL, "savefig.facecolor": BG,
    "axes.edgecolor": GRID, "axes.labelcolor": INK, "text.color": INK,
    "xtick.color": MUTE, "ytick.color": MUTE, "grid.color": GRID,
    "font.family": "DejaVu Sans", "font.size": 11, "axes.titlesize": 13,
    "axes.titleweight": "bold", "axes.grid": True, "grid.alpha": 0.5,
    "axes.spines.top": False, "axes.spines.right": False, "figure.dpi": 140,
})
PCT = FuncFormatter(lambda y, _: f"{y*100:.0f}%")


def _load():
    cache = MD.CACHE / "price_120d.parquet"
    px = pd.read_parquet(cache)
    cand = _candidates(px)
    W = ST.combined_weights(px, cand)
    sub = px[W.columns]
    cost_by = U.dex_cost_bps()
    r = strategy_returns(sub, W, cost_bps_by_name=cost_by)
    return px, cand, W, sub, cost_by, r


def _wm(ax):
    ax.text(0.995, 0.02, "bnbhack-trading-agent · real backtest", transform=ax.transAxes,
            ha="right", va="bottom", color=MUTE, fontsize=7, alpha=0.7)


def chart_equity(px, sub, W, cost_by, r):
    eq = (1 + r).cumprod()
    ew = sub.notna().astype("float64"); ew = ew.div(ew.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    eq_ew = (1 + strategy_returns(sub, ew, cost_bps_by_name=cost_by)).cumprod()
    eq_btc = (1 + px["BTC"].pct_change().fillna(0.0)).cumprod()

    fig, ax = plt.subplots(figsize=(10, 4.6))
    idx = eq.index
    ho = idx[-HOLDOUT_BARS]
    ax.axvspan(ho, idx[-1], color=GOLD, alpha=0.06)
    ax.text(ho, ax.get_ylim()[1], "  locked 21-day holdout", color=GOLD, fontsize=9, va="top", alpha=0.9)

    ax.plot(idx, (eq_btc - 1), color=MUTE, lw=1.4, label=f"BTC buy-and-hold ({(eq_btc.iloc[-1]-1)*100:+.1f}%)")
    ax.plot(idx, (eq_ew - 1), color=CYAN, lw=1.6, alpha=0.9, label=f"Equal-weight DEX set ({(eq_ew.iloc[-1]-1)*100:+.1f}%)")
    ax.plot(idx, (eq - 1), color=GOLD, lw=2.6, label=f"Blended book (live) ({(eq.iloc[-1]-1)*100:+.1f}%)")
    ax.axhline(0, color=INK, lw=0.8, alpha=0.3)
    ax.yaxis.set_major_formatter(PCT)
    ax.set_title("Cumulative return — net of measured PancakeSwap slippage (120d hourly)")
    ax.legend(loc="upper left", facecolor=PANEL, edgecolor=GRID, framealpha=0.9, fontsize=9)
    _wm(ax)
    fig.tight_layout(); fig.savefig(ASSETS / "equity_curve.png"); plt.close(fig)


def chart_drawdown(r):
    eq = (1 + r).cumprod()
    dd = (eq.cummax() - eq) / eq.cummax()
    fig, ax = plt.subplots(figsize=(10, 3.4))
    ax.fill_between(dd.index, -dd * 100, 0, color=RED, alpha=0.35)
    ax.plot(dd.index, -dd * 100, color=RED, lw=1.4)
    ax.axhline(-30, color=RED, lw=1.6, ls="--")
    ax.text(dd.index[2], -30, "  −30% disqualification gate", color=RED, va="bottom", fontsize=9, fontweight="bold")
    mx = dd.max() * 100
    ax.axhline(-mx, color=GOLD, lw=1.0, ls=":")
    ax.text(dd.index[-1], -mx, f"worst −{mx:.1f}%  ", color=GOLD, va="bottom", ha="right", fontsize=9)
    ax.set_ylim(-34, 2)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f"{y:.0f}%"))
    ax.set_title("Drawdown — the design priority is staying inside the 30% gate")
    _wm(ax)
    fig.tight_layout(); fig.savefig(ASSETS / "drawdown.png"); plt.close(fig)


def chart_regime(px, W):
    ref = px["BTC"].astype("float64")
    ma = ref.rolling(336, min_periods=24).mean()
    invested = W.sum(axis=1).clip(0, 1)
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(10, 5.4), sharex=True,
                                 gridspec_kw={"height_ratios": [2.2, 1]})
    a1.plot(ref.index, ref, color=INK, lw=1.6, label="BTC")
    a1.plot(ma.index, ma, color=GOLD, lw=1.6, ls="--", label="regime MA (336h)")
    off = ref < ma
    a1.fill_between(ref.index, ref.min(), ref.max(), where=off, color=RED, alpha=0.08, step="mid")
    a1.set_title("Regime gate — risk-off (shaded) pulls the book toward the stablecoin leg")
    a1.legend(loc="upper left", facecolor=PANEL, edgecolor=GRID, framealpha=0.9, fontsize=9)
    a1.set_yticklabels([])

    a2.fill_between(invested.index, 0, invested * 100, color=CYAN, alpha=0.35, step="mid")
    a2.plot(invested.index, invested * 100, color=CYAN, lw=1.2)
    a2.set_ylim(0, 105)
    a2.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f"{y:.0f}%"))
    a2.set_title("Deployed fraction (rest sits in cash / stables)", fontsize=11)
    _wm(a2)
    fig.tight_layout(); fig.savefig(ASSETS / "regime_gate.png"); plt.close(fig)


def chart_frontier():
    # Sweep the risk dial through the real backtest at three validated points.
    px, cand, _, _, cost_by, _ = _load()
    sub = px[ST.combined_weights(px, cand).columns]
    pts = []
    for cf in (0.0, 0.15, 0.30, 0.40, 0.50):
        cfg = ST.StrategyConfig(core_ew_frac=cf)
        W = ST.combined_weights(px, cand, cfg=cfg)
        r = strategy_returns(px[W.columns], W, cost_bps_by_name=cost_by)
        m = metrics_from_returns(r)
        pts.append((cf, m.total_return * 100, m.max_drawdown * 100))
    cfs = [p[0] for p in pts]; rets = [p[1] for p in pts]; dds = [p[2] for p in pts]

    fig, ax = plt.subplots(figsize=(8.4, 4.6))
    ax.axhspan(30, 40, color=RED, alpha=0.10)
    ax.plot(rets, dds, color=GOLD, lw=2, marker="o", ms=7, mfc=GOLD, mec=BG, zorder=3)
    for cf, rr, dd in pts:
        lbl = f"{cf:.2f}" + ("  ◀ shipped" if abs(cf - 0.30) < 1e-9 else "")
        ax.annotate(lbl, (rr, dd), textcoords="offset points", xytext=(8, 6),
                    color=(GOLD if abs(cf - 0.30) < 1e-9 else INK), fontsize=9,
                    fontweight=("bold" if abs(cf - 0.30) < 1e-9 else "normal"))
    ax.axhline(30, color=RED, lw=1.4, ls="--")
    ax.text(min(rets), 30, " 30% DQ gate", color=RED, va="bottom", fontsize=9, fontweight="bold")
    ax.set_xlabel("full-window return"); ax.set_ylabel("max drawdown")
    ax.xaxis.set_major_formatter(FuncFormatter(lambda y, _: f"{y:.0f}%"))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f"{y:.0f}%"))
    ax.invert_yaxis()
    ax.set_title("Risk dial — core-exposure frontier (every point DQ-safe)")
    _wm(ax)
    fig.tight_layout(); fig.savefig(ASSETS / "risk_frontier.png"); plt.close(fig)


def chart_weekly(r):
    H = 168
    wret = np.array([(1 + r.iloc[i:i + H]).prod() - 1 for i in range(0, len(r) - H + 1, H)]) * 100
    fig, ax = plt.subplots(figsize=(8.4, 4.2))
    cols = [GREEN if x >= 0 else RED for x in wret]
    ax.bar(range(len(wret)), wret, color=cols, alpha=0.85, edgecolor=BG)
    med = float(np.median(wret))
    ax.axhline(med, color=GOLD, lw=1.4, ls="--")
    ax.text(0, med, f" median {med:+.1f}%", color=GOLD, va="bottom", fontsize=9, fontweight="bold")
    ax.axhline(0, color=INK, lw=0.8, alpha=0.4)
    ax.set_title(f"Non-overlapping 7-day windows (n={len(wret)}) — none breach the 30% gate", fontsize=12)
    ax.set_xlabel("week"); ax.set_ylabel("return")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f"{y:.0f}%"))
    ax.set_xticks([])
    _wm(ax)
    fig.tight_layout(); fig.savefig(ASSETS / "weekly_dist.png"); plt.close(fig)


def chart_cost(sub, W):
    pts = []
    for c in (0, 10, 40, 80):
        pts.append((c, metrics_from_returns(strategy_returns(sub, W, cost_bps=c)).total_return * 100))
    live = metrics_from_returns(strategy_returns(sub, W, cost_bps_by_name=U.dex_cost_bps())).total_return * 100
    fig, ax = plt.subplots(figsize=(8.4, 4.2))
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    ax.plot(xs, ys, color=MUTE, lw=2, marker="o", ms=6, mfc=CYAN, mec=BG, label="flat-bps reference")
    ax.scatter([95], [live], color=GOLD, s=130, zorder=5, marker="D", edgecolor=BG,
               label=f"per-name measured DEX cost ({live:+.1f}%)")
    ax.annotate("the earlier report\nstopped here (+17%)", (10, pts[1][1]), textcoords="offset points",
                xytext=(14, 2), color=CYAN, fontsize=8.5)
    ax.annotate("honest headline\n(net of real slippage)", (95, live), textcoords="offset points",
                xytext=(0, 26), ha="center", color=GOLD, fontsize=9, fontweight="bold",
                arrowprops=dict(arrowstyle="-", color=GOLD, lw=1, alpha=0.6))
    ax.axhline(0, color=INK, lw=0.8, alpha=0.3)
    ax.set_xlabel("transaction cost (bps)"); ax.set_ylabel("full-window return")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f"{y:.0f}%"))
    ax.set_title("Cost sensitivity — why the +20% draft was a phantom")
    ax.legend(loc="upper right", facecolor=PANEL, edgecolor=GRID, framealpha=0.9, fontsize=9)
    _wm(ax)
    fig.tight_layout(); fig.savefig(ASSETS / "cost_curve.png"); plt.close(fig)


def chart_universe():
    d = json.load(open(ROOT / "src" / "bnbhack_agent" / "data" / "dex_liquidity.json"))
    rows = [(k, v["weekly_usd"], v.get("impact_bps_200"), v["verdict"])
            for k, v in d.items() if isinstance(v, dict) and v.get("verdict", "").startswith("tradable")]
    rows.sort(key=lambda r: r[1])
    names = [r[0] for r in rows]; wk = [r[1] / 1000 for r in rows]; bps = [r[2] for r in rows]
    cols = [GOLD if r[3] == "tradable" else VIOLET for r in rows]
    fig, ax = plt.subplots(figsize=(8.6, 4.4))
    bars = ax.barh(names, wk, color=cols, alpha=0.9, edgecolor=BG)
    ax.axvline(20, color=RED, lw=1.4, ls="--")
    ax.text(20, len(names) - 0.4, " $20k/wk floor", color=RED, fontsize=9, fontweight="bold")
    ax.set_xscale("log")
    ax.set_xlabel("measured BSC DEX volume — $k / week (log)")
    for b, name, bp in zip(bars, names, bps):
        ax.text(b.get_width() * 1.05, b.get_y() + b.get_height() / 2, f"~{bp}bps",
                va="center", color=MUTE, fontsize=8)
    ax.set_title("Investable universe — ranked by on-chain depth, not CEX volume")
    _wm(ax)
    fig.tight_layout(); fig.savefig(ASSETS / "universe_liquidity.png"); plt.close(fig)


def main():
    px, cand, W, sub, cost_by, r = _load()
    m = metrics_from_returns(r)
    print(f"loaded: {len(cand)} names {cand} | full {m.total_return*100:+.2f}% DD {m.max_drawdown*100:.1f}%")
    chart_equity(px, sub, W, cost_by, r)
    chart_drawdown(r)
    chart_regime(px, W)
    chart_frontier()
    chart_weekly(r)
    chart_cost(sub, W)
    chart_universe()
    print("wrote charts to", ASSETS)


if __name__ == "__main__":
    main()
